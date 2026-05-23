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
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STAT_ID_CONSUMPTION_TEMPLATE,
)
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
        today = datetime.now(_FUSE_TZ).date()
        last_imported = await _async_last_imported_date(self.hass, self._premises_fid)
        if last_imported is None:
            start = today - timedelta(days=_INITIAL_BACKFILL_DAYS)
        else:
            # Refetch the last imported day so any newly-realised hours arrive.
            start = last_imported

        latest_realised: HourlyBar | None = None
        day = start
        while day <= today:
            bars = await self._client.async_fetch_day(day)
            if bars:
                await async_import_hourly_bars(self.hass, self._premises_fid, bars)
                for bar in bars:
                    if bar.is_realised and (
                        latest_realised is None
                        or (bar.local_date, bar.local_hour)
                        > (latest_realised.local_date, latest_realised.local_hour)
                    ):
                        latest_realised = bar
            day += timedelta(days=1)
        if latest_realised is None:
            return self.data
        return FuseEnergySnapshot(
            last_hour_kwh=float(latest_realised.kwh),
            last_hour_cost_gbp=float(latest_realised.cost_gbp),
        )


async def _async_last_imported_date(
    hass: HomeAssistant, premises_fid: str
) -> date | None:
    """Return the local-date of the most recent imported consumption hour."""
    statistic_id = STAT_ID_CONSUMPTION_TEMPLATE.format(premises_fid=premises_fid)
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, set()
    )
    rows = last.get(statistic_id) or []
    if not rows:
        return None
    start_ts = float(rows[0]["start"])
    return datetime.fromtimestamp(start_ts, tz=UTC).astimezone(_FUSE_TZ).date()
