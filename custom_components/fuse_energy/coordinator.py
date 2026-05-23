"""DataUpdateCoordinator that polls Fuse Energy and translates errors."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    FuseEnergyApiAuthError,
    FuseEnergyApiClient,
    FuseEnergyApiError,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class FuseEnergyDataUpdateCoordinator(DataUpdateCoordinator):  # rewritten in Task 6
    """Polls the Fuse Energy API and serves a FuseEnergyData snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: FuseEnergyApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self._client = client

    async def _async_update_data(self):
        try:
            return await self._client.async_get_data()
        except FuseEnergyApiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FuseEnergyApiError as err:
            raise UpdateFailed(str(err)) from err
        except NotImplementedError as err:
            raise UpdateFailed(
                "Fuse Energy API not yet reverse-engineered"
            ) from err
