"""Tests for the Fuse Energy mobile-API client."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.fuse_energy.api import (
    FuseEnergyApiAuthError,
    FuseEnergyApiClient,
    FuseEnergyApiError,
    HourlyBar,
    Premises,
)
from custom_components.fuse_energy.auth import TokenPair


def test_hourly_bar_fields() -> None:
    b = HourlyBar(
        local_date=date(2026, 5, 21), local_hour=20,
        kwh=Decimal("7.633"), cost_gbp=Decimal("1.76"), is_realised=True,
    )
    assert b.local_hour == 20


def test_premises_carries_fid() -> None:
    assert Premises(fid="abc").fid == "abc"


def test_exception_hierarchy() -> None:
    assert issubclass(FuseEnergyApiAuthError, FuseEnergyApiError)


def test_client_constructor_signature() -> None:
    session = MagicMock(spec=aiohttp.ClientSession)
    async def _cb(_): pass
    c = FuseEnergyApiClient(
        session=session,
        device_id="dev",
        tokens=TokenPair("a", "r"),
        on_tokens_refreshed=_cb,
    )
    assert c.tokens == TokenPair("a", "r")


def _resp(status: int, body):
    r = MagicMock()
    r.status = status
    r.json = AsyncMock(return_value=body)
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)
    return r


def _client_with_get(resp_or_resps, refreshed=None):
    """Build a client whose session.get returns the given response(s).
    `refreshed` is an optional callback to capture token-refresh events."""
    session = MagicMock(spec=aiohttp.ClientSession)
    if isinstance(resp_or_resps, list):
        session.get = MagicMock(side_effect=resp_or_resps)
    else:
        session.get = MagicMock(return_value=resp_or_resps)
    async def _cb(new):
        if refreshed is not None:
            refreshed.append(new)
    return FuseEnergyApiClient(
        session=session, device_id="dev",
        tokens=TokenPair("AT", "RT"), on_tokens_refreshed=_cb,
    ), session


async def test_list_premises_parses_nested_shape() -> None:
    resp = _resp(200, [
        {"premises": {"id": "p1"}, "supplies": [], "default_date_uk": "2026-05-25"},
        {"premises": {"id": "p2"}, "supplies": []},
    ])
    client, session = _client_with_get(resp)

    out = await client.async_list_premises()

    assert out == [Premises(fid="p1"), Premises(fid="p2")]

    args, kwargs = session.get.call_args_list[0]
    assert args[0] == "https://api.fuseenergy.com/api/v2/customer/premises"
    assert kwargs["headers"]["Authorization"] == "Bearer AT"
    assert kwargs["headers"]["Device-Id"] == "dev"


async def test_list_premises_empty_list() -> None:
    resp = _resp(200, [])
    client, _ = _client_with_get(resp)
    assert await client.async_list_premises() == []


async def test_list_premises_5xx_raises_api_error() -> None:
    resp = _resp(503, {})
    client, _ = _client_with_get(resp)
    with pytest.raises(FuseEnergyApiError):
        await client.async_list_premises()


_CHART_PAYLOAD = {
    "current_index": {"year": 2026, "month": 5, "day": 25, "hour": 22},
    "supplies": [
        {
            "supply_fid": "supply-1",
            "supply_type": "ELEC_IMPORT",
            "bars": [
                {
                    "bar": {
                        "index": {"year": 2026, "month": 5, "day": 25, "hour": 0},
                        "money": {"amount": "0.25", "currency": "GBP"},
                        "kWh": "1.297",
                        "type": "REALISED",
                    },
                    "breakdown": [],
                },
                {
                    "bar": {
                        "index": {"year": 2026, "month": 5, "day": 25, "hour": 1},
                        "money": {"amount": "0.18", "currency": "GBP"},
                        "kWh": "0.900",
                        "type": "REALISED",
                    },
                    "breakdown": [],
                },
                {
                    "bar": {
                        "index": {"year": 2026, "month": 5, "day": 25, "hour": 23},
                        "money": {"amount": "0.00", "currency": "GBP"},
                        "kWh": "0.000",
                        "type": "FORECAST",
                    },
                    "breakdown": [],
                },
            ],
        },
    ],
}


async def test_fetch_day_parses_bars_and_filters_non_target_date() -> None:
    resp = _resp(200, _CHART_PAYLOAD)
    client, session = _client_with_get(resp)

    bars = await client.async_fetch_day("p1", date(2026, 5, 25))

    assert len(bars) == 3
    assert bars[0] == HourlyBar(
        local_date=date(2026, 5, 25), local_hour=0,
        kwh=Decimal("1.297"), cost_gbp=Decimal("0.25"), is_realised=True,
    )
    assert bars[2].is_realised is False  # FORECAST → False

    args, kwargs = session.get.call_args_list[0]
    assert args[0] == "https://api.fuseenergy.com/api/v1/premises/p1/chart"
    assert kwargs["params"] == {"year": 2026, "month": 5, "day": 25}


async def test_fetch_day_skips_non_elec_supplies() -> None:
    payload = {
        "current_index": {"year": 2026, "month": 5, "day": 25, "hour": 22},
        "supplies": [
            {"supply_fid": "g", "supply_type": "GAS_IMPORT",
             "bars": [{"bar": {"index": {"year": 2026, "month": 5, "day": 25, "hour": 0},
                                "money": {"amount": "1.00", "currency": "GBP"},
                                "kWh": "1.0", "type": "REALISED"}, "breakdown": []}]},
        ],
    }
    resp = _resp(200, payload)
    client, _ = _client_with_get(resp)
    assert await client.async_fetch_day("p1", date(2026, 5, 25)) == []


async def test_fetch_day_5xx_raises_api_error() -> None:
    resp = _resp(500, {})
    client, _ = _client_with_get(resp)
    with pytest.raises(FuseEnergyApiError):
        await client.async_fetch_day("p1", date(2026, 5, 25))


async def test_401_then_refresh_then_retry_succeeds() -> None:
    # Sequence: first GET 401, refresh POST 200, second GET 200.
    first_get = _resp(401, {})
    second_get = _resp(200, _CHART_PAYLOAD)
    refresh = MagicMock()
    refresh.status = 200
    refresh.json = AsyncMock(return_value={
        "access_token": "AT_NEW", "refresh_token": "RT_NEW",
    })
    refresh.__aenter__ = AsyncMock(return_value=refresh)
    refresh.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock(spec=aiohttp.ClientSession)
    session.get = MagicMock(side_effect=[first_get, second_get])
    session.post = MagicMock(return_value=refresh)

    persisted: list[TokenPair] = []
    async def _cb(p): persisted.append(p)
    client = FuseEnergyApiClient(
        session=session, device_id="dev",
        tokens=TokenPair("AT_OLD", "RT_OLD"),
        on_tokens_refreshed=_cb,
    )

    bars = await client.async_fetch_day("p1", date(2026, 5, 25))

    assert len(bars) == 3
    assert client.tokens == TokenPair("AT_NEW", "RT_NEW")
    assert persisted == [TokenPair("AT_NEW", "RT_NEW")]
    # Second GET was retried with the NEW access token.
    second_call_headers = session.get.call_args_list[1].kwargs["headers"]
    assert second_call_headers["Authorization"] == "Bearer AT_NEW"


async def test_401_then_refresh_401_raises_auth_error() -> None:
    first_get = _resp(401, {})
    refresh = MagicMock()
    refresh.status = 401
    refresh.json = AsyncMock(return_value={"status_string": "refresh_revoked"})
    refresh.__aenter__ = AsyncMock(return_value=refresh)
    refresh.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock(spec=aiohttp.ClientSession)
    session.get = MagicMock(side_effect=[first_get])
    session.post = MagicMock(return_value=refresh)

    persisted: list[TokenPair] = []
    async def _cb(p): persisted.append(p)
    client = FuseEnergyApiClient(
        session=session, device_id="dev",
        tokens=TokenPair("AT_OLD", "RT_OLD"),
        on_tokens_refreshed=_cb,
    )

    with pytest.raises(FuseEnergyApiAuthError):
        await client.async_fetch_day("p1", date(2026, 5, 25))
    assert persisted == []  # never persisted because refresh failed
    assert client.tokens == TokenPair("AT_OLD", "RT_OLD")  # in-memory untouched


async def test_concurrent_callers_share_one_refresh() -> None:
    import asyncio

    # Both initial GETs 401; one refresh; both retries 200.
    first_a = _resp(401, {})
    first_b = _resp(401, {})
    retry_a = _resp(200, _CHART_PAYLOAD)
    retry_b = _resp(200, _CHART_PAYLOAD)
    refresh = MagicMock()
    refresh.status = 200
    refresh.json = AsyncMock(return_value={
        "access_token": "AT_NEW", "refresh_token": "RT_NEW",
    })
    refresh.__aenter__ = AsyncMock(return_value=refresh)
    refresh.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock(spec=aiohttp.ClientSession)
    session.get = MagicMock(side_effect=[first_a, first_b, retry_a, retry_b])
    session.post = MagicMock(return_value=refresh)

    persisted: list[TokenPair] = []
    async def _cb(p): persisted.append(p)
    client = FuseEnergyApiClient(
        session=session, device_id="dev",
        tokens=TokenPair("AT_OLD", "RT_OLD"),
        on_tokens_refreshed=_cb,
    )

    a, b = await asyncio.gather(
        client.async_fetch_day("p1", date(2026, 5, 25)),
        client.async_fetch_day("p1", date(2026, 5, 25)),
    )
    assert len(a) == 3 and len(b) == 3
    # Only ONE refresh POST despite two 401s.
    assert session.post.call_count == 1
    assert persisted == [TokenPair("AT_NEW", "RT_NEW")]
