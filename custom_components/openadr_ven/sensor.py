"""Sensor entities for OpenADR VEN integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        DRLevelSensor(coordinator, entry),
        DRSetpointSensor(coordinator, entry),
        DREventIdSensor(coordinator, entry),
    ])


class _DRBaseSensor(SensorEntity):
    """Base class for DR state sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry = entry

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def available(self) -> bool:
        return self._coordinator.data is not None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"OpenADR VEN ({self._entry.data.get('ven_name', '')})",
            "manufacturer": "OpenADR Alliance",
            "model": "Virtual End Node",
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )


class DRLevelSensor(_DRBaseSensor):
    _attr_name = "DR event level"
    _attr_icon = "mdi:transmission-tower"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_dr_level"

    @property
    def native_value(self):
        return self._coordinator.data.get("dr_level")

    @property
    def extra_state_attributes(self):
        return {"event_id": self._coordinator.data.get("event_id")}


class DRSetpointSensor(_DRBaseSensor):
    _attr_name = "DR setpoint"
    _attr_icon = "mdi:solar-power"
    _attr_native_unit_of_measurement = "%"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_dr_setpoint"

    @property
    def native_value(self):
        return self._coordinator.data.get("setpoint_pct")


class DREventIdSensor(_DRBaseSensor):
    _attr_name = "DR event ID"
    _attr_icon = "mdi:identifier"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_dr_event_id"

    @property
    def native_value(self):
        return self._coordinator.data.get("event_id", "none")
