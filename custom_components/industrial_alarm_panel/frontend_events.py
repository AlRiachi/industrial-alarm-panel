"""Frontend update event bridge for the Industrial Alarm Panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .const import EVENT_ALARMS_UPDATED


def attach_alarm_update_event_listener(
    hass: Any, entry_id: str, engine: Any
) -> Callable[[], None]:
    """Fire a Home Assistant event whenever alarm runtime state changes.

    The engine only notifies on material changes, so this event is not fired for
    source readings that leave every alarm unchanged. Event data:

    - ``entry_id``: config entry ID (unchanged contract).
    - ``rule_ids``: IDs of rules whose alarm state or definition changed; an
      empty list means a global change (horn/sound state, bulk refresh).
    """

    def _fire_update_event() -> None:
        hass.bus.async_fire(
            EVENT_ALARMS_UPDATED,
            {
                "entry_id": entry_id,
                "rule_ids": list(getattr(engine, "last_changed_rule_ids", []) or []),
            },
        )

    return engine.add_listener(_fire_update_event)
