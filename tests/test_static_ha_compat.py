import unittest
from pathlib import Path


class StaticHomeAssistantCompatibilityTests(unittest.TestCase):
    def test_options_flow_does_not_assign_read_only_config_entry_property(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/options_flow.py"
        ).read_text()

        self.assertNotIn("self.config_entry =", source)


if __name__ == "__main__":
    unittest.main()
