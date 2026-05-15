"""Frontend panel registration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENABLE_PANEL,
    CONF_PANEL_TITLE,
    DEFAULT_OPTIONS,
    DOMAIN,
    FRONTEND_MODULE,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL,
)

_LOGGER = logging.getLogger(__name__)


async def async_register_panel(hass: HomeAssistant, entry: ConfigEntry) -> Any | None:
    """Register the custom sidebar panel and static frontend asset path."""

    options = {**DEFAULT_OPTIONS, **entry.data, **entry.options}
    if not options.get(CONF_ENABLE_PANEL, True):
        return None

    dist_path = Path(__file__).parent / "frontend" / "dist"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                f"/{DOMAIN}/frontend/dist",
                str(dist_path),
                cache_headers=True,
            )
        ]
    )

    config = {
        "_panel_custom": {
            "name": "industrial-alarm-panel",
            "module_url": FRONTEND_MODULE,
            "embed_iframe": False,
            "trust_external_script": False,
            "config": {
                "entry_id": entry.entry_id,
                "title": options.get(CONF_PANEL_TITLE, PANEL_TITLE),
            },
        }
    }
    frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=options.get(CONF_PANEL_TITLE, PANEL_TITLE),
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL,
        config=config,
        require_admin=False,
    )

    def remove_panel() -> None:
        remove = getattr(frontend, "async_remove_panel", None)
        if remove:
            remove(hass, PANEL_URL)
        else:
            _LOGGER.debug("Frontend panel removal API not available")

    return remove_panel
