"""Config flow for Industrial Alarm Panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ENABLE_BROWSER_SOUND,
    CONF_ENABLE_MEDIA_PLAYER_SOUND,
    CONF_ENABLE_PANEL,
    CONF_HISTORY_RETENTION_DAYS,
    CONF_INSTANCE_NAME,
    CONF_MAX_ACTIVE_ALARMS,
    CONF_MAX_HISTORY_ROWS,
    DEFAULT_DATA,
    DOMAIN,
    NAME,
)
from .options_flow import OptionsFlowHandler


class IndustrialAlarmPanelConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Handle a config flow for Industrial Alarm Panel."""

    VERSION = 1
    MINOR_VERSION = 0

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Create the options flow."""

        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get(CONF_INSTANCE_NAME, NAME),
                data={**DEFAULT_DATA, **user_input},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INSTANCE_NAME,
                        default=DEFAULT_DATA[CONF_INSTANCE_NAME],
                    ): str,
                    vol.Optional(
                        CONF_ENABLE_PANEL,
                        default=DEFAULT_DATA[CONF_ENABLE_PANEL],
                    ): bool,
                    vol.Optional(
                        CONF_ENABLE_BROWSER_SOUND,
                        default=DEFAULT_DATA[CONF_ENABLE_BROWSER_SOUND],
                    ): bool,
                    vol.Optional(
                        CONF_ENABLE_MEDIA_PLAYER_SOUND,
                        default=DEFAULT_DATA[CONF_ENABLE_MEDIA_PLAYER_SOUND],
                    ): bool,
                    vol.Optional(
                        CONF_HISTORY_RETENTION_DAYS,
                        default=DEFAULT_DATA[CONF_HISTORY_RETENTION_DAYS],
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=3650)),
                    vol.Optional(
                        CONF_MAX_ACTIVE_ALARMS,
                        default=DEFAULT_DATA[CONF_MAX_ACTIVE_ALARMS],
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=5000)),
                    vol.Optional(
                        CONF_MAX_HISTORY_ROWS,
                        default=DEFAULT_DATA[CONF_MAX_HISTORY_ROWS],
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=50000)),
                }
            ),
            errors={},
        )
