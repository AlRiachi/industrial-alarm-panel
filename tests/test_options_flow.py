import importlib.util
import unittest


@unittest.skipUnless(
    importlib.util.find_spec("homeassistant"),
    "Home Assistant is not installed in this environment",
)
class OptionsFlowImportTests(unittest.TestCase):
    def test_options_flow_module_imports(self) -> None:
        import custom_components.industrial_alarm_panel.options_flow as options_flow

        self.assertTrue(hasattr(options_flow, "OptionsFlowHandler"))


if __name__ == "__main__":
    unittest.main()
