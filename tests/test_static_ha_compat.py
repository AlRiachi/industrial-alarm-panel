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

    def test_frontend_subscribes_to_alarm_update_events(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("subscribeEvents", source)
        self.assertIn("industrial_alarm_panel_alarms_updated", source)
        self.assertIn("_unsubscribeUpdates", source)

    def test_frontend_uses_full_row_alarm_colors_and_neutral_acknowledged_rows(
        self,
    ) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("alarm-row", source)
        self.assertIn("state-active-unack", source)
        self.assertIn("state-active-ack", source)
        self.assertIn("background: #f3f4f6", source)
        self.assertIn(".alarm-row.priority-critical.state-active-unack", source)

    def test_frontend_can_create_suggested_alarm_rules(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("Suggested Rules", source)
        self.assertIn("create_suggested_rules", source)
        self.assertIn("High W", source)
        self.assertIn("Low V", source)
        self.assertIn("Solar C", source)

    def test_frontend_preserves_rule_forms_while_refreshing(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("_ruleDraft", source)
        self.assertIn("_suggestionDraft", source)
        self.assertIn("_isEditingRulesForm", source)
        self.assertIn("if (!this._isEditingRulesForm()) this._render();", source)

    def test_frontend_has_resizable_listing_columns(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("_wireColumnResizers", source)
        self.assertIn("_columnWidths", source)
        self.assertIn("col-resizer", source)
        self.assertIn("pointerdown", source)
        self.assertIn("colgroup", source)
        self.assertIn("data-table-id", source)

    def test_frontend_delays_alarm_color_and_throttles_browser_horn(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("_alarmVisualDelayMs = 2000", source)
        self.assertIn("state-pending-color", source)
        self.assertIn("_browserHornCooldownMs = 2000", source)
        self.assertIn("_maybePlayBrowserHorn", source)

    def test_frontend_version_is_bumped_for_suggested_rule_ui(self) -> None:
        const_source = Path("custom_components/industrial_alarm_panel/const.py").read_text()
        manifest_source = Path(
            "custom_components/industrial_alarm_panel/manifest.json"
        ).read_text()

        self.assertIn('VERSION = "1.0.9"', const_source)
        self.assertIn('"version": "1.0.9"', manifest_source)

    def test_websocket_registers_suggested_rule_command(self) -> None:
        source = Path("custom_components/industrial_alarm_panel/websocket_api.py").read_text()

        self.assertIn("websocket_create_suggested_rules", source)
        self.assertIn("suggest_alarm_rules", source)


if __name__ == "__main__":
    unittest.main()
