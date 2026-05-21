import unittest
from datetime import UTC, datetime, timedelta

from custom_components.industrial_alarm_panel.alarm_models import (
    AlarmPriority,
    AlarmRule,
    AlarmRuntimeState,
    AlarmValidationError,
)


class AlarmModelTests(unittest.TestCase):
    def test_alarm_rule_parses_required_fields_and_defaults(self) -> None:
        rule = AlarmRule.from_dict(
            {
                "id": "inverter_high_temp",
                "entity_id": "sensor.inverter_temperature",
                "name": "Inverter High Temperature",
                "condition": "above",
                "threshold": 75,
                "priority": "critical",
            }
        )

        self.assertEqual(rule.id, "inverter_high_temp")
        self.assertEqual(rule.priority, AlarmPriority.CRITICAL)
        self.assertTrue(rule.enabled)
        self.assertTrue(rule.requires_ack)
        self.assertTrue(rule.audible)
        self.assertEqual(rule.slug, "inverter_high_temp")

    def test_alarm_rule_rejects_invalid_priority(self) -> None:
        with self.assertRaisesRegex(AlarmValidationError, "priority"):
            AlarmRule.from_dict(
                {
                    "id": "bad",
                    "entity_id": "sensor.value",
                    "name": "Bad Rule",
                    "condition": "above",
                    "threshold": 10,
                    "priority": "urgent",
                }
            )

    def test_alarm_rule_requires_threshold_for_numeric_conditions(self) -> None:
        with self.assertRaisesRegex(AlarmValidationError, "threshold"):
            AlarmRule.from_dict(
                {
                    "id": "missing_threshold",
                    "entity_id": "sensor.value",
                    "name": "Missing Threshold",
                    "condition": "above",
                }
            )

    def test_runtime_state_round_trips_pending_transition_timestamps(self) -> None:
        pending_active = datetime(2026, 1, 1, tzinfo=UTC)
        pending_clear = pending_active + timedelta(seconds=5)
        state = AlarmRuntimeState(
            rule_id="pump_fault",
            pending_active_since=pending_active,
            pending_clear_since=pending_clear,
        )

        loaded = AlarmRuntimeState.from_dict(state.to_dict())

        self.assertEqual(loaded.pending_active_since, pending_active)
        self.assertEqual(loaded.pending_clear_since, pending_clear)


if __name__ == "__main__":
    unittest.main()
