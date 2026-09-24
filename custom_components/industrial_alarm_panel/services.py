"""Service handlers for Industrial Alarm Panel."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .alarm_models import AlarmPriority, AlarmRuleNotFoundError, AlarmValidationError
from .const import (
    DOMAIN,
    EXPORT_HISTORY_MAX_ROWS,
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
LIMIT = "limit"

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
        vol.Optional(LIMIT, default=EXPORT_HISTORY_MAX_ROWS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=EXPORT_HISTORY_MAX_ROWS)
        ),
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


#: Services that change rule configuration require an admin user when called
#: with a user context (automations/scripts without a user are allowed).
ADMIN_SERVICES = frozenset({SERVICE_CREATE_RULE, SERVICE_UPDATE_RULE, SERVICE_DELETE_RULE})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services once (from ``async_setup``).

    The config entry is resolved when a service is called, so services survive
    entry reloads.
    """

    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("services_registered"):
        return

    async def _handler(call: ServiceCall) -> Any:
        try:
            return await _async_handle(hass, call)
        except AlarmRuleNotFoundError as err:
            raise ServiceValidationError(str(err)) from err
        except (AlarmValidationError, ValueError) as err:
            raise ServiceValidationError(f"Invalid request: {err}") from err
        except KeyError as err:
            missing = err.args[0] if err.args else err
            raise ServiceValidationError(f"Not found: {missing}") from err

    for service, schema in SERVICE_SCHEMAS.items():
        if service in ADMIN_SERVICES:
            async_register_admin_service(hass, DOMAIN, service, _handler, schema=schema)
        elif service == SERVICE_EXPORT_HISTORY:
            hass.services.async_register(
                DOMAIN,
                service,
                _handler,
                schema=schema,
                supports_response=SupportsResponse.OPTIONAL,
            )
        else:
            hass.services.async_register(DOMAIN, service, _handler, schema=schema)
    domain_data["services_registered"] = True


async def _async_handle(hass: HomeAssistant, call: ServiceCall) -> Any:
    runtime = _first_runtime(hass)
    engine = runtime.engine
    operator = call.context.user_id
    data = call.data

    if call.service == SERVICE_ACKNOWLEDGE_ALARM:
        await engine.acknowledge_alarm(
            data[RULE_ID], operator=operator, comment=data.get(COMMENT)
        )
        return None
    if call.service == SERVICE_ACKNOWLEDGE_ALL:
        await engine.acknowledge_all(
            priority=data.get(PRIORITY),
            area=data.get(AREA),
            operator=operator,
            comment=data.get(COMMENT),
        )
        return None
    if call.service == SERVICE_SILENCE_HORN:
        await engine.silence_horn(data.get(DURATION_SECONDS), operator=operator)
        return None
    if call.service == SERVICE_UNSILENCE_HORN:
        await engine.unsilence_horn(operator=operator)
        return None
    if call.service == SERVICE_SHELVE_ALARM:
        await engine.shelve_alarm(
            data[RULE_ID],
            duration_minutes=data[DURATION_MINUTES],
            operator=operator,
            comment=data.get(COMMENT),
        )
        return None
    if call.service == SERVICE_UNSHELVE_ALARM:
        await engine.unshelve_alarm(data[RULE_ID], operator=operator)
        return None
    if call.service == SERVICE_DISABLE_ALARM:
        await engine.disable_alarm(
            data[RULE_ID], operator=operator, comment=data.get(COMMENT)
        )
        return None
    if call.service == SERVICE_ENABLE_ALARM:
        await engine.enable_alarm(data[RULE_ID], operator=operator)
        return None
    if call.service == SERVICE_CREATE_RULE:
        await runtime.async_create_rules([data[RULE]])
        return None
    if call.service == SERVICE_UPDATE_RULE:
        await runtime.async_update_rule(data[RULE_ID], data[CHANGES], operator=operator)
        return None
    if call.service == SERVICE_DELETE_RULE:
        await runtime.async_delete_rule(data[RULE_ID])
        return None
    if call.service == SERVICE_TEST_SOUND:
        await runtime.sound_manager.test_sound(AlarmPriority(data[PRIORITY]))
        engine.notify_listeners()
        if runtime.reschedule_timers is not None:
            runtime.reschedule_timers()
        return None
    if call.service == SERVICE_EXPORT_HISTORY:
        limit = int(data.get(LIMIT, EXPORT_HISTORY_MAX_ROWS))
        events = await runtime.history_store.query_events(
            limit=limit,
            start_time=_parse_datetime(data.get(START_TIME)),
            end_time=_parse_datetime(data.get(END_TIME)),
        )
        return {
            "format": data.get(FORMAT, "csv"),
            "rows": [_event_row(event.to_dict()) for event in events],
            "limit": limit,
            "truncated": len(events) >= limit,
        }
    return None


def _first_runtime(hass: HomeAssistant) -> Any:
    from .runtime import IntegrationNotLoadedError, async_get_runtime

    try:
        return async_get_runtime(hass)
    except IntegrationNotLoadedError as err:
        raise HomeAssistantError(str(err)) from err


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _event_row(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if value is not None}


def service_names() -> Iterable[str]:
    """Return registered service names for diagnostics/tests."""

    return SERVICE_SCHEMAS.keys()
