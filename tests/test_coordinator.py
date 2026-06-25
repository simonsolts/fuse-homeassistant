"""Tests for FuseEnergyDataUpdateCoordinator (backfill orchestration)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

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
        local_date=d,
        local_hour=h,
        kwh=Decimal(kwh),
        cost_gbp=Decimal(cost),
        is_realised=realised,
    )


def _make_coord(
    hass: HomeAssistant, client: FuseEnergyApiClient
) -> FuseEnergyDataUpdateCoordinator:
    return FuseEnergyDataUpdateCoordinator(hass, client, premises_fid="pfid")


async def test_fetches_today_only_when_no_prior_statistics(
    recorder_mock,
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
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
    recorder_mock,
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
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
    fetched = [c.args[1] for c in client.async_fetch_day.call_args_list]
    assert fetched == [last_imported, last_imported + timedelta(days=1), today_ldn]


async def test_auth_error_translates_to_config_entry_auth_failed(
    recorder_mock,
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "custom_components.fuse_energy.coordinator._async_last_imported_date",
        AsyncMock(return_value=None),
    )
    client = MagicMock(spec=FuseEnergyApiClient)
    client.async_fetch_day = AsyncMock(
        side_effect=FuseEnergyApiAuthError("bad cookies")
    )

    coord = _make_coord(hass, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()


async def test_api_error_translates_to_update_failed(
    recorder_mock,
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
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
    recorder_mock,
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    freezer,
) -> None:
    # Freeze well past hour 11 local so h10/h11 are fully elapsed; the test
    # is about snapshot picking the latest realised+complete bar, not about
    # the in-progress filter.
    freezer.move_to("2026-05-26T18:00:00+00:00")
    today = date(2026, 5, 26)
    monkeypatch.setattr(
        "custom_components.fuse_energy.coordinator._async_last_imported_date",
        AsyncMock(return_value=today),
    )
    client = MagicMock(spec=FuseEnergyApiClient)
    client.async_fetch_day = AsyncMock(
        return_value=[
            _bar(today, 10, kwh="0.5", cost="0.1", realised=True),
            _bar(today, 11, kwh="0.7", cost="0.2", realised=True),
            _bar(today, 12, kwh="0.0", cost="0.0", realised=False),  # forecast
        ]
    )

    coord = _make_coord(hass, client)
    snap = await coord._async_update_data()
    assert snap.last_hour_kwh == pytest.approx(0.7)
    assert snap.last_hour_cost_gbp == pytest.approx(0.2)


async def test_in_progress_hour_excluded_from_writer_and_snapshot(
    recorder_mock,
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    freezer,
) -> None:
    """Fuse's mobile API marks the current (in-progress) hour as REALISED with
    a growing partial value. If we let that partial reach the statistics
    writer, the row gets locked at the partial value forever (subsequent
    ticks skip it via the start_ts <= last_start_ts check). So the
    coordinator must exclude any bar whose hour hasn't fully elapsed."""
    # Freeze to 2026-05-26 10:30 UTC == 11:30 Europe/London (BST = UTC+1).
    # Hours 0-10 local are fully elapsed; hour 11 is in progress.
    freezer.move_to("2026-05-26T10:30:00+00:00")
    today = date(2026, 5, 26)

    bars = [_bar(today, h, kwh="1.0", cost="0.1", realised=True) for h in range(11)]
    # h11 is the in-progress hour with a partial value Fuse marked REALISED.
    bars.append(_bar(today, 11, kwh="0.128", cost="0.03", realised=True))

    monkeypatch.setattr(
        "custom_components.fuse_energy.coordinator._async_last_imported_date",
        AsyncMock(return_value=today),
    )
    importer = AsyncMock()
    monkeypatch.setattr(
        "custom_components.fuse_energy.coordinator.async_import_hourly_bars",
        importer,
    )
    client = MagicMock(spec=FuseEnergyApiClient)
    client.async_fetch_day = AsyncMock(return_value=bars)

    coord = _make_coord(hass, client)
    snap = await coord._async_update_data()

    # Writer must NOT have been handed the in-progress h11 bar.
    importer.assert_called_once()
    passed = importer.call_args.args[2]
    assert {b.local_hour for b in passed} == set(range(11))

    # Snapshot reflects h10 (last fully-elapsed hour), not h11's partial.
    assert snap.last_hour_kwh == pytest.approx(1.0)
    assert snap.last_hour_cost_gbp == pytest.approx(0.1)
