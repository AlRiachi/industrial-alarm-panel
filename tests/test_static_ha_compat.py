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

    def test_frontend_version_is_bumped_for_rule_management_ui(self) -> None:
        const_source = Path("custom_components/industrial_alarm_panel/const.py").read_text()
        manifest_source = Path(
            "custom_components/industrial_alarm_panel/manifest.json"
        ).read_text()
        pyproject_source = Path("pyproject.toml").read_text()
        readme_source = Path("README.md").read_text()

        expected_version = "1.0.11"
        const_version_match = re.search(r'^VERSION = "([^"]+)"$', const_source, re.MULTILINE)
        readme_version_match = re.search(
            r"^Current release: `v([^`]+)`$", readme_source, re.MULTILINE
        )

        self.assertIsNotNone(const_version_match)
        self.assertIsNotNone(readme_version_match)

        const_version = const_version_match.group(1)
        manifest_version = json.loads(manifest_source)["version"]
        pyproject_version = tomllib.loads(pyproject_source)["project"]["version"]
        readme_version = readme_version_match.group(1)

        self.assertEqual(expected_version, const_version)
        self.assertEqual(
            {expected_version},
            {const_version, manifest_version, pyproject_version, readme_version},
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

    def test_frontend_previews_and_selects_suggested_rules(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("list_suggested_rules", source)
        self.assertIn("_previewSuggestedRules", source)
        self.assertIn("_selectedSuggestedRuleIds", source)
        self.assertIn("Create Selected", source)
        self.assertIn("Create All", source)
        self.assertIn("data-suggested-select", source)
        self.assertIn("_clearSuggestedPreview", source)
        self.assertIn("Select All", source)
        self.assertIn("Deselect All", source)
        self.assertIn("_selectAllSuggestedRules", source)
        self.assertIn("_deselectAllSuggestedRules", source)

    def test_frontend_can_bulk_delete_rules(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("delete_rules", source)
        self.assertIn("_selectedRuleIds", source)
        self.assertIn("_deleteSelectedRules", source)
        self.assertIn("_removeAutoGeneratedRules", source)
        self.assertIn("Remove Auto-Generated Rules", source)
        self.assertIn("data-rule-select", source)

    def test_frontend_preserves_table_horizontal_scroll_on_refresh(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("_tableScrollLeft", source)
        self.assertIn("_captureTableScroll", source)
        self.assertIn("_restoreTableScroll", source)
        self.assertIn("scrollLeft", source)
        self.assertIn("table[data-table-id]", source)

    def test_frontend_has_mobile_sidebar_toggle_button(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("_toggleSidebar", source)
        self.assertIn("hass-toggle-menu", source)
        self.assertIn("open: true", source)
        self.assertIn("data-action=\"toggle-menu\"", source)
        self.assertIn("menu-button", source)


if __name__ == "__main__":
    unittest.main()
