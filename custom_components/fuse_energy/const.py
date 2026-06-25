"""Constants for the Fuse Energy integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN: str = "fuse_energy"

DEFAULT_SCAN_INTERVAL: timedelta = timedelta(minutes=15)

# --- Config entry data keys ---
CONF_PHONE_NUMBER: str = "phone_number"
CONF_DEVICE_ID: str = "device_id"
CONF_ACCESS_TOKEN: str = "access_token"
CONF_REFRESH_TOKEN: str = "refresh_token"
CONF_PREMISES_FID: str = "premises_fid"

# --- API endpoints ---
FUSE_API_BASE_URL: str = "https://api.fuseenergy.com"
FUSE_WEB_BASE_URL: str = "https://www.fuseenergy.com"
# Sent as x-fuse-app-version on the web SMS-dispatch call.
# Bump if that endpoint starts rejecting this value.
FUSE_WEB_APP_VERSION: str = "5.314"


# --- Statistics IDs ---
def _stat_object_id_suffix(premises_fid: str) -> str:
    # HA statistic_id object_ids must match [a-z0-9_]+; UUIDs contain hyphens.
    return premises_fid.replace("-", "_")


def stat_id_consumption(premises_fid: str) -> str:
    return f"{DOMAIN}:elec_consumption_{_stat_object_id_suffix(premises_fid)}"


def stat_id_cost(premises_fid: str) -> str:
    return f"{DOMAIN}:elec_cost_{_stat_object_id_suffix(premises_fid)}"


SENSOR_LAST_HOUR_KWH: str = "last_hour_kwh"
SENSOR_LAST_HOUR_COST: str = "last_hour_cost"
