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
            stale_token = self._tokens.access_token
            headers = {
                "Authorization": f"Bearer {stale_token}",
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
                        await self._refresh_tokens(stale_token)
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
        # Capture the token we're about to use so _refresh_tokens can detect
        # whether a concurrent caller already refreshed on our behalf.
        stale_token = self._tokens.access_token
        headers = {
            "Authorization": f"Bearer {stale_token}",
            "Device-Id": self._device_id,
        }
        try:
            async with self._session.get(
                f"{FUSE_API_BASE_URL}{path}",
                headers=headers, timeout=_TIMEOUT, **kw,
            ) as r:
                if r.status == 401:
                    # Yield once so sibling tasks can reach the same 401 branch
                    # before any refresh starts, maximising deduplication.
                    await asyncio.sleep(0)
                    await self._refresh_tokens(stale_token)
                    headers = {
                        "Authorization": f"Bearer {self._tokens.access_token}",
                        "Device-Id": self._device_id,
                    }
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

    async def _refresh_tokens(self, stale_token: str) -> None:
        """Refresh the token pair, serialised so concurrent ticks share one
        refresh. Guards by stale_token so both the concurrent-waiter case
        (blocked on the lock while another caller refreshed) and the
        sequential case (caller started after refresh completed) are handled:
        if the current access_token is no longer stale_token the refresh
        already happened and we skip it.

        Persists via on_tokens_refreshed BEFORE swapping in-memory.
        """
        async with self._refresh_lock:
            if self._tokens.access_token != stale_token:
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

    async def async_fetch_day(
        self, premises_fid: str, local_date: date,
    ) -> list[HourlyBar]:
        """GET /api/v1/premises/{premises_fid}/chart?year=Y&month=M&day=D.

        Response shape (flat — no tRPC wrapping):
          {"current_index": {...}, "supplies": [{"supply_fid", "supply_type",
                                                  "bars": [{"bar": {...}, "breakdown": [...]}]}, ...]}
        """
        data = await self._get(
            f"/api/v1/premises/{premises_fid}/chart",
            params={
                "year": local_date.year,
                "month": local_date.month,
                "day": local_date.day,
            },
        )
        if not isinstance(data, dict):
            raise FuseEnergyApiError(f"unexpected chart shape: {type(data)}")
        # DIAGNOSTIC: dump current_index + last 3 raw ELEC_IMPORT bars from the
        # payload so we can see exactly what Fuse classifies as REALISED.
        current_index = data.get("current_index")
        raw_elec_bars: list[dict] = []
        for supply in data.get("supplies") or ():
            if supply.get("supply_type") == "ELEC_IMPORT":
                raw_elec_bars = [e.get("bar") or {} for e in (supply.get("bars") or ())]
                break
        _LOGGER.warning(
            "[fuse-diag] fetch_day %s: current_index=%s; raw last 3 elec bars=%s",
            local_date,
            current_index,
            raw_elec_bars[-3:],
        )
        bars = _parse_bars(data, local_date)
        if bars:
            recent = sorted(bars, key=lambda b: b.local_hour)[-3:]
            _LOGGER.warning(
                "[fuse-diag] fetch_day %s parsed %d bars; last 3=%s",
                local_date,
                len(bars),
                [
                    f"h{b.local_hour:02d} kwh={b.kwh} cost={b.cost_gbp} realised={b.is_realised}"
                    for b in recent
                ],
            )
        else:
            _LOGGER.warning(
                "[fuse-diag] fetch_day %s parsed 0 bars (current_index=%s)",
                local_date,
                current_index,
            )
        return bars


def _parse_bars(payload: dict, local_date: date) -> list[HourlyBar]:
    """Extract ELEC_IMPORT bars matching local_date from the chart payload."""
    bars: list[HourlyBar] = []
    for supply in payload.get("supplies") or ():
        if supply.get("supply_type") != "ELEC_IMPORT":
            continue
        for entry in supply.get("bars") or ():
            bar = entry.get("bar") or {}
            idx = bar.get("index") or {}
            if (idx.get("year"), idx.get("month"), idx.get("day")) != (
                local_date.year, local_date.month, local_date.day,
            ):
                continue
            kwh_raw = bar.get("kWh")
            amount_raw = (bar.get("money") or {}).get("amount")
            if kwh_raw is None or amount_raw is None:
                continue
            bars.append(
                HourlyBar(
                    local_date=local_date,
                    local_hour=int(idx.get("hour", 0)),
                    kwh=Decimal(str(kwh_raw)),
                    cost_gbp=Decimal(str(amount_raw)),
                    is_realised=bar.get("type") == "REALISED",
                )
            )
    bars.sort(key=lambda b: b.local_hour)
    return bars
