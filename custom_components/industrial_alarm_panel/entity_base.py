"""Entity helpers for Industrial Alarm Panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN, NAME


class IndustrialAlarmPanelEntity(Entity):
    """Base entity tied to the alarm engine."""

    _attr_has_entity_name = True

    def __init__(self, runtime: Any, key: str, name: str) -> None:
        self.runtime = runtime
        self.engine = runtime.engine
        self._attr_unique_id = f"{DOMAIN}_{runtime.entry_id}_{key}"
        self._attr_suggested_object_id = f"industrial_alarm_{key}"
        self._attr_translation_key = key
        self._attr_name = name
        self._remove_listener: Callable[[], None] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for grouping entities."""

        return DeviceInfo(
            identifiers={(DOMAIN, self.runtime.entry_id)},
            name=NAME,
            manufacturer="Industrial Alarm Panel",
            model="DCS Alarm Annunciator",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to alarm engine updates."""

        self._remove_listener = self.engine.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from alarm engine updates."""

        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None


class PerAlarmEntity(IndustrialAlarmPanelEntity):
    """Base entity for one alarm rule."""

    def __init__(self, runtime: Any, rule_id: str, key: str, name: str) -> None:
        self.rule_id = rule_id
        super().__init__(runtime, f"{key}_{rule_id}", name)

    @property
    def rule(self) -> Any:
        """Return the entity's alarm rule."""

        return self.engine.rules[self.rule_id]

    @property
    def runtime_state(self) -> Any:
        """Return the entity's runtime state."""

        return self.engine.states[self.rule_id]
