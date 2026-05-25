"""Fuse Energy mobile-API client.

Targets api.fuseenergy.com with Authorization: Bearer <access_token> +
Device-Id headers. Wraps every call with transparent refresh-on-401.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Awaitable, Callable

import aiohttp

from .auth import (
    FuseEnergyAuthError,
    FuseEnergyAuthTransient,
    TokenPair,
    async_refresh,
)
from .const import FUSE_API_BASE_URL

_LOGGER = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=15)


class FuseEnergyApiError(Exception):
    """Generic transport / parse error — caller maps to UpdateFailed."""


class FuseEnergyApiAuthError(FuseEnergyApiError):
    """Refresh itself failed — caller maps to ConfigEntryAuthFailed."""


@dataclass(frozen=True, slots=True)
class Premises:
    """A premises returned by /api/v2/customer/premises."""
    fid: str


@dataclass(frozen=True, slots=True)
class HourlyBar:
    """One hour of consumption + cost. Same shape as the previous client."""
    local_date: date
    local_hour: int
    kwh: Decimal
    cost_gbp: Decimal
    is_realised: bool


class FuseEnergyApiClient:
    """Mobile-API client with refresh-on-401 retry."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        device_id: str,
        tokens: TokenPair,
        on_tokens_refreshed: Callable[[TokenPair], Awaitable[None]],
    ) -> None:
        self._session = session
        self._device_id = device_id
        self._tokens = tokens
        self._on_tokens_refreshed = on_tokens_refreshed
        self._refresh_lock = asyncio.Lock()

    @property
    def tokens(self) -> TokenPair:
        return self._tokens
