"""Button entities for Industrial Alarm Panel."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .alarm_models import AlarmRule
from .entity_base import IndustrialAlarmPanelEntity, PerAlarmEntity
from .runtime import IndustrialAlarmConfigEntry


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

    def __init__(
        self,
        runtime: Any,
        rule_id: str,
        action_key: str,
        name_template: str,
        action: Any,
    ) -> None:
        name = name_template.format(name=runtime.engine.rules[rule_id].name)
        super().__init__(runtime, rule_id, action_key, name)
        self._name_template = name_template
        self.entity_description = ButtonEntityDescription(key=action_key, name=name)
        self._attr_suggested_object_id = f"industrial_alarm_{action_key}"
        self._action = action

    async def async_press(self) -> None:
        """Handle button press."""

        await self._action(self.rule_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IndustrialAlarmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities."""

    runtime = entry.runtime_data
    engine = runtime.engine

    async def _test_sound() -> None:
        await runtime.sound_manager.test_sound()
        engine.notify_listeners()

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
            _test_sound,
        ),
    ]
    async_add_entities(entities)

    def _rule_entities(rule: AlarmRule) -> list[ButtonEntity]:
        return [
            PerAlarmButton(
                runtime,
                rule.id,
                f"ack_{rule.slug}",
                "Acknowledge {name}",
                lambda rid: engine.acknowledge_alarm(rid, operator="entity"),
            ),
            PerAlarmButton(
                runtime,
                rule.id,
                f"shelve_{rule.slug}",
                "Shelve {name}",
                lambda rid: engine.shelve_alarm(
                    rid, duration_minutes=60, operator="entity"
                ),
            ),
            PerAlarmButton(
                runtime,
                rule.id,
                f"disable_{rule.slug}",
                "Disable {name}",
                lambda rid: engine.disable_alarm(rid, operator="entity"),
            ),
        ]

    # Also adds the current per-rule buttons; later rules are added in place.
    runtime.register_rule_entity_platform(async_add_entities, _rule_entities)
