"""Button entities for Industrial Alarm Panel."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity_base import IndustrialAlarmPanelEntity, PerAlarmEntity


class AlarmActionButton(IndustrialAlarmPanelEntity, ButtonEntity):
    """Global action button."""

    def __init__(self, runtime: Any, key: str, name: str, action: Any) -> None:
        super().__init__(runtime, key, name)
        self.entity_description = ButtonEntityDescription(key=key, name=name)
        self._action = action

    async def async_press(self) -> None:
        """Handle button press."""

        await self._action()


class PerAlarmButton(PerAlarmEntity, ButtonEntity):
    """Per-alarm action button."""

    def __init__(self, runtime: Any, rule_id: str, action_key: str, name: str, action: Any) -> None:
        super().__init__(runtime, rule_id, action_key, name)
        self.entity_description = ButtonEntityDescription(key=action_key, name=name)
        self._attr_suggested_object_id = f"industrial_alarm_{action_key}"
        self._action = action

    async def async_press(self) -> None:
        """Handle button press."""

        await self._action(self.rule_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities."""

    runtime = hass.data[DOMAIN][entry.entry_id]
    engine = runtime.engine
    entities: list[ButtonEntity] = [
        AlarmActionButton(
            runtime,
            "acknowledge_all",
            "Acknowledge All",
            lambda: engine.acknowledge_all(operator="entity"),
        ),
        AlarmActionButton(
            runtime,
            "silence_horn",
            "Silence Horn",
            lambda: engine.silence_horn(operator="entity"),
        ),
        AlarmActionButton(
            runtime,
            "unsilence_horn",
            "Unsilence Horn",
            lambda: engine.unsilence_horn(operator="entity"),
        ),
        AlarmActionButton(
            runtime,
            "test_sound",
            "Test Sound",
            runtime.sound_manager.test_sound,
        ),
    ]
    for rule_id, rule in engine.rules.items():
        entities.extend(
            [
                PerAlarmButton(
                    runtime,
                    rule_id,
                    f"ack_{rule.slug}",
                    f"Acknowledge {rule.name}",
                    lambda rid: engine.acknowledge_alarm(rid, operator="entity"),
                ),
                PerAlarmButton(
                    runtime,
                    rule_id,
                    f"shelve_{rule.slug}",
                    f"Shelve {rule.name}",
                    lambda rid: engine.shelve_alarm(
                        rid, duration_minutes=60, operator="entity"
                    ),
                ),
                PerAlarmButton(
                    runtime,
                    rule_id,
                    f"disable_{rule.slug}",
                    f"Disable {rule.name}",
                    lambda rid: engine.disable_alarm(rid, operator="entity"),
                ),
            ]
        )
    async_add_entities(entities)
