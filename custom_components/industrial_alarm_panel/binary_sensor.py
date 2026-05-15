"""Binary sensor entities for Industrial Alarm Panel."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .alarm_models import AlarmLifecycleState
from .const import DOMAIN
from .entity_base import IndustrialAlarmPanelEntity, PerAlarmEntity


class GlobalBinarySensor(IndustrialAlarmPanelEntity, BinarySensorEntity):
    """Global binary alarm status sensor."""

    def __init__(self, runtime: Any, key: str, name: str, value_fn: Any) -> None:
        super().__init__(runtime, key, name)
        self.entity_description = BinarySensorEntityDescription(key=key, name=name)
        self._value_fn = value_fn

    @property
    def is_on(self) -> bool:
        """Return binary sensor state."""

        return bool(self._value_fn())


class AlarmRuleBinarySensor(PerAlarmEntity, BinarySensorEntity):
    """Per-alarm binary sensor."""

    def __init__(self, runtime: Any, rule_id: str) -> None:
        super().__init__(
            runtime,
            rule_id,
            "alarm",
            runtime.engine.rules[rule_id].name,
        )
        self.entity_description = BinarySensorEntityDescription(
            key="alarm", name=runtime.engine.rules[rule_id].name
        )
        self._attr_suggested_object_id = f"industrial_alarm_{self.rule.slug}"

    @property
    def is_on(self) -> bool:
        """Return whether alarm is active."""

        return self.runtime_state.is_active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return DCS alarm attributes."""

        return self.engine.alarm_to_dict(self.rule, self.runtime_state)

    @property
    def available(self) -> bool:
        """Return availability."""

        return self.runtime_state.lifecycle_state not in {
            AlarmLifecycleState.OUT_OF_SERVICE,
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""

    runtime = hass.data[DOMAIN][entry.entry_id]
    engine = runtime.engine
    entities: list[BinarySensorEntity] = [
        GlobalBinarySensor(runtime, "any_active", "Any Active", engine.active_count),
        GlobalBinarySensor(
            runtime,
            "any_unacknowledged",
            "Any Unacknowledged",
            engine.unacknowledged_count,
        ),
        GlobalBinarySensor(
            runtime,
            "horn_active",
            "Horn Active",
            lambda: runtime.sound_manager.horn_active,
        ),
    ]
    entities.extend(AlarmRuleBinarySensor(runtime, rule_id) for rule_id in engine.rules)
    async_add_entities(entities)
