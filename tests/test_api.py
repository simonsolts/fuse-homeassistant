"""Tests for the Fuse Energy tRPC client."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import aiohttp

from custom_components.fuse_energy.api import (
    FuseEnergyApiAuthError,
    FuseEnergyApiClient,
    FuseEnergyApiError,
    HourlyBar,
)


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
