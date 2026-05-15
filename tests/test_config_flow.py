import importlib.util
import unittest


@unittest.skipUnless(
    importlib.util.find_spec("homeassistant"),
    "Home Assistant is not installed in this environment",
)
class ConfigFlowImportTests(unittest.TestCase):
    def test_config_flow_module_imports(self) -> None:
        import custom_components.industrial_alarm_panel.config_flow as config_flow

        self.assertTrue(hasattr(config_flow, "IndustrialAlarmPanelConfigFlow"))


if __name__ == "__main__":
    unittest.main()
