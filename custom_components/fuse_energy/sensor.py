"""Sensor platform for the Fuse Energy integration."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_COST_TOTAL, SENSOR_ENERGY_TOTAL
from .coordinator import FuseEnergyDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FuseEnergyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            FuseEnergyEnergyTotalSensor(coordinator, entry.entry_id),
            FuseEnergyCostTotalSensor(coordinator, entry.entry_id),
        ]
    )


class _FuseEnergyBaseSensor(
    CoordinatorEntity[FuseEnergyDataUpdateCoordinator], SensorEntity
):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FuseEnergyDataUpdateCoordinator,
        entry_id: str,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Fuse Energy",
            manufacturer="Fuse Energy",
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None


class FuseEnergyEnergyTotalSensor(_FuseEnergyBaseSensor):
    _attr_name = "Energy total"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        coordinator: FuseEnergyDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, entry_id, SENSOR_ENERGY_TOTAL)

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.energy_total_kwh


class FuseEnergyCostTotalSensor(_FuseEnergyBaseSensor):
    _attr_name = "Cost total"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "GBP"  # ISO 4217 - HA dashboard accepts

    def __init__(
        self,
        coordinator: FuseEnergyDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, entry_id, SENSOR_COST_TOTAL)

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.cost_total_gbp
