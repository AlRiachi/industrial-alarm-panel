"""Service handlers for Industrial Alarm Panel."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .alarm_models import AlarmPriority
from .const import (
    DOMAIN,
    SERVICE_ACKNOWLEDGE_ALARM,
    SERVICE_ACKNOWLEDGE_ALL,
    SERVICE_CREATE_RULE,
    SERVICE_DELETE_RULE,
    SERVICE_DISABLE_ALARM,
    SERVICE_ENABLE_ALARM,
    SERVICE_EXPORT_HISTORY,
    SERVICE_SHELVE_ALARM,
    SERVICE_SILENCE_HORN,
    SERVICE_TEST_SOUND,
    SERVICE_UNSHELVE_ALARM,
    SERVICE_UNSILENCE_HORN,
    SERVICE_UPDATE_RULE,
)

RULE_ID = "rule_id"
COMMENT = "comment"
PRIORITY = "priority"
AREA = "area"
DURATION_SECONDS = "duration_seconds"
DURATION_MINUTES = "duration_minutes"
RULE = "rule"
CHANGES = "changes"
START_TIME = "start_time"
END_TIME = "end_time"
FORMAT = "format"

ACK_SCHEMA = vol.Schema({vol.Required(RULE_ID): cv.string, vol.Optional(COMMENT): cv.string})
ACK_ALL_SCHEMA = vol.Schema(
    {
        vol.Optional(PRIORITY): vol.In([priority.value for priority in AlarmPriority]),
        vol.Optional(AREA): cv.string,
        vol.Optional(COMMENT): cv.string,
    }
)
SILENCE_SCHEMA = vol.Schema(
    {vol.Optional(DURATION_SECONDS): vol.All(vol.Coerce(int), vol.Range(min=1))}
)
SHELVE_SCHEMA = vol.Schema(
    {
        vol.Required(RULE_ID): cv.string,
        vol.Required(DURATION_MINUTES): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(COMMENT): cv.string,
    }
)
RULE_ID_SCHEMA = vol.Schema({vol.Required(RULE_ID): cv.string})
CREATE_RULE_SCHEMA = vol.Schema({vol.Required(RULE): dict})
UPDATE_RULE_SCHEMA = vol.Schema({vol.Required(RULE_ID): cv.string, vol.Required(CHANGES): dict})
TEST_SOUND_SCHEMA = vol.Schema(
    {vol.Optional(PRIORITY, default=AlarmPriority.CRITICAL.value): vol.In([priority.value for priority in AlarmPriority])}
)
EXPORT_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Optional(START_TIME): cv.string,
        vol.Optional(END_TIME): cv.string,
        vol.Optional(FORMAT, default="csv"): vol.In(["csv", "json"]),
    }
)

SERVICE_SCHEMAS = {
    SERVICE_ACKNOWLEDGE_ALARM: ACK_SCHEMA,
    SERVICE_ACKNOWLEDGE_ALL: ACK_ALL_SCHEMA,
    SERVICE_SILENCE_HORN: SILENCE_SCHEMA,
    SERVICE_UNSILENCE_HORN: vol.Schema({}),
    SERVICE_SHELVE_ALARM: SHELVE_SCHEMA,
    SERVICE_UNSHELVE_ALARM: RULE_ID_SCHEMA,
    SERVICE_DISABLE_ALARM: ACK_SCHEMA,
    SERVICE_ENABLE_ALARM: RULE_ID_SCHEMA,
    SERVICE_CREATE_RULE: CREATE_RULE_SCHEMA,
    SERVICE_UPDATE_RULE: UPDATE_RULE_SCHEMA,
    SERVICE_DELETE_RULE: RULE_ID_SCHEMA,
    SERVICE_TEST_SOUND: TEST_SOUND_SCHEMA,
    SERVICE_EXPORT_HISTORY: EXPORT_HISTORY_SCHEMA,
}


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services once."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("services_registered"):
        return

    async def _handler(call: ServiceCall) -> Any:
        runtime = _first_runtime(hass)
        engine = runtime.engine
        operator = call.context.user_id
        data = call.data

        if call.service == SERVICE_ACKNOWLEDGE_ALARM:
            await engine.acknowledge_alarm(
                data[RULE_ID], operator=operator, comment=data.get(COMMENT)
            )
            return
        if call.service == SERVICE_ACKNOWLEDGE_ALL:
            await engine.acknowledge_all(
                priority=data.get(PRIORITY),
                area=data.get(AREA),
                operator=operator,
                comment=data.get(COMMENT),
            )
            return
        if call.service == SERVICE_SILENCE_HORN:
            await engine.silence_horn(
                data.get(DURATION_SECONDS), operator=operator
            )
            return
        if call.service == SERVICE_UNSILENCE_HORN:
            await engine.unsilence_horn(operator=operator)
            return
        if call.service == SERVICE_SHELVE_ALARM:
            await engine.shelve_alarm(
                data[RULE_ID],
                duration_minutes=data[DURATION_MINUTES],
                operator=operator,
                comment=data.get(COMMENT),
            )
            return
        if call.service == SERVICE_UNSHELVE_ALARM:
            await engine.unshelve_alarm(data[RULE_ID], operator=operator)
            return
        if call.service == SERVICE_DISABLE_ALARM:
            await engine.disable_alarm(
                data[RULE_ID], operator=operator, comment=data.get(COMMENT)
            )
            return
        if call.service == SERVICE_ENABLE_ALARM:
            await engine.enable_alarm(data[RULE_ID], operator=operator)
            return
        if call.service == SERVICE_CREATE_RULE:
            await engine.create_rule(data[RULE])
            await runtime.rule_store.async_save_rules(engine.rules.values())
            _reload_entry(hass, runtime.entry_id)
            return
        if call.service == SERVICE_UPDATE_RULE:
            await engine.update_rule(data[RULE_ID], data[CHANGES])
            await runtime.rule_store.async_save_rules(engine.rules.values())
            _reload_entry(hass, runtime.entry_id)
            return
        if call.service == SERVICE_DELETE_RULE:
            await engine.delete_rule(data[RULE_ID])
            await runtime.rule_store.async_save_rules(engine.rules.values())
            _reload_entry(hass, runtime.entry_id)
            return
        if call.service == SERVICE_TEST_SOUND:
            await runtime.sound_manager.test_sound(AlarmPriority(data[PRIORITY]))
            engine.notify_listeners()
            return
        if call.service == SERVICE_EXPORT_HISTORY:
            start = _parse_datetime(data.get(START_TIME))
            end = _parse_datetime(data.get(END_TIME))
            events = await runtime.history_store.query_events(
                start_time=start, end_time=end
            )
            return {
                "format": data.get(FORMAT, "csv"),
                "rows": [_event_row(event.to_dict()) for event in events],
            }

    for service, schema in SERVICE_SCHEMAS.items():
        hass.services.async_register(DOMAIN, service, _handler, schema=schema)
    domain_data["services_registered"] = True


def _first_runtime(hass: HomeAssistant) -> Any:
    runtimes = [
        value
        for key, value in hass.data.get(DOMAIN, {}).items()
        if key != "services_registered" and key != "websocket_registered"
    ]
    if not runtimes:
        raise RuntimeError("Industrial Alarm Panel is not configured")
    return runtimes[0]


def _reload_entry(hass: HomeAssistant, entry_id: str) -> None:
    hass.async_create_task(hass.config_entries.async_reload(entry_id))


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _event_row(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if value is not None}


def service_names() -> Iterable[str]:
    """Return registered service names for diagnostics/tests."""

    return SERVICE_SCHEMAS.keys()
