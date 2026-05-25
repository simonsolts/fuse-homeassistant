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
