import unittest

from custom_components.industrial_alarm_panel.alarm_engine import AlarmEngine
from custom_components.industrial_alarm_panel.alarm_store import InMemoryHistoryStore
from custom_components.industrial_alarm_panel.const import EVENT_ALARMS_UPDATED
from custom_components.industrial_alarm_panel.frontend_events import (
    attach_alarm_update_event_listener,
)


class FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, str]]] = []

    def async_fire(self, event_type: str, event_data: dict[str, str]) -> None:
        self.events.append((event_type, event_data))


class FakeHass:
    def __init__(self) -> None:
        self.bus = FakeBus()


class FrontendEventTests(unittest.TestCase):
    def test_alarm_engine_updates_fire_home_assistant_event(self) -> None:
        hass = FakeHass()
        engine = AlarmEngine([], InMemoryHistoryStore())

        remove_listener = attach_alarm_update_event_listener(hass, "entry-1", engine)

        engine.notify_listeners()

        self.assertEqual(
            hass.bus.events,
            [(EVENT_ALARMS_UPDATED, {"entry_id": "entry-1"})],
        )

        remove_listener()
        engine.notify_listeners()

        self.assertEqual(len(hass.bus.events), 1)


if __name__ == "__main__":
    unittest.main()
