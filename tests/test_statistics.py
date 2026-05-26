"""Tests for the external-statistics writer."""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.fuse_energy.api import HourlyBar
from custom_components.fuse_energy.const import stat_id_consumption, stat_id_cost
from custom_components.fuse_energy.statistics import async_import_hourly_bars


LDN = ZoneInfo("Europe/London")
PFID = "abc12345-1234-1234-1234-abcdef123456"


def _bar(hour: int, kwh: str, cost: str, *, realised: bool = True) -> HourlyBar:
    return HourlyBar(
        local_date=date(2026, 5, 21),
        local_hour=hour,
        kwh=Decimal(kwh),
        cost_gbp=Decimal(cost),
        is_realised=realised,
    )


def _utc_for(local_year: int, local_month: int, local_day: int, local_hour: int) -> datetime:
    return datetime(local_year, local_month, local_day, local_hour, tzinfo=LDN).astimezone(UTC)


async def test_imports_realised_hours_with_cumulative_sum(
    recorder_mock,
    hass: HomeAssistant,
) -> None:
    bars = [_bar(0, "0.1", "0.01"), _bar(1, "0.2", "0.02"), _bar(2, "0.3", "0.03")]

    await async_import_hourly_bars(hass, PFID, bars)
    await async_wait_recording_done(hass)

    kwh_id = stat_id_consumption(PFID)
    cost_id = stat_id_cost(PFID)

    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        _utc_for(2026, 5, 21, 0),
        None,
        {kwh_id, cost_id},
        "hour",
        None,
        {"start", "state", "sum"},
    )
    kwh_rows = rows[kwh_id]
    assert [r["state"] for r in kwh_rows] == [pytest.approx(0.1), pytest.approx(0.2), pytest.approx(0.3)]
    assert [r["sum"] for r in kwh_rows] == [pytest.approx(0.1), pytest.approx(0.3), pytest.approx(0.6)]

    cost_rows = rows[cost_id]
    assert [r["state"] for r in cost_rows] == [pytest.approx(0.01), pytest.approx(0.02), pytest.approx(0.03)]
    assert [r["sum"] for r in cost_rows] == [pytest.approx(0.01), pytest.approx(0.03), pytest.approx(0.06)]


async def test_skips_forecast_bars(recorder_mock, hass: HomeAssistant) -> None:
    bars = [
        _bar(0, "0.1", "0.01", realised=True),
        _bar(1, "0.2", "0.02", realised=False),
    ]

    await async_import_hourly_bars(hass, PFID, bars)
    await async_wait_recording_done(hass)

    kwh_id = stat_id_consumption(PFID)
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 5, kwh_id, True, {"sum", "state"}
    )
    assert len(last[kwh_id]) == 1
    assert last[kwh_id][0]["state"] == pytest.approx(0.1)


async def test_resumes_from_last_recorded_sum(
    recorder_mock, hass: HomeAssistant
) -> None:
    await async_import_hourly_bars(hass, PFID, [_bar(0, "0.5", "0.05")])
    await async_wait_recording_done(hass)

    await async_import_hourly_bars(
        hass, PFID, [_bar(0, "0.5", "0.05"), _bar(1, "0.4", "0.04")]
    )
    await async_wait_recording_done(hass)

    kwh_id = stat_id_consumption(PFID)
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 5, kwh_id, True, {"sum"}
    )
    sums = sorted(r["sum"] for r in last[kwh_id])
    assert sums == [pytest.approx(0.5), pytest.approx(0.9)]


async def test_empty_bars_is_noop(recorder_mock, hass: HomeAssistant) -> None:
    await async_import_hourly_bars(hass, PFID, [])
    await async_wait_recording_done(hass)

    kwh_id = stat_id_consumption(PFID)
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, kwh_id, True, {"sum"}
    )
    assert last == {}


async def test_recent_window_upserts_when_value_settles(
    recorder_mock, hass: HomeAssistant, freezer
) -> None:
    """Fuse's mobile API marks an hour as REALISED immediately when it ends
    but the value continues to settle for some hours as the meter pushes
    readings. The writer must rewrite the row when called again with an
    updated value, not lock the partial value via the append-only filter."""
    freezer.move_to("2026-05-21T14:00:00+00:00")

    # Tick 1: h10 BST = 09:00 UTC, partial value 0.1
    await async_import_hourly_bars(hass, PFID, [_bar(10, "0.1", "0.01")])
    await async_wait_recording_done(hass)

    # Tick 2: Fuse settled h10 to 1.5
    await async_import_hourly_bars(hass, PFID, [_bar(10, "1.5", "0.15")])
    await async_wait_recording_done(hass)

    kwh_id = stat_id_consumption(PFID)
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, kwh_id, True, {"sum", "state"}
    )
    assert last[kwh_id][0]["state"] == pytest.approx(1.5)
    assert last[kwh_id][0]["sum"] == pytest.approx(1.5)


async def test_recent_window_upsert_chains_running_sum_with_new_hour(
    recorder_mock, hass: HomeAssistant, freezer
) -> None:
    """After upserting a recent hour to its settled value, a new hour added
    in the same tick must chain running_sum from the corrected base."""
    freezer.move_to("2026-05-21T14:00:00+00:00")

    # Tick 1: h10 partial 0.1
    await async_import_hourly_bars(hass, PFID, [_bar(10, "0.1", "0.01")])
    await async_wait_recording_done(hass)

    # Tick 2: h10 settled to 1.5, h11 new at 1.4
    await async_import_hourly_bars(hass, PFID, [
        _bar(10, "1.5", "0.15"),
        _bar(11, "1.4", "0.14"),
    ])
    await async_wait_recording_done(hass)

    kwh_id = stat_id_consumption(PFID)
    rows_dict = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass, _utc_for(2026, 5, 21, 0), None, {kwh_id}, "hour", None,
        {"start", "state", "sum"},
    )
    rows = rows_dict[kwh_id]
    pairs = [(r["state"], r["sum"]) for r in rows]
    assert pairs == [
        (pytest.approx(1.5), pytest.approx(1.5)),
        (pytest.approx(1.4), pytest.approx(2.9)),
    ]


async def test_settled_history_outside_rewrite_window_is_preserved(
    recorder_mock, hass: HomeAssistant, freezer
) -> None:
    """Bars older than the rewrite window must NOT be overwritten if they're
    already in DB — settled history is trusted."""
    # Freeze at 2026-05-22T14:00 UTC. The bar at 2026-05-19 h10 BST ended at
    # 2026-05-19 10:00 UTC — over 48h ago, way outside the 24h rewrite window.
    freezer.move_to("2026-05-22T14:00:00+00:00")

    old_bar = HourlyBar(
        local_date=date(2026, 5, 19), local_hour=10,
        kwh=Decimal("1.0"), cost_gbp=Decimal("0.1"), is_realised=True,
    )
    await async_import_hourly_bars(hass, PFID, [old_bar])
    await async_wait_recording_done(hass)

    # Try to overwrite with a different value
    new_bar = HourlyBar(
        local_date=date(2026, 5, 19), local_hour=10,
        kwh=Decimal("99.0"), cost_gbp=Decimal("9.9"), is_realised=True,
    )
    await async_import_hourly_bars(hass, PFID, [new_bar])
    await async_wait_recording_done(hass)

    kwh_id = stat_id_consumption(PFID)
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, kwh_id, True, {"sum", "state"}
    )
    assert last[kwh_id][0]["state"] == pytest.approx(1.0)  # original preserved
    assert last[kwh_id][0]["sum"] == pytest.approx(1.0)
