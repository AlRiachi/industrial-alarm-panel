"""Frontend update event bridge for the Industrial Alarm Panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .const import EVENT_ALARMS_UPDATED


def attach_alarm_update_event_listener(
    hass: Any, entry_id: str, engine: Any
) -> Callable[[], None]:
    """Fire a Home Assistant event whenever alarm runtime state changes."""

    def _fire_update_event() -> None:
        hass.bus.async_fire(EVENT_ALARMS_UPDATED, {"entry_id": entry_id})

    return engine.add_listener(_fire_update_event)
