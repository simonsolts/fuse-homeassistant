"""Fuse Energy tRPC client.

Protocol summary:

- Endpoint: ``GET /api/trpc/premisesDisplayData?input=<urlencoded-json>``
  where the JSON is ``{"premisesFid": <uuid>, "index": {"year","month","day"}}``.
- Auth: cookies ``session_id`` (UUID) and ``app-auth`` (server-encrypted token).
- Required header: ``x-fuse-app-version: <live value>`` — strict equality.
  Wrong/missing value -> HTTP 500 with ``____reloadRequired: true``.
- Sign-out signal: HTTP 500 with ``____signOutRequired: true``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from urllib.parse import quote

import aiohttp

from .const import FUSE_BASE_URL, FUSE_TRPC_PATH
from .version_resolver import AppVersionResolver

_LOGGER = logging.getLogger(__name__)
_FETCH_PATH = f"{FUSE_TRPC_PATH}/premisesDisplayData"


class FuseEnergyApiError(Exception):
    """Generic error talking to the Fuse Energy API (network, 5xx, malformed)."""


class FuseEnergyApiAuthError(FuseEnergyApiError):
    """Cookies are missing/invalid or the server signalled ____signOutRequired."""


@dataclass(slots=True, frozen=True)
class HourlyBar:
    """One hour of consumption + cost from Fuse's chart.

    Local date/hour are in Europe/London. Translation to UTC happens
    in the statistics writer.
    """

    local_date: date
    local_hour: int
    kwh: Decimal
    cost_gbp: Decimal
    is_realised: bool


class FuseEnergyApiClient:
    """Async client for the Fuse Energy customer tRPC API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        session_id: str,
        app_auth: str,
        premises_fid: str,
        version_resolver: AppVersionResolver | None = None,
    ) -> None:
        self._session = session
        self._session_id = session_id
        self._app_auth = app_auth
        self._premises_fid = premises_fid
        self._version_resolver = version_resolver or AppVersionResolver(session)

    async def async_fetch_day(self, local_date: date) -> list[HourlyBar]:
        """Fetch hourly bars for one local-time date.

        Retries once after invalidating the version resolver if the server
        signals ``____reloadRequired`` (UI version drift). Raises
        ``FuseEnergyApiAuthError`` on auth failure, ``FuseEnergyApiError``
        on anything else.
        """
        try:
            return await self._fetch_once(local_date)
        except _StalledUIError:
            _LOGGER.warning(
                "Cached x-fuse-app-version is stale; refreshing version and retrying."
            )
            self._version_resolver.invalidate()
            try:
                return await self._fetch_once(local_date)
            except _StalledUIError as err:
                raise FuseEnergyApiError(
                    "Fuse rejected request as 'UI stalled' twice in a row; "
                    "either the version-discovery is broken or the API contract "
                    "changed."
                ) from err

    async def _fetch_once(self, local_date: date) -> list[HourlyBar]:
        version = await self._version_resolver.async_resolve()
        input_obj = {
            "premisesFid": self._premises_fid,
            "index": {
                "year": local_date.year,
                "month": local_date.month,
                "day": local_date.day,
            },
        }
        url = (
            f"{FUSE_BASE_URL}{_FETCH_PATH}"
            f"?input={quote(json.dumps(input_obj, separators=(',', ':')))}"
        )
        headers = {"x-fuse-app-version": version}
        cookies = {"session_id": self._session_id, "app-auth": self._app_auth}

        try:
            async with self._session.get(url, headers=headers, cookies=cookies) as resp:
                if resp.status == 401:
                    raise FuseEnergyApiAuthError("HTTP 401 from Fuse")
                payload = await resp.json()
                if resp.status == 200:
                    return _parse_bars(payload, local_date)
                _classify_error(payload)
                raise FuseEnergyApiError(
                    f"unexpected HTTP {resp.status} from Fuse: {payload}"
                )
        except aiohttp.ClientError as err:
            raise FuseEnergyApiError(str(err)) from err


class _StalledUIError(Exception):
    """Internal marker for ____reloadRequired:true responses."""


def _classify_error(payload: dict) -> None:
    """Raise the right exception class based on the tRPC error envelope."""
    data = ((payload or {}).get("error") or {}).get("data") or {}
    if data.get("____signOutRequired"):
        raise FuseEnergyApiAuthError(
            "Fuse signalled ____signOutRequired (session expired)"
        )
    if data.get("____reloadRequired"):
        raise _StalledUIError("UI stalled — x-fuse-app-version is wrong")
    # fall through; caller raises FuseEnergyApiError


def _parse_bars(payload: dict, local_date: date) -> list[HourlyBar]:
    """Extract the elec-import bars from a premisesDisplayData response."""
    chart = ((payload or {}).get("result") or {}).get("data") or {}
    chart = (chart.get("data") or {}).get("chart") or {}
    bars: list[HourlyBar] = []
    for supply in chart.get("supplies") or ():
        if supply.get("supply_type") != "ELEC_IMPORT":
            continue
        for entry in supply.get("bars") or ():
            bar = entry.get("bar") or {}
            idx = bar.get("index") or {}
            if (idx.get("year"), idx.get("month"), idx.get("day")) != (
                local_date.year,
                local_date.month,
                local_date.day,
            ):
                continue
            bars.append(
                HourlyBar(
                    local_date=local_date,
                    local_hour=int(idx.get("hour", 0)),
                    kwh=Decimal(str(bar.get("kWh"))),
                    cost_gbp=Decimal(str((bar.get("money") or {}).get("amount"))),
                    is_realised=bar.get("type") == "REALISED",
                )
            )
    bars.sort(key=lambda b: b.local_hour)
    return bars
