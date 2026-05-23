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

def _stat_object_id_suffix(premises_fid: str) -> str:
    # HA statistic_id object_ids must match [a-z0-9_]+; UUIDs contain hyphens.
    return premises_fid.replace("-", "_")


def stat_id_consumption(premises_fid: str) -> str:
    return f"{DOMAIN}:elec_consumption_{_stat_object_id_suffix(premises_fid)}"


def stat_id_cost(premises_fid: str) -> str:
    return f"{DOMAIN}:elec_cost_{_stat_object_id_suffix(premises_fid)}"

FALLBACK_APP_VERSION: str = "5.310"

SENSOR_LAST_HOUR_KWH: str = "last_hour_kwh"
SENSOR_LAST_HOUR_COST: str = "last_hour_cost"
