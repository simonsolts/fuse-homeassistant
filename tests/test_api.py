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
