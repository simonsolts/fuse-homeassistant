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

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema({vol.Required("verification_code"): str}),
        )
