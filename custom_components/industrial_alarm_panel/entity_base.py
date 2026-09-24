"""Entity helpers for Industrial Alarm Panel."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN, NAME


class IndustrialAlarmPanelEntity(Entity):
    """Base entity tied to the alarm engine.

    Global entities are written only when the engine commits a real change.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime: Any, key: str, name: str) -> None:
        self.runtime = runtime
        self.engine = runtime.engine
        self._attr_unique_id = f"{DOMAIN}_{runtime.entry_id}_{key}"
        self._attr_suggested_object_id = f"industrial_alarm_{key}"
        self._attr_translation_key = key
        self._attr_name = name

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

        self.async_on_remove(self.engine.add_listener(self.async_write_ha_state))


class PerAlarmEntity(IndustrialAlarmPanelEntity):
    """Base entity for one alarm rule.

    Subscribes only to changes of its own rule, so a change on one alarm does
    not rewrite the state of every per-alarm entity.
    """

    #: Display name template; ``{name}`` is the rule's current name.
    _name_template = "{name}"

    def __init__(self, runtime: Any, rule_id: str, key: str, name: str) -> None:
        self.rule_id = rule_id
        super().__init__(runtime, f"{key}_{rule_id}", name)

    @property
    def rule(self) -> Any:
        """Return the entity's alarm rule (None once deleted)."""

        return self.engine.rules.get(self.rule_id)

    @property
    def runtime_state(self) -> Any:
        """Return the entity's runtime state (None once deleted)."""

        return self.engine.states.get(self.rule_id)

    @property
    def available(self) -> bool:
        """Return False once the rule was deleted."""

        return self.rule is not None and self.runtime_state is not None

    async def async_added_to_hass(self) -> None:
        """Subscribe to this rule's updates only."""

        self.async_on_remove(
            self.engine.add_rule_listener(self.rule_id, self._handle_rule_update)
        )

    @callback
    def _handle_rule_update(self) -> None:
        rule = self.rule
        if rule is not None:
            self._attr_name = self._name_template.format(name=rule.name)
        self.async_write_ha_state()
