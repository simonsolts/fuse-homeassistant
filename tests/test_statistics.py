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
from custom_components.fuse_energy.const import (
    STAT_ID_CONSUMPTION_TEMPLATE,
    STAT_ID_COST_TEMPLATE,
)
from custom_components.fuse_energy.statistics import async_import_hourly_bars


LDN = ZoneInfo("Europe/London")


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

    await async_import_hourly_bars(hass, "pfid", bars)
    await async_wait_recording_done(hass)

    kwh_id = STAT_ID_CONSUMPTION_TEMPLATE.format(premises_fid="pfid")
    cost_id = STAT_ID_COST_TEMPLATE.format(premises_fid="pfid")

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

    await async_import_hourly_bars(hass, "pfid", bars)
    await async_wait_recording_done(hass)

    kwh_id = STAT_ID_CONSUMPTION_TEMPLATE.format(premises_fid="pfid")
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 5, kwh_id, True, {"sum", "state"}
    )
    assert len(last[kwh_id]) == 1
    assert last[kwh_id][0]["state"] == pytest.approx(0.1)


async def test_resumes_from_last_recorded_sum(
    recorder_mock, hass: HomeAssistant
) -> None:
    await async_import_hourly_bars(hass, "pfid", [_bar(0, "0.5", "0.05")])
    await async_wait_recording_done(hass)

    # Second batch overlaps: hour 0 already stored, hour 1 is new.
    await async_import_hourly_bars(
        hass, "pfid", [_bar(0, "0.5", "0.05"), _bar(1, "0.4", "0.04")]
    )
    await async_wait_recording_done(hass)

    kwh_id = STAT_ID_CONSUMPTION_TEMPLATE.format(premises_fid="pfid")
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 5, kwh_id, True, {"sum"}
    )
    # Two rows total; second sum = 0.5 + 0.4 = 0.9
    sums = sorted(r["sum"] for r in last[kwh_id])
    assert sums == [pytest.approx(0.5), pytest.approx(0.9)]


async def test_empty_bars_is_noop(recorder_mock, hass: HomeAssistant) -> None:
    # Should not raise, not write anything.
    await async_import_hourly_bars(hass, "pfid", [])
    await async_wait_recording_done(hass)

    kwh_id = STAT_ID_CONSUMPTION_TEMPLATE.format(premises_fid="pfid")
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, kwh_id, True, {"sum"}
    )
    assert last == {}
