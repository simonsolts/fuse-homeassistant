"""Config flow for the Fuse Energy integration.

Phone-OTP three-step flow:
  async_step_user → async_step_otp → (async_step_additional_info?) → entry

Reauth re-runs the same chain via async_step_reauth.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from . import auth as auth_mod
from .api import FuseEnergyApiClient
from .auth import (
    AdditionalInfoResult,
    AuthorizedResult,
    TokenPair,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_PHONE_NUMBER,
    CONF_PREMISES_FID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
_UNIQUE_ID = "fuse_energy_singleton"
_E164 = re.compile(r"^\+[1-9]\d{1,14}$")

_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_PHONE_NUMBER): str}
)


class FuseEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Phone-OTP config flow."""

    VERSION = 2

    def __init__(self) -> None:
        self._phone_number: str | None = None
        self._device_id: str | None = None
        self._auth_flow_token: str | None = None
        self._questions: list[auth_mod.Question] | None = None
        self._additional_info_title: str | None = None
        self._additional_info_subtitle: str | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        if self._async_current_entries() and self._reauth_entry is None:
            return self.async_abort(reason="single_instance_allowed")

        if self._reauth_entry is None:
            await self.async_set_unique_id(_UNIQUE_ID)
            self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            phone = user_input[CONF_PHONE_NUMBER].strip().replace(" ", "")
            if not _E164.match(phone):
                errors["base"] = "invalid_phone"
            else:
                session = aiohttp_client.async_get_clientsession(self.hass)
                device_id = (
                    self._reauth_entry.data[CONF_DEVICE_ID]
                    if self._reauth_entry is not None
                    else str(uuid.uuid4())
                )
                try:
                    token = await auth_mod.async_send_otp(
                        session, device_id=device_id, phone_number=phone,
                    )
                except auth_mod.FuseEnergyAuthError as e:
                    errors["base"] = e.error_code
                except auth_mod.FuseEnergyAuthTransient:
                    errors["base"] = "cannot_connect"
                else:
                    self._phone_number = phone
                    self._device_id = device_id
                    self._auth_flow_token = token
                    return await self.async_step_otp()

        return self.async_show_form(
            step_id="user", data_schema=_USER_SCHEMA, errors=errors,
        )

    _OTP_SCHEMA = vol.Schema({vol.Required("verification_code"): str})

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._auth_flow_token is not None
            assert self._device_id is not None
            code = user_input["verification_code"].strip()
            session = aiohttp_client.async_get_clientsession(self.hass)
            try:
                result = await auth_mod.async_verify_otp(
                    session,
                    device_id=self._device_id,
                    auth_flow_token=self._auth_flow_token,
                    code=code,
                )
            except auth_mod.FuseEnergyAuthError as e:
                errors["base"] = e.error_code
            except auth_mod.FuseEnergyAuthTransient:
                errors["base"] = "cannot_connect"
            else:
                if isinstance(result, AuthorizedResult):
                    return await self._async_finalise(result.tokens)
                if isinstance(result, AdditionalInfoResult):
                    self._auth_flow_token = result.auth_flow_token
                    self._questions = result.questions
                    self._additional_info_title = result.title
                    self._additional_info_subtitle = result.subtitle
                    return await self.async_step_additional_info()

        return self.async_show_form(
            step_id="otp",
            data_schema=self._OTP_SCHEMA,
            errors=errors,
            description_placeholders={"phone_number": self._phone_number or ""},
        )

    async def _async_finalise(self, tokens: TokenPair) -> FlowResult:
        """Discover premises and either create the entry or reload an existing one."""
        assert self._device_id is not None
        session = aiohttp_client.async_get_clientsession(self.hass)
        client = FuseEnergyApiClient(
            session=session,
            device_id=self._device_id,
            tokens=tokens,
            on_tokens_refreshed=_noop_persist,
        )
        try:
            premises = await client.async_list_premises()
        except Exception as e:
            _LOGGER.warning("premises discovery failed: %s", e)
            return self.async_abort(reason="cannot_connect")

        if not premises:
            return self.async_abort(reason="no_premises")
        if len(premises) > 1:
            return self.async_abort(reason="multi_premises")

        data = {
            CONF_PHONE_NUMBER: self._phone_number,
            CONF_DEVICE_ID: self._device_id,
            CONF_ACCESS_TOKEN: tokens.access_token,
            CONF_REFRESH_TOKEN: tokens.refresh_token,
            CONF_PREMISES_FID: premises[0].fid,
        }

        if self._reauth_entry is not None:
            return self.async_update_reload_and_abort(
                self._reauth_entry, data=data,
                reason="reauth_successful",
            )

        return self.async_create_entry(title="Fuse Energy", data=data)

    async def async_step_additional_info(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        from homeassistant.helpers import selector

        assert self._questions is not None

        errors: dict[str, str] = {}
        if user_input is not None:
            responses: dict[str, str] = {}
            for q in self._questions:
                raw = user_input.get(q.key)
                if raw is None:
                    continue
                if q.type == "DATE" and hasattr(raw, "isoformat"):
                    responses[q.key] = raw.isoformat()
                else:
                    responses[q.key] = str(raw)

            session = aiohttp_client.async_get_clientsession(self.hass)
            try:
                result = await auth_mod.async_submit_additional_info(
                    session,
                    device_id=self._device_id,  # type: ignore[arg-type]
                    auth_flow_token=self._auth_flow_token,  # type: ignore[arg-type]
                    responses=responses,
                )
            except auth_mod.FuseEnergyAuthError as e:
                errors["base"] = e.error_code
            except auth_mod.FuseEnergyAuthTransient:
                errors["base"] = "cannot_connect"
            else:
                if isinstance(result, AuthorizedResult):
                    return await self._async_finalise(result.tokens)
                if isinstance(result, AdditionalInfoResult):
                    self._auth_flow_token = result.auth_flow_token
                    self._questions = result.questions
                    self._additional_info_title = result.title
                    self._additional_info_subtitle = result.subtitle
                    return await self.async_step_additional_info()

        # Build dynamic schema from the question list.
        fields: dict = {}
        for q in self._questions:
            if q.type == "DATE":
                fields[vol.Required(q.key)] = selector.DateSelector()
            else:
                if q.type != "TEXT":
                    _LOGGER.warning(
                        "unknown additional-info question type %r for key %r; rendering as text",
                        q.type, q.key,
                    )
                fields[vol.Required(q.key)] = str

        return self.async_show_form(
            step_id="additional_info",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={
                "title": getattr(self, "_additional_info_title", "") or "",
                "subtitle": getattr(self, "_additional_info_subtitle", "") or "",
            },
        )


async def _noop_persist(_tokens: TokenPair) -> None:
    """Used during config-flow premises discovery — no refresh should happen
    with brand-new tokens, but if it did we'd just drop the result here."""
    return None
