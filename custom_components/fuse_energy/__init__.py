"""Fuse Energy custom integration for Home Assistant."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .api import FuseEnergyApiClient
from .auth import TokenPair
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_PREMISES_FID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)
from .coordinator import FuseEnergyDataUpdateCoordinator

_PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = aiohttp_client.async_get_clientsession(hass)

    async def _persist_tokens(new_tokens: TokenPair) -> None:
        """Called by FuseEnergyApiClient after every successful refresh.
        Persist BEFORE the client swaps its in-memory copy so disk and memory
        never diverge."""
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_ACCESS_TOKEN: new_tokens.access_token,
                CONF_REFRESH_TOKEN: new_tokens.refresh_token,
            },
        )

    client = FuseEnergyApiClient(
        session=session,
        device_id=entry.data[CONF_DEVICE_ID],
        tokens=TokenPair(
            access_token=entry.data[CONF_ACCESS_TOKEN],
            refresh_token=entry.data[CONF_REFRESH_TOKEN],
        ),
        on_tokens_refreshed=_persist_tokens,
    )
    coordinator = FuseEnergyDataUpdateCoordinator(
        hass, client, premises_fid=entry.data[CONF_PREMISES_FID],
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
