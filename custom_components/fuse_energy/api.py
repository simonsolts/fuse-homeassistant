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

    async def _request(self, method: str, path: str, **kw) -> dict | list:
        """Issue an authenticated request; on 401, refresh once and retry.

        On second 401 (or refresh-itself failure), raise FuseEnergyApiAuthError.
        On 5xx / network, raise FuseEnergyApiError.
        """
        for attempt in (0, 1):
            headers = {
                "Authorization": f"Bearer {self._tokens.access_token}",
                "Device-Id": self._device_id,
                **kw.pop("headers", {}),
            }
            try:
                async with self._session.request(
                    method, f"{FUSE_API_BASE_URL}{path}",
                    headers=headers, timeout=_TIMEOUT, **kw,
                ) as r:
                    if r.status == 401:
                        if attempt == 1:
                            raise FuseEnergyApiAuthError(
                                "401 even after refresh"
                            )
                        await self._refresh_tokens()
                        continue
                    if 500 <= r.status:
                        raise FuseEnergyApiError(
                            f"HTTP {r.status} from {path}"
                        )
                    if not (200 <= r.status < 300):
                        body = await r.text()
                        raise FuseEnergyApiError(
                            f"HTTP {r.status} from {path}: {body[:200]}"
                        )
                    return await r.json()
            except aiohttp.ClientError as e:
                raise FuseEnergyApiError(f"network: {e}") from e
        raise FuseEnergyApiError("unreachable")

    async def _get(self, path: str, **kw) -> dict | list:
        # Defer to _request, but use session.get to keep test seams simple.
        headers = {
            "Authorization": f"Bearer {self._tokens.access_token}",
            "Device-Id": self._device_id,
        }
        try:
            async with self._session.get(
                f"{FUSE_API_BASE_URL}{path}",
                headers=headers, timeout=_TIMEOUT, **kw,
            ) as r:
                if r.status == 401:
                    await self._refresh_tokens()
                    headers["Authorization"] = f"Bearer {self._tokens.access_token}"
                    async with self._session.get(
                        f"{FUSE_API_BASE_URL}{path}",
                        headers=headers, timeout=_TIMEOUT, **kw,
                    ) as r2:
                        if r2.status == 401:
                            raise FuseEnergyApiAuthError("401 even after refresh")
                        if not (200 <= r2.status < 300):
                            raise FuseEnergyApiError(
                                f"HTTP {r2.status} from {path}"
                            )
                        return await r2.json()
                if 500 <= r.status:
                    raise FuseEnergyApiError(f"HTTP {r.status} from {path}")
                if not (200 <= r.status < 300):
                    raise FuseEnergyApiError(f"HTTP {r.status} from {path}")
                return await r.json()
        except aiohttp.ClientError as e:
            raise FuseEnergyApiError(f"network: {e}") from e

    async def _refresh_tokens(self) -> None:
        """Refresh the token pair, serialised so concurrent ticks share one
        refresh. Persists via on_tokens_refreshed BEFORE swapping in-memory."""
        snapshot = self._tokens.access_token
        async with self._refresh_lock:
            if self._tokens.access_token != snapshot:
                return  # another caller already refreshed
            try:
                new_tokens = await async_refresh(
                    self._session,
                    device_id=self._device_id,
                    tokens=self._tokens,
                )
            except FuseEnergyAuthError as e:
                raise FuseEnergyApiAuthError(str(e)) from e
            except FuseEnergyAuthTransient as e:
                raise FuseEnergyApiError(str(e)) from e
            await self._on_tokens_refreshed(new_tokens)
            self._tokens = new_tokens

    async def async_list_premises(self) -> list[Premises]:
        """GET /api/v2/customer/premises.

        Response shape:
          [{"premises": {"id": "<uuid>", ...}, "supplies": [...], "default_date_uk": "..."}, ...]
        """
        data = await self._get("/api/v2/customer/premises")
        if not isinstance(data, list):
            raise FuseEnergyApiError(f"unexpected list-premises shape: {type(data)}")
        out: list[Premises] = []
        for entry in data:
            inner = (entry or {}).get("premises") or {}
            fid = inner.get("id")
            if not fid:
                continue
            out.append(Premises(fid=fid))
        return out
