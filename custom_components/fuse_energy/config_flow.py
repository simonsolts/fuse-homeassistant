"""Config flow for the Fuse Energy integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .api import (
    FuseEnergyApiAuthError,
    FuseEnergyApiClient,
    FuseEnergyApiError,
)
from .const import CONF_ACCESS_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

_UNIQUE_ID = "fuse_energy_singleton"

_USER_SCHEMA = vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str})


class FuseEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        # Enforce a single instance of this integration. Using
        # ``_async_current_entries`` (rather than unique_id) lets us return the
        # canonical ``single_instance_allowed`` abort reason that HA's frontend
        # surfaces with a translated message.
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        await self.async_set_unique_id(_UNIQUE_ID)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN]
            session = aiohttp_client.async_get_clientsession(self.hass)
            client = FuseEnergyApiClient(session=session, access_token=token)
            try:
                await client.async_get_data()
            except FuseEnergyApiAuthError:
                errors["base"] = "invalid_auth"
            except FuseEnergyApiError:
                errors["base"] = "cannot_connect"
            except NotImplementedError:
                # TODO: while the API is stubbed, accept the token unconditionally.
                # Replace this branch with real validation once the API is wired up.
                pass

            if not errors:
                return self.async_create_entry(
                    title="Fuse Energy",
                    data={CONF_ACCESS_TOKEN: token},
                )

        return self.async_show_form(
            step_id="user", data_schema=_USER_SCHEMA, errors=errors
        )
