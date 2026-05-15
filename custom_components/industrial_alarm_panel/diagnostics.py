"""Diagnostics support for Industrial Alarm Panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    runtime = hass.data[DOMAIN][entry.entry_id]
    history_path = Path(runtime.history_store.path)
    return {
        "entry": {
            "title": entry.title,
            "domain": entry.domain,
            "options": dict(entry.options),
        },
        "integration_version": VERSION,
        "frontend_version": VERSION,
        "rule_count": len(runtime.engine.rules),
        "active_alarm_count": runtime.engine.active_count(),
        "unacknowledged_alarm_count": runtime.engine.unacknowledged_count(),
        "history_db_size": history_path.stat().st_size if history_path.exists() else 0,
        "sound": runtime.sound_manager.as_dict(),
        "media_player_ids": list(runtime.sound_manager.media_players),
    }
