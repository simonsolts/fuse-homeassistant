"""Config flow for the Fuse Energy integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from .api import (
    FuseEnergyApiAuthError,
    FuseEnergyApiClient,
    FuseEnergyApiError,
)
from .const import (
    CONF_APP_AUTH,
    CONF_PREMISES_FID,
    CONF_SESSION_ID,
    DOMAIN,
)

_UNIQUE_ID = "fuse_energy_singleton"
_FUSE_TZ = ZoneInfo("Europe/London")

_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SESSION_ID): str,
        vol.Required(CONF_APP_AUTH): str,
        vol.Required(CONF_PREMISES_FID): str,
    }
)


class FuseEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Fuse Energy."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        # Guards against the TOCTOU window between two simultaneous flow initiations.
        await self.async_set_unique_id(_UNIQUE_ID)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            session = aiohttp_client.async_get_clientsession(self.hass)
            client = FuseEnergyApiClient(
                session=session,
                session_id=user_input[CONF_SESSION_ID],
                app_auth=user_input[CONF_APP_AUTH],
                premises_fid=user_input[CONF_PREMISES_FID],
            )
            try:
                await client.async_fetch_day(datetime.now(_FUSE_TZ).date())
            except FuseEnergyApiAuthError:
                errors["base"] = "invalid_auth"
            except FuseEnergyApiError:
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(
                    title="Fuse Energy",
                    data=dict(user_input),
                )

        return self.async_show_form(
            step_id="user", data_schema=_USER_SCHEMA, errors=errors
        )
