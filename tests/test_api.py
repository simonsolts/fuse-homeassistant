"""Tests for the Fuse Energy tRPC client."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import quote

import aiohttp
import pytest

from custom_components.fuse_energy.api import (
    FuseEnergyApiAuthError,
    FuseEnergyApiClient,
    FuseEnergyApiError,
    HourlyBar,
)
from custom_components.fuse_energy.version_resolver import AppVersionResolver


def test_hourly_bar_is_a_dataclass_with_expected_fields() -> None:
    bar = HourlyBar(
        local_date=date(2026, 5, 21),
        local_hour=20,
        kwh=Decimal("7.633"),
        cost_gbp=Decimal("1.76"),
        is_realised=True,
    )
    assert bar.local_date == date(2026, 5, 21)
    assert bar.local_hour == 20
    assert bar.kwh == Decimal("7.633")
    assert bar.cost_gbp == Decimal("1.76")
    assert bar.is_realised is True


def test_exception_hierarchy() -> None:
    assert issubclass(FuseEnergyApiAuthError, FuseEnergyApiError)


def test_client_constructor_signature() -> None:
    session = MagicMock(spec=aiohttp.ClientSession)
    client = FuseEnergyApiClient(
        session=session,
        session_id="sid",
        app_auth="aa",
        premises_fid="pfid",
    )
    assert client._premises_fid == "pfid"


# ---------------------------------------------------------------------------
# Task 4: async_fetch_day
# ---------------------------------------------------------------------------


def _resp(status: int, json_body) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_body)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _sample_payload() -> dict:
    return {"result": {"data": {"data": {"chart": {
        "current_index": {"year": 2026, "month": 5, "day": 21, "hour": 23},
        "supplies": [{
            "supply_fid": "supply-uuid",
            "supply_type": "ELEC_IMPORT",
            "bars": [
                {"bar": {
                    "index": {"year": 2026, "month": 5, "day": 21, "hour": 0},
                    "money": {"amount": "0.03", "currency": "GBP"},
                    "kWh": "0.128",
                    "type": "REALISED",
                }, "breakdown": []},
                {"bar": {
                    "index": {"year": 2026, "month": 5, "day": 21, "hour": 1},
                    "money": {"amount": "0.04", "currency": "GBP"},
                    "kWh": "0.21",
                    "type": "FORECAST",
                }, "breakdown": []},
            ],
        }, {
            # Non-electricity supply must be ignored.
            "supply_fid": "gas-uuid",
            "supply_type": "GAS_IMPORT",
            "bars": [{"bar": {"index": {"year": 2026, "month": 5, "day": 21, "hour": 0},
                              "money": {"amount": "9.99", "currency": "GBP"},
                              "kWh": "99.0", "type": "REALISED"}, "breakdown": []}],
        }],
    }}}}}


def _make_client_with_session(session: MagicMock) -> FuseEnergyApiClient:
    resolver = MagicMock(spec=AppVersionResolver)
    resolver.async_resolve = AsyncMock(return_value="5.310")
    resolver.invalidate = MagicMock()
    return FuseEnergyApiClient(
        session=session,
        session_id="sid",
        app_auth="aa",
        premises_fid="pfid",
        version_resolver=resolver,
    )


async def test_fetch_day_returns_only_elec_bars_in_order() -> None:
    session = MagicMock()
    session.get = MagicMock(return_value=_resp(200, _sample_payload()))
    client = _make_client_with_session(session)

    bars = await client.async_fetch_day(date(2026, 5, 21))

    assert [b.local_hour for b in bars] == [0, 1]
    assert bars[0].kwh == Decimal("0.128")
    assert bars[0].cost_gbp == Decimal("0.03")
    assert bars[0].is_realised is True
    assert bars[1].is_realised is False


async def test_fetch_day_sends_required_cookies_and_version_header() -> None:
    session = MagicMock()
    session.get = MagicMock(return_value=_resp(200, _sample_payload()))
    client = _make_client_with_session(session)
    await client.async_fetch_day(date(2026, 5, 21))

    call = session.get.call_args
    url = call.args[0]
    expected_input = quote(json.dumps(
        {"premisesFid": "pfid", "index": {"year": 2026, "month": 5, "day": 21}},
        separators=(",", ":"),
    ))
    assert url == (
        "https://www.fuseenergy.com/api/trpc/premisesDisplayData"
        f"?input={expected_input}"
    )
    assert call.kwargs["headers"]["x-fuse-app-version"] == "5.310"
    cookies = call.kwargs["cookies"]
    assert cookies["session_id"] == "sid"
    assert cookies["app-auth"] == "aa"


async def test_reload_required_triggers_one_retry_with_fresh_version() -> None:
    stalled = _resp(500, {"error": {"data": {"____reloadRequired": True, "httpStatus": 500}}})
    ok = _resp(200, _sample_payload())
    session = MagicMock()
    session.get = MagicMock(side_effect=[stalled, ok])

    resolver = MagicMock(spec=AppVersionResolver)
    resolver.async_resolve = AsyncMock(side_effect=["stale-1", "fresh-2"])
    resolver.invalidate = MagicMock()

    client = FuseEnergyApiClient(
        session=session,
        session_id="sid",
        app_auth="aa",
        premises_fid="pfid",
        version_resolver=resolver,
    )
    bars = await client.async_fetch_day(date(2026, 5, 21))
    assert bars  # success after retry
    resolver.invalidate.assert_called_once()
    assert session.get.call_count == 2
    # second call used the refreshed version
    assert session.get.call_args_list[1].kwargs["headers"]["x-fuse-app-version"] == "fresh-2"


async def test_reload_required_twice_in_a_row_raises_api_error() -> None:
    stalled = _resp(500, {"error": {"data": {"____reloadRequired": True, "httpStatus": 500}}})
    session = MagicMock()
    session.get = MagicMock(side_effect=[stalled, stalled])
    client = _make_client_with_session(session)

    with pytest.raises(FuseEnergyApiError):
        await client.async_fetch_day(date(2026, 5, 21))


async def test_sign_out_required_raises_auth_error() -> None:
    out = _resp(500, {"error": {"data": {"____signOutRequired": True, "httpStatus": 500}}})
    session = MagicMock()
    session.get = MagicMock(return_value=out)
    client = _make_client_with_session(session)

    with pytest.raises(FuseEnergyApiAuthError):
        await client.async_fetch_day(date(2026, 5, 21))


async def test_http_401_raises_auth_error() -> None:
    session = MagicMock()
    session.get = MagicMock(return_value=_resp(401, {"error": {}}))
    client = _make_client_with_session(session)

    with pytest.raises(FuseEnergyApiAuthError):
        await client.async_fetch_day(date(2026, 5, 21))


async def test_unexpected_500_raises_api_error() -> None:
    session = MagicMock()
    session.get = MagicMock(return_value=_resp(500, {"error": {"data": {"httpStatus": 500}}}))
    client = _make_client_with_session(session)

    with pytest.raises(FuseEnergyApiError) as exc_info:
        await client.async_fetch_day(date(2026, 5, 21))
    assert type(exc_info.value) is FuseEnergyApiError


async def test_network_error_raises_api_error() -> None:
    session = MagicMock()
    session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))
    client = _make_client_with_session(session)

    with pytest.raises(FuseEnergyApiError):
        await client.async_fetch_day(date(2026, 5, 21))
