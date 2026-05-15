import importlib.util
import unittest


@unittest.skipUnless(
    importlib.util.find_spec("homeassistant"),
    "Home Assistant is not installed in this environment",
)
class ServicesImportTests(unittest.TestCase):
    def test_services_module_imports(self) -> None:
        import custom_components.industrial_alarm_panel.services as services

        self.assertIn("acknowledge_alarm", set(services.service_names()))


if __name__ == "__main__":
    unittest.main()
