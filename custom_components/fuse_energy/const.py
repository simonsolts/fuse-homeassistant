"""Constants for the Fuse Energy integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN: str = "fuse_energy"

DEFAULT_SCAN_INTERVAL: timedelta = timedelta(minutes=15)

CONF_SESSION_ID: str = "session_id"
CONF_APP_AUTH: str = "app_auth"
CONF_PREMISES_FID: str = "premises_fid"

FUSE_BASE_URL: str = "https://www.fuseenergy.com"
FUSE_TRPC_PATH: str = "/api/trpc"

STAT_ID_CONSUMPTION_TEMPLATE: str = "fuse_energy:elec_consumption_{premises_fid}"
STAT_ID_COST_TEMPLATE: str = "fuse_energy:elec_cost_{premises_fid}"

FALLBACK_APP_VERSION: str = "5.310"

SENSOR_LAST_HOUR_KWH: str = "last_hour_kwh"
SENSOR_LAST_HOUR_COST: str = "last_hour_cost"
