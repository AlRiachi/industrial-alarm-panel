"""Diagnostics support for Industrial Alarm Panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import VERSION
from .runtime import IndustrialAlarmConfigEntry


def _file_size(path: Path) -> int:
    """Return a file size in bytes (0 if missing); runs in the executor."""

    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: IndustrialAlarmConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    runtime = entry.runtime_data
    history_path = Path(runtime.history_store.path)
    history_db_size = await hass.async_add_executor_job(_file_size, history_path)
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
        "history_db_size": history_db_size,
        "sound": runtime.sound_manager.as_dict(),
        "media_player_ids": list(runtime.sound_manager.media_players),
    }
