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

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import aiohttp

from .version_resolver import AppVersionResolver


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

    async def async_fetch_day(self, local_date: date) -> list[HourlyBar]:  # pragma: no cover (Task 4)
        raise NotImplementedError("implemented in Task 4")
