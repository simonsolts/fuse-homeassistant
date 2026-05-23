"""Fuse Energy API client.

STUB: the Fuse Energy API has not been reverse-engineered yet. The client
exposes the interface the rest of the integration depends on, but
`async_get_data` raises NotImplementedError. A later task will fill it in.
"""
from __future__ import annotations

from dataclasses import dataclass

import aiohttp


class FuseEnergyApiError(Exception):
    """Generic error talking to the Fuse Energy API (network, 5xx, malformed)."""


class FuseEnergyApiAuthError(FuseEnergyApiError):
    """The access token was rejected (401 or equivalent)."""


@dataclass(slots=True)
class FuseEnergyData:
    """Snapshot of usage and cost returned by the API."""

    energy_total_kwh: float | None
    cost_total_gbp: float | None


class FuseEnergyApiClient:
    """Async client for the Fuse Energy customer API.

    The constructor signature is locked in here so the coordinator and config
    flow can depend on it. The body of `async_get_data` is intentionally a
    NotImplementedError until reverse-engineering lands.
    """

    def __init__(self, session: aiohttp.ClientSession, access_token: str) -> None:
        self._session = session
        self._access_token = access_token

    async def async_get_data(self) -> FuseEnergyData:
        raise NotImplementedError(
            "Fuse Energy API not yet reverse-engineered"
        )
