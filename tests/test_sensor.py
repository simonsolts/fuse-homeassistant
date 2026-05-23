"""Tests for fuse_energy sensor entities."""
from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant

from custom_components.fuse_energy.api import FuseEnergyApiClient, FuseEnergyData
from custom_components.fuse_energy.coordinator import (
    FuseEnergyDataUpdateCoordinator,
)
from custom_components.fuse_energy.sensor import (
    FuseEnergyCostTotalSensor,
    FuseEnergyEnergyTotalSensor,
)


async def _make_coordinator(
    hass: HomeAssistant, data: FuseEnergyData | None
) -> FuseEnergyDataUpdateCoordinator:
    client = AsyncMock(spec=FuseEnergyApiClient)
    client.async_get_data.return_value = data
    coordinator = FuseEnergyDataUpdateCoordinator(hass, client)
    coordinator.data = data
    return coordinator


async def test_energy_sensor_attributes_when_data_present(
    hass: HomeAssistant,
) -> None:
    coordinator = await _make_coordinator(
        hass, FuseEnergyData(energy_total_kwh=42.5, cost_total_gbp=9.99)
    )
    sensor = FuseEnergyEnergyTotalSensor(coordinator, entry_id="entry-1")

    assert sensor.native_value == 42.5
    assert sensor.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR
    assert sensor.device_class == SensorDeviceClass.ENERGY
    assert sensor.state_class == SensorStateClass.TOTAL_INCREASING
    assert sensor.unique_id == "entry-1_energy_total"
    assert sensor.available is True


async def test_cost_sensor_attributes_when_data_present(
    hass: HomeAssistant,
) -> None:
    coordinator = await _make_coordinator(
        hass, FuseEnergyData(energy_total_kwh=42.5, cost_total_gbp=9.99)
    )
    sensor = FuseEnergyCostTotalSensor(coordinator, entry_id="entry-1")

    assert sensor.native_value == 9.99
    assert sensor.native_unit_of_measurement == "GBP"
    assert sensor.device_class == SensorDeviceClass.MONETARY
    assert sensor.state_class == SensorStateClass.TOTAL_INCREASING
    assert sensor.unique_id == "entry-1_cost_total"
    assert sensor.available is True


async def test_sensors_unavailable_when_coordinator_data_is_none(
    hass: HomeAssistant,
) -> None:
    coordinator = await _make_coordinator(hass, None)
    energy = FuseEnergyEnergyTotalSensor(coordinator, entry_id="entry-1")
    cost = FuseEnergyCostTotalSensor(coordinator, entry_id="entry-1")

    assert energy.available is False
    assert cost.available is False
    assert energy.native_value is None
    assert cost.native_value is None
