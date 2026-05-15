"""Sensor entities for Industrial Alarm Panel."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .alarm_models import AlarmPriority
from .const import DOMAIN
from .entity_base import IndustrialAlarmPanelEntity


class CountSensor(IndustrialAlarmPanelEntity, SensorEntity):
    """Alarm count sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        runtime: Any,
        key: str,
        name: str,
        value_fn: Any,
    ) -> None:
        super().__init__(runtime, key, name)
        self.entity_description = SensorEntityDescription(key=key, name=name)
        self._value_fn = value_fn

    @property
    def native_value(self) -> int:
        """Return sensor value."""

        return int(self._value_fn())


class TextSensor(IndustrialAlarmPanelEntity, SensorEntity):
    """Text status sensor."""

    def __init__(self, runtime: Any, key: str, name: str, value_fn: Any) -> None:
        super().__init__(runtime, key, name)
        self.entity_description = SensorEntityDescription(key=key, name=name)
        self._value_fn = value_fn

    @property
    def native_value(self) -> str | None:
        """Return sensor value."""

        value = self._value_fn()
        if isinstance(value, dict):
            return value.get("name") or value.get("id")
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return full object attributes."""

        value = self._value_fn()
        return value if isinstance(value, dict) else {}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""

    runtime = hass.data[DOMAIN][entry.entry_id]
    engine = runtime.engine
    async_add_entities(
        [
            CountSensor(runtime, "active_count", "Active Count", engine.active_count),
            CountSensor(
                runtime,
                "unacknowledged_count",
                "Unacknowledged Count",
                engine.unacknowledged_count,
            ),
            CountSensor(
                runtime,
                "critical_count",
                "Critical Count",
                lambda: engine.priority_count(AlarmPriority.CRITICAL),
            ),
            CountSensor(
                runtime,
                "high_count",
                "High Count",
                lambda: engine.priority_count(AlarmPriority.HIGH),
            ),
            TextSensor(runtime, "last_alarm", "Last Alarm", engine.last_alarm),
            TextSensor(
                runtime,
                "last_event",
                "Last Event",
                lambda: engine.last_event.to_dict() if engine.last_event else None,
            ),
        ]
    )
