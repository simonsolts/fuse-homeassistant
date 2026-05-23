"""Tests for fuse_energy sensor entities."""
from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant

from custom_components.fuse_energy.api import FuseEnergyApiClient
from custom_components.fuse_energy.coordinator import (
    FuseEnergyDataUpdateCoordinator,
    FuseEnergySnapshot,
)
from custom_components.fuse_energy.sensor import (
    FuseEnergyLastHourCostSensor,
    FuseEnergyLastHourEnergySensor,
)


async def _coord(hass: HomeAssistant, snap: FuseEnergySnapshot | None) -> FuseEnergyDataUpdateCoordinator:
    client = AsyncMock(spec=FuseEnergyApiClient)
    coord = FuseEnergyDataUpdateCoordinator(hass, client, premises_fid="pfid")
    coord.data = snap
    return coord


async def test_energy_sensor_attributes_when_data_present(hass: HomeAssistant) -> None:
    snap = FuseEnergySnapshot(
        last_hour_kwh=0.5,
        last_hour_cost_gbp=0.1,
    )
    coord = await _coord(hass, snap)
    sensor = FuseEnergyLastHourEnergySensor(coord, entry_id="entry-1")

    assert sensor.native_value == 0.5
    assert sensor.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
    assert sensor.device_class == SensorDeviceClass.ENERGY
    assert sensor.state_class is None
    assert sensor.unique_id == "entry-1_last_hour_kwh"
    assert sensor.available is True


async def test_cost_sensor_attributes_when_data_present(hass: HomeAssistant) -> None:
    snap = FuseEnergySnapshot(
        last_hour_kwh=0.5,
        last_hour_cost_gbp=0.1,
    )
    coord = await _coord(hass, snap)
    sensor = FuseEnergyLastHourCostSensor(coord, entry_id="entry-1")

    assert sensor.native_value == 0.1
    assert sensor.native_unit_of_measurement == "GBP"
    assert sensor.device_class == SensorDeviceClass.MONETARY
    assert sensor.state_class is None
    assert sensor.unique_id == "entry-1_last_hour_cost"
    assert sensor.available is True


async def test_sensors_unavailable_when_snapshot_is_none(hass: HomeAssistant) -> None:
    coord = await _coord(hass, None)
    e = FuseEnergyLastHourEnergySensor(coord, entry_id="entry-1")
    c = FuseEnergyLastHourCostSensor(coord, entry_id="entry-1")
    assert e.available is False
    assert c.available is False
    assert e.native_value is None
    assert c.native_value is None


async def test_sensors_unavailable_after_failed_update(hass: HomeAssistant) -> None:
    snap = FuseEnergySnapshot(
        last_hour_kwh=0.5, last_hour_cost_gbp=0.1,
    )
    coord = await _coord(hass, snap)
    coord.last_update_success = False
    e = FuseEnergyLastHourEnergySensor(coord, entry_id="entry-1")
    c = FuseEnergyLastHourCostSensor(coord, entry_id="entry-1")
    assert e.available is False
    assert c.available is False
