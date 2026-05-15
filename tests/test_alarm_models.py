import unittest

from custom_components.industrial_alarm_panel.alarm_models import (
    AlarmPriority,
    AlarmRule,
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


if __name__ == "__main__":
    unittest.main()
