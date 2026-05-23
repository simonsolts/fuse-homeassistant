"""Tests for FuseEnergyDataUpdateCoordinator (backfill orchestration)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.fuse_energy.api import (
    FuseEnergyApiAuthError,
    FuseEnergyApiClient,
    FuseEnergyApiError,
    HourlyBar,
)
from custom_components.fuse_energy.coordinator import (
    FuseEnergyDataUpdateCoordinator,
)


LDN = ZoneInfo("Europe/London")


def _bar(d: date, h: int, kwh="1.0", cost="0.1", realised=True) -> HourlyBar:
    return HourlyBar(
        local_date=d, local_hour=h,
        kwh=Decimal(kwh), cost_gbp=Decimal(cost),
        is_realised=realised,
    )


def _make_coord(hass: HomeAssistant, client: FuseEnergyApiClient) -> FuseEnergyDataUpdateCoordinator:
    return FuseEnergyDataUpdateCoordinator(hass, client, premises_fid="pfid")


async def test_fetches_today_only_when_no_prior_statistics(
    recorder_mock, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch,
) -> None:
    today_ldn = datetime.now(LDN).date()
    client = MagicMock(spec=FuseEnergyApiClient)
    client.async_fetch_day = AsyncMock(return_value=[_bar(today_ldn, 0)])

    # Fake "no prior statistics" by patching the writer's last-stat lookup.
    monkeypatch.setattr(
        "custom_components.fuse_energy.coordinator._async_last_imported_date",
        AsyncMock(return_value=None),
    )

    coord = _make_coord(hass, client)
    snapshot = await coord._async_update_data()

    # Initial-load horizon is 30 days, so it should iterate 31 days (incl today).
    assert client.async_fetch_day.call_count == 31
    assert snapshot is not None  # latest realised bar surfaced


async def test_resumes_from_last_statistic_date(
    recorder_mock, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch,
) -> None:
    today_ldn = datetime.now(LDN).date()
    last_imported = today_ldn - timedelta(days=2)
    monkeypatch.setattr(
        "custom_components.fuse_energy.coordinator._async_last_imported_date",
        AsyncMock(return_value=last_imported),
    )

    client = MagicMock(spec=FuseEnergyApiClient)
    client.async_fetch_day = AsyncMock(return_value=[_bar(today_ldn, 0)])

    coord = _make_coord(hass, client)
    await coord._async_update_data()

    # Resumes from last_imported through today inclusive → 3 days.
    assert client.async_fetch_day.call_count == 3
    fetched = [c.args[0] for c in client.async_fetch_day.call_args_list]
    assert fetched == [last_imported, last_imported + timedelta(days=1), today_ldn]


async def test_auth_error_translates_to_config_entry_auth_failed(
    recorder_mock, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "custom_components.fuse_energy.coordinator._async_last_imported_date",
        AsyncMock(return_value=None),
    )
    client = MagicMock(spec=FuseEnergyApiClient)
    client.async_fetch_day = AsyncMock(side_effect=FuseEnergyApiAuthError("bad cookies"))

    coord = _make_coord(hass, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()


async def test_api_error_translates_to_update_failed(
    recorder_mock, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "custom_components.fuse_energy.coordinator._async_last_imported_date",
        AsyncMock(return_value=None),
    )
    client = MagicMock(spec=FuseEnergyApiClient)
    client.async_fetch_day = AsyncMock(side_effect=FuseEnergyApiError("boom"))

    coord = _make_coord(hass, client)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


async def test_snapshot_holds_latest_realised_bar(
    recorder_mock, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = datetime.now(LDN).date()
    monkeypatch.setattr(
        "custom_components.fuse_energy.coordinator._async_last_imported_date",
        AsyncMock(return_value=today),
    )
    client = MagicMock(spec=FuseEnergyApiClient)
    client.async_fetch_day = AsyncMock(return_value=[
        _bar(today, 10, kwh="0.5", cost="0.1", realised=True),
        _bar(today, 11, kwh="0.7", cost="0.2", realised=True),
        _bar(today, 12, kwh="0.0", cost="0.0", realised=False),  # forecast
    ])

    coord = _make_coord(hass, client)
    snap = await coord._async_update_data()
    assert snap.last_hour_kwh == pytest.approx(0.7)
    assert snap.last_hour_cost_gbp == pytest.approx(0.2)
