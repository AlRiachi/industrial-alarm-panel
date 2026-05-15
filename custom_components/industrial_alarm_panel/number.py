"""Number entities for Industrial Alarm Panel."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HISTORY_RETENTION_DAYS, DEFAULT_OPTIONS, DOMAIN
from .entity_base import IndustrialAlarmPanelEntity


class RetentionDaysNumber(IndustrialAlarmPanelEntity, NumberEntity):
    """History retention number entity."""

    _attr_native_min_value = 1
    _attr_native_max_value = 3650
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.DAYS

    def __init__(self, runtime: Any, entry: ConfigEntry) -> None:
        super().__init__(runtime, "history_retention_days", "History Retention Days")
        self.entry = entry
        self.entity_description = NumberEntityDescription(
            key="history_retention_days",
            name="History Retention Days",
            native_unit_of_measurement=UnitOfTime.DAYS,
        )

    @property
    def native_value(self) -> int:
        """Return current retention days."""

        return int(
            self.entry.options.get(
                CONF_HISTORY_RETENTION_DAYS,
                self.entry.data.get(
                    CONF_HISTORY_RETENTION_DAYS,
                    DEFAULT_OPTIONS[CONF_HISTORY_RETENTION_DAYS],
                ),
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Update retention setting."""

        options = dict(self.entry.options)
        options[CONF_HISTORY_RETENTION_DAYS] = int(value)
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await self.hass.config_entries.async_reload(self.entry.entry_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities."""

    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RetentionDaysNumber(runtime, entry)])
