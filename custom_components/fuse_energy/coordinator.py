"""DataUpdateCoordinator that drives Fuse Energy backfill on every tick."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    FuseEnergyApiAuthError,
    FuseEnergyApiClient,
    FuseEnergyApiError,
    HourlyBar,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, stat_id_consumption
from .statistics import async_import_hourly_bars

_LOGGER = logging.getLogger(__name__)
_FUSE_TZ = ZoneInfo("Europe/London")
_INITIAL_BACKFILL_DAYS = 30


@dataclass(slots=True, frozen=True)
class FuseEnergySnapshot:
    """Sensor-facing view: the most recent realised hour we've seen."""

    last_hour_kwh: float
    last_hour_cost_gbp: float


class FuseEnergyDataUpdateCoordinator(DataUpdateCoordinator[FuseEnergySnapshot | None]):
    """On each tick, fetch + import any new hourly bars since the last imported one."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: FuseEnergyApiClient,
        *,
        premises_fid: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self._client = client
        self._premises_fid = premises_fid

    async def _async_update_data(self) -> FuseEnergySnapshot | None:
        try:
            return await self._do_tick()
        except FuseEnergyApiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FuseEnergyApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _do_tick(self) -> FuseEnergySnapshot | None:
        now_utc = datetime.now(UTC)
        today = now_utc.astimezone(_FUSE_TZ).date()
        last_imported = await _async_last_imported_date(self.hass, self._premises_fid)
        if last_imported is None:
            start = today - timedelta(days=_INITIAL_BACKFILL_DAYS)
        else:
            # Refetch the last imported day so any newly-realised hours arrive.
            start = last_imported
        _LOGGER.warning(
            "[fuse-diag] tick start: today=%s last_imported=%s start=%s",
            today, last_imported, start,
        )

        # Collect all bars across the range and import in a single call so the
        # writer's running_sum stays continuous. Importing per-day races with
        # the recorder's async write queue and resets running_sum at each day
        # boundary, producing big negative bars at midnight in the Energy
        # dashboard.
        all_bars: list[HourlyBar] = []
        day = start
        while day <= today:
            all_bars.extend(
                await self._client.async_fetch_day(self._premises_fid, day)
            )
            day += timedelta(days=1)

        # Fuse's mobile API marks the current (in-progress) hour as REALISED
        # with a growing partial value. If we pass that to the writer the row
        # gets locked at the partial value forever (subsequent ticks skip it
        # via start_ts <= last_start_ts). Only consider bars whose local hour
        # has fully elapsed.
        complete_bars = [b for b in all_bars if _bar_end_utc(b) <= now_utc]

        realised_count = sum(1 for b in complete_bars if b.is_realised)
        _LOGGER.warning(
            "[fuse-diag] collected %d bars total, %d complete, %d realised+complete. "
            "Last 3 realised+complete=%s",
            len(all_bars),
            len(complete_bars),
            realised_count,
            [
                f"{b.local_date} h{b.local_hour:02d} kwh={b.kwh}"
                for b in sorted(
                    (b for b in complete_bars if b.is_realised),
                    key=lambda b: (b.local_date, b.local_hour),
                )[-3:]
            ],
        )

        if complete_bars:
            await async_import_hourly_bars(
                self.hass, self._premises_fid, complete_bars
            )

        latest_realised: HourlyBar | None = None
        for bar in complete_bars:
            if bar.is_realised and (
                latest_realised is None
                or (bar.local_date, bar.local_hour)
                > (latest_realised.local_date, latest_realised.local_hour)
            ):
                latest_realised = bar
        if latest_realised is None:
            _LOGGER.warning("[fuse-diag] no realised bars; keeping previous snapshot")
            return self.data
        _LOGGER.warning(
            "[fuse-diag] latest_realised=%s h%02d kwh=%s cost=%s",
            latest_realised.local_date,
            latest_realised.local_hour,
            latest_realised.kwh,
            latest_realised.cost_gbp,
        )
        return FuseEnergySnapshot(
            last_hour_kwh=float(latest_realised.kwh),
            last_hour_cost_gbp=float(latest_realised.cost_gbp),
        )


def _bar_end_utc(bar: HourlyBar) -> datetime:
    """End of the bar's local hour in UTC. A bar is fully elapsed when this
    is <= now_utc."""
    local_start = datetime(
        bar.local_date.year,
        bar.local_date.month,
        bar.local_date.day,
        bar.local_hour,
        tzinfo=_FUSE_TZ,
    )
    return (local_start + timedelta(hours=1)).astimezone(UTC)


async def _async_last_imported_date(
    hass: HomeAssistant, premises_fid: str
) -> date | None:
    """Return the local-date of the most recent imported consumption hour."""
    statistic_id = stat_id_consumption(premises_fid)
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, set()
    )
    rows = last.get(statistic_id) or []
    if not rows:
        return None
    start_ts = float(rows[0]["start"])
    return datetime.fromtimestamp(start_ts, tz=UTC).astimezone(_FUSE_TZ).date()
