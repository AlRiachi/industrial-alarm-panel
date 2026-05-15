"""Select entities for Industrial Alarm Panel."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .alarm_models import AlarmPriority
from .const import DOMAIN
from .entity_base import IndustrialAlarmPanelEntity


class PriorityFilterSelect(IndustrialAlarmPanelEntity, SelectEntity):
    """Frontend priority filter helper entity."""

    _attr_options = ["all"] + [priority.value for priority in AlarmPriority]

    def __init__(self, runtime: Any) -> None:
        super().__init__(runtime, "filter_priority", "Filter Priority")
        self.entity_description = SelectEntityDescription(
            key="filter_priority", name="Filter Priority"
        )
        self._attr_current_option = "all"

    async def async_select_option(self, option: str) -> None:
        """Select priority filter."""

        if option not in self.options:
            raise ValueError(f"Unsupported priority filter: {option}")
        self._attr_current_option = option
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""

    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PriorityFilterSelect(runtime)])
