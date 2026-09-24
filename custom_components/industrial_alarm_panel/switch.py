"""Switch entities for Industrial Alarm Panel."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SOUND_MODE_NONE
from .entity_base import IndustrialAlarmPanelEntity
from .runtime import IndustrialAlarmConfigEntry


class SoundEnabledSwitch(IndustrialAlarmPanelEntity, SwitchEntity):
    """Enable or disable audible sound."""

    def __init__(self, runtime: Any) -> None:
        super().__init__(runtime, "sound_enabled", "Sound Enabled")
        self.entity_description = SwitchEntityDescription(
            key="sound_enabled", name="Sound Enabled"
        )
        self._previous_mode = runtime.sound_manager.sound_mode

    @property
    def is_on(self) -> bool:
        """Return switch state."""

        return self.runtime.sound_manager.sound_mode != SOUND_MODE_NONE

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable sound."""

        if self.runtime.sound_manager.sound_mode == SOUND_MODE_NONE:
            self.runtime.sound_manager.sound_mode = self._previous_mode or "browser_only"
        await self.runtime.engine.unsilence_horn(operator="entity")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable sound."""

        self._previous_mode = self.runtime.sound_manager.sound_mode
        self.runtime.sound_manager.sound_mode = SOUND_MODE_NONE
        await self.runtime.engine.silence_horn(operator="entity")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IndustrialAlarmConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities."""

    runtime = entry.runtime_data
    async_add_entities([SoundEnabledSwitch(runtime)])
