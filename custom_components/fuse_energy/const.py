"""Constants for the Fuse Energy integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN: str = "fuse_energy"

DEFAULT_SCAN_INTERVAL: timedelta = timedelta(minutes=15)

CONF_ACCESS_TOKEN: str = "access_token"

SENSOR_ENERGY_TOTAL: str = "energy_total"
SENSOR_COST_TOTAL: str = "cost_total"
