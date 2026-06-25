"""Write Fuse hourly bars into Home Assistant's long-term statistics.

Uses the external-statistics API (``async_add_external_statistics``) so
the statistic_ids look like ``fuse_energy:elec_consumption_<pfid>`` and
don't collide with any sensor entity's auto-generated stats.

UTC alignment: Fuse's index hours are Europe/London local. HA's
statistics rows must ``start`` at a UTC hour boundary. We convert per bar.

Recent-window upsert: Fuse's mobile API marks an hour as REALISED the
moment it ends, but the value continues to settle for some hours as the
meter pushes its readings. To handle this, we rewrite the last
``_REWRITE_HOURS`` of stats on every tick (UPSERT semantics) while
preserving older settled history unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
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
    statistics_during_period,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant

from .api import HourlyBar
from .const import DOMAIN, stat_id_consumption, stat_id_cost

_FUSE_TZ = ZoneInfo("Europe/London")

# Bars whose start is within this window of "now" are always re-checked
# (upserted) on every tick, so settled values overwrite earlier partial
# values that Fuse may have returned right after the hour closed.
_REWRITE_HOURS = 24


async def async_import_hourly_bars(
    hass: HomeAssistant,
    premises_fid: str,
    bars: Iterable[HourlyBar],
) -> None:
    """Import realised hourly bars into the kWh and cost statistic series.

    Forecast bars are skipped; they'll be picked up once Fuse re-classifies
    them as REALISED on a subsequent poll.
    """
    bars_list = list(bars)
    realised = [b for b in bars_list if b.is_realised]
    if not realised:
        return

    kwh_stat_id = stat_id_consumption(premises_fid)
    cost_stat_id = stat_id_cost(premises_fid)

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
    now_utc = datetime.now(UTC)
    cutoff_dt = now_utc - timedelta(hours=_REWRITE_HOURS)
    cutoff_ts = cutoff_dt.timestamp()

    sorted_bars = sorted(bars, key=lambda b: (b.local_date, b.local_hour))

    last_query = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )
    last_rows = last_query.get(statistic_id) or []
    if last_rows:
        last_start_ts_in_db = float(last_rows[0]["start"])
        last_sum_in_db = float(last_rows[0]["sum"] or 0.0)
    else:
        last_start_ts_in_db = float("-inf")
        last_sum_in_db = 0.0

    rows: list[StatisticData] = []

    # Phase 1: bars with start < cutoff (older than rewrite window) —
    # append if not already in DB, skip if already present. This handles
    # initial backfill and recovery after extended downtime; values older
    # than the rewrite window are trusted as settled.
    running_sum = last_sum_in_db
    for bar in sorted_bars:
        start_dt = _bar_start_utc(bar)
        start_ts = start_dt.timestamp()
        if start_ts >= cutoff_ts:
            break  # entered Phase 2 zone
        if start_ts <= last_start_ts_in_db:
            continue
        value = float(value_getter(bar))
        running_sum += value
        rows.append(StatisticData(start=start_dt, state=value, sum=running_sum))

    # Phase 2: bars with start >= cutoff (within rewrite window) — always
    # upsert. Running_sum is reset to the cumulative sum at the latest row
    # strictly before the cutoff, so values for hours within the window are
    # rebuilt from scratch on every tick.
    p2_base = await _get_running_sum_before(hass, statistic_id, cutoff_dt)
    running_sum = p2_base
    for bar in sorted_bars:
        start_dt = _bar_start_utc(bar)
        start_ts = start_dt.timestamp()
        if start_ts < cutoff_ts:
            continue
        value = float(value_getter(bar))
        running_sum += value
        rows.append(StatisticData(start=start_dt, state=value, sum=running_sum))

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


async def _get_running_sum_before(
    hass: HomeAssistant,
    statistic_id: str,
    before_dt: datetime,
) -> float:
    """Return the cumulative sum at the latest stats row whose start is
    strictly before ``before_dt``. Returns 0.0 if no such row exists."""
    last_query = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )
    last_rows = last_query.get(statistic_id) or []
    if not last_rows:
        return 0.0
    last_start_ts = float(last_rows[0]["start"])
    if last_start_ts < before_dt.timestamp():
        return float(last_rows[0]["sum"] or 0.0)

    # Latest row is in or after the rewrite window — query for the row
    # immediately before the cutoff using a 7-day lookback (plenty given
    # we re-fetch the last 2 days every tick).
    start_dt = before_dt - timedelta(days=7)
    rows_dict = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start_dt,
        before_dt,
        {statistic_id},
        "hour",
        None,
        {"sum"},
    )
    rows = rows_dict.get(statistic_id, [])
    if not rows:
        return 0.0
    return float(rows[-1].get("sum") or 0.0)


def _bar_start_utc(bar: HourlyBar) -> datetime:
    local = datetime(
        bar.local_date.year,
        bar.local_date.month,
        bar.local_date.day,
        bar.local_hour,
        tzinfo=_FUSE_TZ,
    )
    return local.astimezone(UTC)
