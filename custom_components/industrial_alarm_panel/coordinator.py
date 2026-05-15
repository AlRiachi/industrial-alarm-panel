"""Coordinator helpers for Industrial Alarm Panel."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class AlarmUpdateCoordinator:
    """Lightweight update fan-out used by the alarm engine and entities."""

    def __init__(self) -> None:
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Add a listener and return an unsubscribe callback."""

        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def async_update_listeners(self) -> None:
        """Notify listeners."""

        for listener in list(self._listeners):
            listener()

    def as_dict(self) -> dict[str, Any]:
        """Return diagnostics."""

        return {"listener_count": len(self._listeners)}
