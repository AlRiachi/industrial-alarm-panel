import unittest
from datetime import UTC, datetime, timedelta

from custom_components.industrial_alarm_panel.alarm_engine import AlarmEngine
from custom_components.industrial_alarm_panel.alarm_models import (
    AlarmLifecycleState,
    AlarmRule,
)
from custom_components.industrial_alarm_panel.alarm_store import InMemoryHistoryStore


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class AlarmEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.clock = Clock()
        self.history = InMemoryHistoryStore()

    async def test_numeric_alarm_uses_deadband_for_clear(self) -> None:
        rule = AlarmRule.from_dict(
            {
                "id": "temp_high",
                "entity_id": "sensor.temp",
                "name": "Temperature High",
                "condition": "above",
                "threshold": 75,
                "deadband": 2,
                "priority": "critical",
            }
        )
        engine = AlarmEngine([rule], self.history, now=self.clock.now)

        await engine.process_state("sensor.temp", "76")
        self.assertEqual(
            engine.get_alarm("temp_high").lifecycle_state,
            AlarmLifecycleState.ACTIVE_UNACK,
        )

        await engine.process_state("sensor.temp", "74")
        self.assertEqual(
            engine.get_alarm("temp_high").lifecycle_state,
            AlarmLifecycleState.ACTIVE_UNACK,
        )

        await engine.process_state("sensor.temp", "72.9")
        self.assertEqual(
            engine.get_alarm("temp_high").lifecycle_state,
            AlarmLifecycleState.CLEARED_UNACK,
        )

    async def test_ack_and_clear_lifecycle_transitions_match_dcs_rules(self) -> None:
        rule = AlarmRule.from_dict(
            {
                "id": "pump_fault",
                "entity_id": "binary_sensor.pump_fault",
                "name": "Pump Fault",
                "condition": "is_on",
                "priority": "high",
            }
        )
        engine = AlarmEngine([rule], self.history, now=self.clock.now)

        await engine.process_state("binary_sensor.pump_fault", "on")
        await engine.acknowledge_alarm("pump_fault", operator="operator-a")
        self.assertEqual(
            engine.get_alarm("pump_fault").lifecycle_state,
            AlarmLifecycleState.ACTIVE_ACK,
        )

        await engine.process_state("binary_sensor.pump_fault", "off")
        self.assertEqual(
            engine.get_alarm("pump_fault").lifecycle_state,
            AlarmLifecycleState.CLEARED_ACK,
        )

    async def test_shelved_alarm_does_not_activate_until_unshelved(self) -> None:
        rule = AlarmRule.from_dict(
            {
                "id": "manual",
                "entity_id": "binary_sensor.manual",
                "name": "Manual",
                "condition": "is_on",
                "priority": "medium",
            }
        )
        engine = AlarmEngine([rule], self.history, now=self.clock.now)

        await engine.shelve_alarm("manual", duration_minutes=10)
        await engine.process_state("binary_sensor.manual", "on")
        self.assertEqual(
            engine.get_alarm("manual").lifecycle_state,
            AlarmLifecycleState.SHELVED,
        )

        await engine.unshelve_alarm("manual")
        await engine.process_state("binary_sensor.manual", "on")
        self.assertEqual(
            engine.get_alarm("manual").lifecycle_state,
            AlarmLifecycleState.ACTIVE_UNACK,
        )

    async def test_deleting_rule_does_not_notify_removed_per_alarm_entities(self) -> None:
        rule = AlarmRule.from_dict(
            {
                "id": "delete_me",
                "entity_id": "binary_sensor.delete_me",
                "name": "Delete Me",
                "condition": "is_on",
                "priority": "low",
            }
        )
        engine = AlarmEngine([rule], self.history, now=self.clock.now)
        notifications = 0

        def removed_entity_listener() -> None:
            nonlocal notifications
            notifications += 1
            engine.get_alarm("delete_me")

        engine.add_listener(removed_entity_listener)

        await engine.delete_rule("delete_me")

        self.assertNotIn("delete_me", engine.rules)
        self.assertNotIn("delete_me", engine.states)
        self.assertEqual(notifications, 0)

    async def test_engine_can_notify_entities_after_external_sound_state_change(self) -> None:
        engine = AlarmEngine([], self.history, now=self.clock.now)
        notifications = 0

        def listener() -> None:
            nonlocal notifications
            notifications += 1

        engine.add_listener(listener)

        engine.notify_listeners()

        self.assertEqual(notifications, 1)


if __name__ == "__main__":
    unittest.main()
