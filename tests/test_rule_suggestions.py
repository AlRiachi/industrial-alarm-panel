import unittest

from custom_components.industrial_alarm_panel.rule_suggestions import suggest_alarm_rules


class FakeState:
    def __init__(
        self,
        entity_id: str,
        *,
        friendly_name: str,
        device_class: str | None = None,
        unit: str | None = None,
    ) -> None:
        self.entity_id = entity_id
        self.attributes = {"friendly_name": friendly_name}
        if device_class is not None:
            self.attributes["device_class"] = device_class
        if unit is not None:
            self.attributes["unit_of_measurement"] = unit


class RuleSuggestionTests(unittest.TestCase):
    def test_suggests_powertag_power_voltage_and_availability_rules(self) -> None:
        states = [
            FakeState(
                "sensor.powertag_main_power",
                friendly_name="PowerTag Main Power",
                device_class="power",
                unit="W",
            ),
            FakeState(
                "sensor.powertag_main_voltage",
                friendly_name="PowerTag Main Voltage",
                device_class="voltage",
                unit="V",
            ),
        ]

        rules = suggest_alarm_rules(states, existing_rule_ids=set())
        by_id = {rule["id"]: rule for rule in rules}

        self.assertEqual(
            by_id["auto_sensor_powertag_main_power_high_consumption"]["threshold"],
            2000,
        )
        self.assertEqual(
            by_id["auto_sensor_powertag_main_power_high_consumption"]["condition"],
            "above",
        )
        self.assertEqual(
            by_id["auto_sensor_powertag_main_voltage_low_voltage"]["threshold"],
            207,
        )
        self.assertEqual(
            by_id["auto_sensor_powertag_main_voltage_high_voltage"]["threshold"],
            253,
        )
        self.assertIn(
            "auto_sensor_powertag_main_power_unavailable",
            by_id,
        )
        self.assertEqual(
            by_id["auto_sensor_powertag_main_power_unavailable"]["condition"],
            "unavailable",
        )

    def test_converts_high_consumption_threshold_for_kw_sensors(self) -> None:
        states = [
            FakeState(
                "sensor.powertag_ev_power",
                friendly_name="PowerTag EV Power",
                device_class="power",
                unit="kW",
            )
        ]

        rules = suggest_alarm_rules(
            states,
            existing_rule_ids=set(),
            power_threshold_w=2500,
        )

        self.assertEqual(rules[0]["threshold"], 2.5)

    def test_suggests_high_solar_water_temperature_rule(self) -> None:
        states = [
            FakeState(
                "sensor.solar_water_tank_temperature",
                friendly_name="Solar Water Tank Temperature",
                device_class="temperature",
                unit="°C",
            )
        ]

        rules = suggest_alarm_rules(states, existing_rule_ids=set())
        by_id = {rule["id"]: rule for rule in rules}

        self.assertEqual(
            by_id[
                "auto_sensor_solar_water_tank_temperature_high_solar_water_temperature"
            ]["threshold"],
            75,
        )
        self.assertIn(
            "auto_sensor_solar_water_tank_temperature_unavailable",
            by_id,
        )

    def test_skips_existing_generated_rule_ids(self) -> None:
        states = [
            FakeState(
                "sensor.powertag_main_power",
                friendly_name="PowerTag Main Power",
                device_class="power",
                unit="W",
            )
        ]

        rules = suggest_alarm_rules(
            states,
            existing_rule_ids={
                "auto_sensor_powertag_main_power_high_consumption",
            },
        )

        self.assertNotIn(
            "auto_sensor_powertag_main_power_high_consumption",
            {rule["id"] for rule in rules},
        )


if __name__ == "__main__":
    unittest.main()
