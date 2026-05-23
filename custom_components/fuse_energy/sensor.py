"""Sensor platform for the Fuse Energy integration.

Both sensors omit ``state_class`` on purpose. The long-term hourly
statistics that show up on the Energy dashboard / Statistics card come
from the writer in ``statistics.py`` — not from these entities — so we
don't want HA to auto-generate statistics from these display sensors.
HA also rejects ``MEASUREMENT`` paired with the ``energy`` /
``monetary`` device classes.
"""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_LAST_HOUR_COST, SENSOR_LAST_HOUR_KWH
from .coordinator import FuseEnergyDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FuseEnergyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            FuseEnergyLastHourEnergySensor(coordinator, entry.entry_id),
            FuseEnergyLastHourCostSensor(coordinator, entry.entry_id),
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


class FuseEnergyLastHourEnergySensor(_FuseEnergyBaseSensor):
    _attr_name = "Last hour energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(
        self,
        coordinator: FuseEnergyDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, entry_id, SENSOR_LAST_HOUR_KWH)

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.last_hour_kwh


class FuseEnergyLastHourCostSensor(_FuseEnergyBaseSensor):
    _attr_name = "Last hour cost"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "GBP"

    def __init__(
        self,
        coordinator: FuseEnergyDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, entry_id, SENSOR_LAST_HOUR_COST)

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.last_hour_cost_gbp
