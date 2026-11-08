import json
import re
import tomllib
import unittest
from pathlib import Path


class StaticHomeAssistantCompatibilityTests(unittest.TestCase):
    def test_options_flow_does_not_assign_read_only_config_entry_property(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/options_flow.py"
        ).read_text()

        self.assertNotIn("self.config_entry =", source)

    def test_options_flow_uses_supported_voluptuous_list_validator(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/options_flow.py"
        ).read_text()

        self.assertNotIn("vol.EnsureList", source)

    def test_frontend_registers_panel_custom_element_name(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn('customElements.define("industrial-alarm-panel"', source)

    def test_frontend_registration_is_safe_to_import_more_than_once(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn('customElements.get("industrial-alarm-panel")', source)

    def test_panel_registration_uses_home_assistant_panel_custom_api(self) -> None:
        source = Path("custom_components/industrial_alarm_panel/alarm_panel.py").read_text()

        self.assertIn("from homeassistant.components import panel_custom", source)
        self.assertIn("await panel_custom.async_register_panel(", source)
        self.assertIn("trust_external=False", source)
        self.assertNotIn('"trust_external_script"', source)

    def test_frontend_module_url_is_versioned_for_browser_cache_busting(self) -> None:
        source = Path("custom_components/industrial_alarm_panel/const.py").read_text()

        self.assertIn("?v={VERSION}", source)

    def test_integration_schedules_due_alarm_timing_transitions(self) -> None:
        source = Path("custom_components/industrial_alarm_panel/__init__.py").read_text()

        self.assertIn("async_call_later", source)
        self.assertIn("next_due_transition_at", source)
        self.assertIn("process_due_transitions", source)
        self.assertIn("remove_delay_timer", source)

    def _panel_source(self) -> str:
        return Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

    def test_frontend_subscribes_to_alarm_update_events(self) -> None:
        source = self._panel_source()

        self.assertIn("subscribeEvents", source)
        self.assertIn("industrial_alarm_panel_alarms_updated", source)
        self.assertIn("_unsubscribe", source)
        self.assertIn("disconnectedCallback", source)

    def test_frontend_coalesces_reloads_and_loads_in_parallel(self) -> None:
        source = self._panel_source()

        self.assertIn("_scheduleLoad", source)
        self.assertIn("_loadPending", source)
        self.assertIn("Promise.all([", source)

    def test_frontend_codes_priority_by_shape_number_and_colour(self) -> None:
        source = self._panel_source()

        for priority in ("critical", "high", "medium", "low", "info", "status"):
            self.assertIn(f'{priority}: {{ n: ', source)
        self.assertIn("function glyph(", source)
        for mode in ("filled", "hollow", "struck", "dashed"):
            self.assertIn(f'"{mode}"', source)

    def test_frontend_flashes_only_unacknowledged_and_respects_reduced_motion(self) -> None:
        source = self._panel_source()

        self.assertIn(".row.unack .g.m-filled .shape { animation:", source)
        self.assertIn("@keyframes iap-unlit", source)
        self.assertNotIn("brightness(.35)", source)
        self.assertIn("prefers-reduced-motion: reduce", source)
        self.assertIn("--iap-flash: 1s", source)

    def test_frontend_does_not_rerender_whole_panel_on_input(self) -> None:
        source = self._panel_source()

        # The shell is built once; search typing only re-renders the alarm list.
        self.assertEqual(1, source.count("this.shadowRoot.innerHTML ="))
        self.assertIn('input === "alarm-search"', source)
        self.assertIn("_renderStack();", source)

    def test_frontend_escapes_user_text(self) -> None:
        source = self._panel_source()

        self.assertIn("function escapeHtml(", source)
        self.assertIn("escapeHtml(alarm.name)", source)
        self.assertIn("escapeHtml(rule.name)", source)

    def test_frontend_horn_has_its_own_cadence(self) -> None:
        source = self._panel_source()

        hass_setter = source[source.index("set hass(hass)"):source.index("get hass()")]
        self.assertNotIn("Horn", hass_setter)
        self.assertIn("_browserHornIntervalMs = 2000", source)
        self.assertIn("_syncHorn", source)
        self.assertIn("_stopHornLoop", source)

    def test_frontend_delays_new_alarm_colour(self) -> None:
        source = self._panel_source()

        self.assertIn("_alarmVisualDelayMs = 2000", source)
        self.assertIn("_isPendingColour", source)

    def test_frontend_can_create_suggested_alarm_rules(self) -> None:
        source = self._panel_source()

        self.assertIn("SUGGEST RULES", source)
        self.assertIn("create_suggested_rules", source)
        self.assertIn("list_suggested_rules", source)
        self.assertIn("data-suggested-select", source)
        self.assertIn("select-all-suggested-rules", source)
        self.assertIn("deselect-all-suggested-rules", source)
        self.assertIn("create-selected-suggested-rules", source)
        self.assertIn("create-all-suggested-rules", source)

    def test_frontend_manages_rules(self) -> None:
        source = self._panel_source()

        self.assertIn("update_rule", source)
        self.assertIn("create_rule", source)
        self.assertIn("delete_rule", source)
        self.assertIn("delete_rules", source)
        self.assertIn('"clone"', source)
        self.assertIn("toggle-rule", source)
        self.assertIn("remove-auto-generated-rules", source)
        self.assertIn("data-rule-select", source)

    def test_frontend_has_resizable_listing_columns(self) -> None:
        source = self._panel_source()

        self.assertIn("_wireColumnResizers", source)
        self.assertIn("_columnWidths", source)
        self.assertIn("col-resizer", source)
        self.assertIn("pointerdown", source)
        self.assertIn("data-table-id", source)

    def test_frontend_history_filters_and_csv_export(self) -> None:
        source = self._panel_source()

        self.assertIn("export_history", source)
        self.assertIn("text/csv", source)
        self.assertIn("history-range", source)
        self.assertIn("history-type", source)

    def test_frontend_has_mobile_sidebar_toggle_and_next_decision(self) -> None:
        source = self._panel_source()

        self.assertIn("_toggleSidebar", source)
        self.assertIn("hass-toggle-menu", source)
        self.assertIn("open: true", source)
        self.assertIn('data-action="toggle-menu"', source)
        self.assertIn("_renderNext", source)
        self.assertIn("ACK ALL · ${pending.length}", source)

    def test_frontend_offers_shelve_presets_and_shows_expiry(self) -> None:
        source = self._panel_source()

        for label in ("1 hour", "4 hours", "8 hours", "1 day", "3 days", "7 days"):
            self.assertIn(label, source)
        self.assertIn("duration_minutes: minutes", source)
        self.assertIn("shelve_expiry", source)
        self.assertIn("unshelve_alarm", source)

    def test_frontend_bundles_its_fonts_locally(self) -> None:
        source = self._panel_source()
        fonts = Path("custom_components/industrial_alarm_panel/frontend/dist/fonts")

        self.assertNotIn("fonts.googleapis.com", source)
        for name in ("B612-Regular.woff2", "B612-Bold.woff2", "B612Mono-Regular.woff2", "OFL.txt"):
            self.assertTrue((fonts / name).exists(), name)

    def test_release_version_metadata_is_bumped(self) -> None:
        const_source = Path("custom_components/industrial_alarm_panel/const.py").read_text()
        manifest_source = Path(
            "custom_components/industrial_alarm_panel/manifest.json"
        ).read_text()
        pyproject_source = Path("pyproject.toml").read_text()
        readme_source = Path("README.md").read_text()

        expected_version = "1.1.1"
        const_version_match = re.search(r'^VERSION = "([^"]+)"$', const_source, re.MULTILINE)

        self.assertIsNotNone(const_version_match)
        self.assertNotIn("Current release:", readme_source)
        self.assertIn(f"## What's New in v{expected_version}", readme_source)

        const_version = const_version_match.group(1)
        manifest_version = json.loads(manifest_source)["version"]
        pyproject_version = tomllib.loads(pyproject_source)["project"]["version"]

        self.assertEqual(expected_version, const_version)
        self.assertEqual(
            {expected_version},
            {const_version, manifest_version, pyproject_version},
        )

    def test_websocket_registers_suggested_rule_management_commands(self) -> None:
        source = Path("custom_components/industrial_alarm_panel/websocket_api.py").read_text()

        self.assertIn("websocket_list_suggested_rules", source)
        self.assertIn("websocket_create_suggested_rules", source)
        self.assertIn("websocket_delete_rules", source)
        self.assertIn("select_suggested_rules", source)
        self.assertIn("delete_rules(", source)
        self.assertIn("generated_only", source)
        self.assertIn("rule_ids", source)
        self.assertIn("remove_per_rule_entity_registry_entries", source)

if __name__ == "__main__":
    unittest.main()
