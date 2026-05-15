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


if __name__ == "__main__":
    unittest.main()
