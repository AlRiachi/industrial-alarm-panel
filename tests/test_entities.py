import importlib.util
import unittest


@unittest.skipUnless(
    importlib.util.find_spec("homeassistant"),
    "Home Assistant is not installed in this environment",
)
class EntityImportTests(unittest.TestCase):
    def test_entity_modules_import(self) -> None:
        import custom_components.industrial_alarm_panel.binary_sensor
        import custom_components.industrial_alarm_panel.button
        import custom_components.industrial_alarm_panel.number
        import custom_components.industrial_alarm_panel.select
        import custom_components.industrial_alarm_panel.sensor
        import custom_components.industrial_alarm_panel.switch

        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
