"""Generate suggested alarm rules from Home Assistant sensor metadata."""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any


def suggest_alarm_rules(
    states: Iterable[Any],
    *,
    existing_rule_ids: set[str],
    power_threshold_w: float = 2000,
    low_voltage_v: float = 207,
    high_voltage_v: float = 253,
    high_solar_water_temp_c: float = 75,
) -> list[dict[str, Any]]:
    """Return generated alarm rules for electrical and solar hot-water sensors."""

    rules: list[dict[str, Any]] = []
    seen_rule_ids = set(existing_rule_ids)

    for state in states:
        entity_id = str(getattr(state, "entity_id", ""))
        if not entity_id.startswith("sensor."):
            continue

        friendly_name = _friendly_name(state)
        haystack = f"{entity_id} {friendly_name}".lower()
        device_class = _attribute(state, "device_class").lower()
        unit = _attribute(state, "unit_of_measurement").lower()

        is_powertag = "powertag" in haystack or "power tag" in haystack
        is_power = device_class == "power" or unit in {"w", "kw"}
        is_voltage = device_class == "voltage" or unit == "v"
        is_solar_water_temp = (
            (device_class == "temperature" or unit in {"c", "°c"})
            and "solar" in haystack
            and any(token in haystack for token in ("water", "tank", "boiler"))
        )

        if is_power:
            threshold = _power_threshold_for_unit(power_threshold_w, unit)
            _append_rule(
                rules,
                seen_rule_ids,
                entity_id,
                "high_consumption",
                {
                    "name": f"{friendly_name} High Consumption",
                    "condition": "above",
                    "threshold": threshold,
                    "deadband": _number_for_unit(0.1, unit) if unit == "kw" else 100,
                    "priority": "high",
                    "area": "Electrical",
                    "system": "PowerTag" if is_powertag else "Electrical",
                    "description": f"{friendly_name} is above {threshold:g} {unit or 'W'}",
                    "instructions": "Check major loads and abnormal electrical consumption.",
                },
            )

        if is_voltage:
            for suffix, name, condition, threshold in (
                ("low_voltage", "Low Voltage", "below", low_voltage_v),
                ("high_voltage", "High Voltage", "above", high_voltage_v),
            ):
                _append_rule(
                    rules,
                    seen_rule_ids,
                    entity_id,
                    suffix,
                    {
                        "name": f"{friendly_name} {name}",
                        "condition": condition,
                        "threshold": _clean_number(threshold),
                        "deadband": 2,
                        "priority": "high",
                        "area": "Electrical",
                        "system": "PowerTag" if is_powertag else "Electrical",
                        "description": f"{friendly_name} is {condition} {threshold:g} V",
                        "instructions": "Check supply voltage, upstream breaker, and load balance.",
                    },
                )

        if is_solar_water_temp:
            _append_rule(
                rules,
                seen_rule_ids,
                entity_id,
                "high_solar_water_temperature",
                {
                    "name": f"{friendly_name} High Temperature",
                    "condition": "above",
                    "threshold": _clean_number(high_solar_water_temp_c),
                    "deadband": 2,
                    "priority": "high",
                    "area": "Solar",
                    "system": "Solar Hot Water",
                    "description": (
                        f"{friendly_name} is above {high_solar_water_temp_c:g} C"
                    ),
                    "instructions": "Check circulation, pump operation, and over-temperature protection.",
                },
            )

        if is_powertag or is_power or is_voltage or is_solar_water_temp:
            _append_rule(
                rules,
                seen_rule_ids,
                entity_id,
                "unavailable",
                {
                    "name": f"{friendly_name} Unavailable",
                    "condition": "unavailable",
                    "priority": "low",
                    "audible": False,
                    "auto_ack_on_clear": True,
                    "area": "Solar" if is_solar_water_temp else "Electrical",
                    "system": (
                        "Solar Hot Water"
                        if is_solar_water_temp
                        else "PowerTag"
                        if is_powertag
                        else "Electrical"
                    ),
                    "description": f"{friendly_name} is unavailable",
                    "instructions": "Check device connectivity and Home Assistant integration status.",
                },
            )

    return rules


def _append_rule(
    rules: list[dict[str, Any]],
    seen_rule_ids: set[str],
    entity_id: str,
    suffix: str,
    rule_data: dict[str, Any],
) -> None:
    rule_id = f"auto_{_slugify(entity_id)}_{suffix}"
    if rule_id in seen_rule_ids:
        return
    seen_rule_ids.add(rule_id)
    rules.append(
        {
            "id": rule_id,
            "entity_id": entity_id,
            "tag": entity_id,
            "requires_ack": True,
            "audible": True,
            **rule_data,
        }
    )


def _attribute(state: Any, name: str) -> str:
    return str(getattr(state, "attributes", {}).get(name) or "").strip()


def _friendly_name(state: Any) -> str:
    return _attribute(state, "friendly_name") or str(getattr(state, "entity_id", ""))


def _power_threshold_for_unit(power_threshold_w: float, unit: str) -> float | int:
    if unit == "kw":
        return _clean_number(power_threshold_w / 1000)
    return _clean_number(power_threshold_w)


def _number_for_unit(value: float, unit: str) -> float | int:
    if unit == "kw":
        return _clean_number(value)
    return _clean_number(value)


def _clean_number(value: float) -> float | int:
    return int(value) if float(value).is_integer() else value


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "alarm"
