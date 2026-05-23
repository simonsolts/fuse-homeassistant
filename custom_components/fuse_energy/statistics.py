"""Write Fuse hourly bars into Home Assistant's long-term statistics.

Uses the external-statistics API (``async_add_external_statistics``) so
the statistic_ids look like ``fuse_energy:elec_consumption_<pfid>`` and
don't collide with any sensor entity's auto-generated stats.

UTC alignment: Fuse's index hours are Europe/London local. HA's
statistics rows must ``start`` at a UTC hour boundary. We convert per bar.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant

from .api import HourlyBar
from .const import (
    DOMAIN,
    STAT_ID_CONSUMPTION_TEMPLATE,
    STAT_ID_COST_TEMPLATE,
)

_FUSE_TZ = ZoneInfo("Europe/London")


async def async_import_hourly_bars(
    hass: HomeAssistant,
    premises_fid: str,
    bars: Iterable[HourlyBar],
) -> None:
    """Import realised hourly bars into the kWh and cost statistic series.

    Forecast bars are skipped; they'll be picked up once Fuse re-classifies
    them as REALISED on a subsequent poll.
    """
    realised = [b for b in bars if b.is_realised]
    if not realised:
        return

    kwh_stat_id = STAT_ID_CONSUMPTION_TEMPLATE.format(premises_fid=premises_fid)
    cost_stat_id = STAT_ID_COST_TEMPLATE.format(premises_fid=premises_fid)

    await _import_series(
        hass,
        statistic_id=kwh_stat_id,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        name=f"Fuse Energy electricity consumption ({premises_fid})",
        bars=realised,
        value_getter=lambda b: b.kwh,
    )
    await _import_series(
        hass,
        statistic_id=cost_stat_id,
        unit="GBP",
        name=f"Fuse Energy electricity cost ({premises_fid})",
        bars=realised,
        value_getter=lambda b: b.cost_gbp,
    )


async def _import_series(
    hass: HomeAssistant,
    *,
    statistic_id: str,
    unit: str,
    name: str,
    bars: list[HourlyBar],
    value_getter: Callable[[HourlyBar], Decimal],
) -> None:
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )
    last_rows = last.get(statistic_id) or []
    if last_rows:
        last_start_ts = float(last_rows[0]["start"])
        running_sum = float(last_rows[0]["sum"] or 0.0)
    else:
        last_start_ts = float("-inf")
        running_sum = 0.0

    rows: list[StatisticData] = []
    for bar in sorted(bars, key=lambda b: (b.local_date, b.local_hour)):
        start = _bar_start_utc(bar)
        if start.timestamp() <= last_start_ts:
            continue
        value = float(value_getter(bar))
        running_sum += value
        rows.append(
            StatisticData(start=start, state=value, sum=running_sum)
        )

    if not rows:
        return

    metadata: StatisticMetaData = {
        "has_mean": False,
        "has_sum": True,
        "name": name,
        "source": DOMAIN,
        "statistic_id": statistic_id,
        "unit_of_measurement": unit,
    }
    async_add_external_statistics(hass, metadata, rows)


def _bar_start_utc(bar: HourlyBar) -> datetime:
    local = datetime(
        bar.local_date.year,
        bar.local_date.month,
        bar.local_date.day,
        bar.local_hour,
        tzinfo=_FUSE_TZ,
    )
    return local.astimezone(UTC)


