import unittest

from custom_components.industrial_alarm_panel.alarm_engine import AlarmEngine
from custom_components.industrial_alarm_panel.alarm_models import (
    AlarmRule,
    AlarmValidationError,
)
from custom_components.industrial_alarm_panel.alarm_store import InMemoryHistoryStore
from custom_components.industrial_alarm_panel.rule_management import (
    delete_rules,
    is_generated_rule_id,
    matching_per_rule_entity_entries,
    per_rule_entity_unique_ids,
    select_suggested_rules,
)


class FakeRegistryEntry:
    def __init__(self, entity_id: str, unique_id: str, config_entry_id: str) -> None:
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.config_entry_id = config_entry_id


class FakeEngine:
    def __init__(self, rules: list[AlarmRule]) -> None:
        self.rules = {rule.id: rule for rule in rules}
        self.delete_rule_calls: list[str] = []

    async def delete_rule(self, rule_id: str) -> None:
        self.delete_rule_calls.append(rule_id)
        self.rules.pop(rule_id)


def make_rule(rule_id: str, entity_id: str = "sensor.source") -> AlarmRule:
    return AlarmRule.from_dict(
        {
            "id": rule_id,
            "entity_id": entity_id,
            "name": rule_id.replace("_", " ").title(),
            "condition": "above",
            "threshold": 10,
            "priority": "medium",
        }
    )


class RuleManagementTests(unittest.IsolatedAsyncioTestCase):
    def test_generated_rule_ids_use_auto_prefix(self) -> None:
        self.assertTrue(is_generated_rule_id("auto_sensor_main_power_unavailable"))
        self.assertFalse(is_generated_rule_id("manual_temperature_high"))

    def test_select_suggested_rules_keeps_requested_order_and_reports_skips(self) -> None:
        suggested = [
            {"id": "auto_a", "name": "A"},
            {"id": "auto_b", "name": "B"},
            {"id": "auto_c", "name": "C"},
        ]

        selected, skipped = select_suggested_rules(
            suggested, ["auto_c", "missing", "auto_a", "auto_c"]
        )

        self.assertEqual([rule["id"] for rule in selected], ["auto_c", "auto_a"])
        self.assertEqual(skipped, ["missing"])

    def test_select_suggested_rules_omitted_ids_preserves_all_suggestions(self) -> None:
        suggested = [{"id": "auto_a"}, {"id": "auto_b"}]

        selected, skipped = select_suggested_rules(suggested, None)

        self.assertEqual(selected, suggested)
        self.assertEqual(skipped, [])

    async def test_delete_generated_only_removes_only_auto_rules(self) -> None:
        engine = AlarmEngine(
            [
                make_rule("auto_sensor_power_high_consumption"),
                make_rule("manual_temperature_high"),
            ],
            InMemoryHistoryStore(),
        )

        result = await delete_rules(engine, generated_only=True)

        self.assertEqual(result.deleted_rule_ids, ["auto_sensor_power_high_consumption"])
        self.assertEqual(result.skipped_rule_ids, [])
        self.assertNotIn("auto_sensor_power_high_consumption", engine.rules)
        self.assertIn("manual_temperature_high", engine.rules)

    async def test_delete_generated_only_with_explicit_ids_skips_non_generated(
        self,
    ) -> None:
        engine = AlarmEngine(
            [make_rule("auto_a"), make_rule("auto_b"), make_rule("manual_c")],
            InMemoryHistoryStore(),
        )

        result = await delete_rules(
            engine,
            rule_ids=["auto_b", "manual_c", "missing"],
            generated_only=True,
        )

        self.assertEqual(result.deleted_rule_ids, ["auto_b"])
        self.assertEqual(result.skipped_rule_ids, ["manual_c", "missing"])
        self.assertIn("auto_a", engine.rules)
        self.assertNotIn("auto_b", engine.rules)
        self.assertIn("manual_c", engine.rules)

    async def test_delete_explicit_rules_skips_unknown_ids(self) -> None:
        engine = AlarmEngine(
            [make_rule("rule_a"), make_rule("rule_b")], InMemoryHistoryStore()
        )

        result = await delete_rules(engine, rule_ids=["missing", "rule_b"])

        self.assertEqual(result.deleted_rule_ids, ["rule_b"])
        self.assertEqual(result.skipped_rule_ids, ["missing"])
        self.assertIn("rule_a", engine.rules)
        self.assertNotIn("rule_b", engine.rules)

    async def test_delete_rules_delegates_to_engine_delete_rule(self) -> None:
        engine = FakeEngine([make_rule("rule_a"), make_rule("rule_b")])

        result = await delete_rules(engine, rule_ids=["rule_b"])

        self.assertEqual(engine.delete_rule_calls, ["rule_b"])
        self.assertEqual(result.deleted_rule_ids, ["rule_b"])
        self.assertIn("rule_a", engine.rules)
        self.assertNotIn("rule_b", engine.rules)

    async def test_delete_requires_explicit_ids_or_generated_only(self) -> None:
        engine = AlarmEngine([], InMemoryHistoryStore())

        with self.assertRaises(AlarmValidationError):
            await delete_rules(engine)

    def test_per_rule_entity_unique_ids_match_existing_entity_classes(self) -> None:
        rule = make_rule("auto_sensor_powertag_main_power_high_consumption")

        self.assertEqual(
            per_rule_entity_unique_ids("entry-1", rule),
            {
                "industrial_alarm_panel_entry-1_alarm_auto_sensor_powertag_main_power_high_consumption",
                "industrial_alarm_panel_entry-1_ack_auto_sensor_powertag_main_power_high_consumption_auto_sensor_powertag_main_power_high_consumption",
                "industrial_alarm_panel_entry-1_shelve_auto_sensor_powertag_main_power_high_consumption_auto_sensor_powertag_main_power_high_consumption",
                "industrial_alarm_panel_entry-1_disable_auto_sensor_powertag_main_power_high_consumption_auto_sensor_powertag_main_power_high_consumption",
            },
        )

    def test_matching_registry_entries_returns_only_current_entry_per_rule_entities(
        self,
    ) -> None:
        rule = make_rule("auto_sensor_power_high_consumption")
        expected_unique_id = (
            "industrial_alarm_panel_entry-1_alarm_auto_sensor_power_high_consumption"
        )
        entries = [
            FakeRegistryEntry("binary_sensor.match", expected_unique_id, "entry-1"),
            FakeRegistryEntry("binary_sensor.other_entry", expected_unique_id, "entry-2"),
            FakeRegistryEntry("sensor.source", "sensor.source_unique", "entry-1"),
        ]

        matches = matching_per_rule_entity_entries("entry-1", [rule], entries)

        self.assertEqual([entry.entity_id for entry in matches], ["binary_sensor.match"])


if __name__ == "__main__":
    unittest.main()
