"""WebSocket API for the Industrial Alarm Panel frontend."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import wraps
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .alarm_models import AlarmPriority, AlarmRuleNotFoundError, AlarmValidationError
from .const import DOMAIN, EXPORT_HISTORY_MAX_ROWS, display_options
from .rule_management import delete_rules, select_suggested_rules
from .rule_suggestions import suggest_alarm_rules
from .runtime import (
    IntegrationNotLoadedError,
    async_get_runtime,
    remove_per_rule_entity_registry_entries,
)

_LOGGER = logging.getLogger(__name__)

__all__ = ["async_register_websocket_api", "remove_per_rule_entity_registry_entries"]

AsyncHandler = Callable[
    [HomeAssistant, websocket_api.ActiveConnection, dict[str, Any]], Awaitable[None]
]


def handle_errors(func: AsyncHandler) -> AsyncHandler:
    """Translate expected domain errors into websocket error replies.

    - unknown rule / integration not loaded -> ``not_found``
    - validation problems (bad rule data, bad timestamps) -> ``invalid_format``
    """

    @wraps(func)
    async def wrapper(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        try:
            await func(hass, connection, msg)
        except (AlarmRuleNotFoundError, IntegrationNotLoadedError) as err:
            connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(err))
        except (AlarmValidationError, ValueError, vol.Invalid) as err:
            connection.send_error(
                msg["id"], websocket_api.ERR_INVALID_FORMAT, str(err)
            )
        except KeyError as err:
            missing = err.args[0] if err.args else err
            connection.send_error(
                msg["id"], websocket_api.ERR_NOT_FOUND, f"Not found: {missing}"
            )

    return wrapper

SUGGESTED_RULE_THRESHOLD_SCHEMA = {
    vol.Optional("power_threshold_w", default=2000): vol.All(
        vol.Coerce(float), vol.Range(min=1)
    ),
    vol.Optional("low_voltage_v", default=207): vol.All(
        vol.Coerce(float), vol.Range(min=1)
    ),
    vol.Optional("high_voltage_v", default=253): vol.All(
        vol.Coerce(float), vol.Range(min=1)
    ),
    vol.Optional("high_solar_water_temp_c", default=75): vol.All(
        vol.Coerce(float), vol.Range(min=1)
    ),
}


def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register websocket commands once."""

    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("websocket_registered"):
        return
    websocket_api.async_register_command(hass, websocket_list_alarms)
    websocket_api.async_register_command(hass, websocket_list_history)
    websocket_api.async_register_command(hass, websocket_list_rules)
    websocket_api.async_register_command(hass, websocket_create_rule)
    websocket_api.async_register_command(hass, websocket_list_suggested_rules)
    websocket_api.async_register_command(hass, websocket_create_suggested_rules)
    websocket_api.async_register_command(hass, websocket_update_rule)
    websocket_api.async_register_command(hass, websocket_delete_rule)
    websocket_api.async_register_command(hass, websocket_delete_rules)
    websocket_api.async_register_command(hass, websocket_acknowledge)
    websocket_api.async_register_command(hass, websocket_acknowledge_all)
    websocket_api.async_register_command(hass, websocket_silence)
    websocket_api.async_register_command(hass, websocket_shelve)
    websocket_api.async_register_command(hass, websocket_test_sound)
    websocket_api.async_register_command(hass, websocket_export_history)
    domain_data["websocket_registered"] = True


def _runtime(hass: HomeAssistant) -> Any:
    return async_get_runtime(hass)


def _operator(connection: websocket_api.ActiveConnection) -> str | None:
    user = getattr(connection, "user", None)
    return getattr(user, "id", None)


@websocket_api.websocket_command(
    {vol.Required("type"): "industrial_alarm_panel/list_alarms"}
)
@websocket_api.async_response
@handle_errors
async def websocket_list_alarms(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List alarms."""

    runtime = _runtime(hass)
    connection.send_result(
        msg["id"],
        {
            "alarms": runtime.engine.list_alarms(include_normal=True),
            "sound": runtime.sound_manager.as_dict(),
            "display": display_options(runtime.options),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/list_history",
        vol.Optional("limit", default=250): vol.All(vol.Coerce(int), vol.Range(min=1, max=5000)),
        vol.Optional("start_time"): str,
        vol.Optional("end_time"): str,
        vol.Optional("priority"): str,
        vol.Optional("area"): str,
        vol.Optional("system"): str,
        vol.Optional("event_type"): str,
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_list_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List alarm history."""

    runtime = _runtime(hass)
    events = await runtime.history_store.query_events(
        limit=msg["limit"],
        start_time=_parse_datetime(msg.get("start_time")),
        end_time=_parse_datetime(msg.get("end_time")),
        priority=msg.get("priority"),
        area=msg.get("area"),
        system=msg.get("system"),
        event_type=msg.get("event_type"),
    )
    connection.send_result(msg["id"], {"events": [event.to_dict() for event in events]})


@websocket_api.websocket_command(
    {vol.Required("type"): "industrial_alarm_panel/list_rules"}
)
@websocket_api.async_response
@handle_errors
async def websocket_list_rules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List alarm rules."""

    runtime = _runtime(hass)
    connection.send_result(
        msg["id"],
        {"rules": [rule.to_dict() for rule in runtime.engine.rules.values()]},
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "industrial_alarm_panel/create_rule", vol.Required("rule"): dict}
)
@websocket_api.async_response
@handle_errors
async def websocket_create_rule(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create an alarm rule."""

    runtime = _runtime(hass)
    [rule] = await runtime.async_create_rules([msg["rule"]])
    connection.send_result(msg["id"], {"rule": rule.to_dict()})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/list_suggested_rules",
        **SUGGESTED_RULE_THRESHOLD_SCHEMA,
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_list_suggested_rules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Preview suggested alarm rules from current Home Assistant sensors."""

    runtime = _runtime(hass)
    suggested = suggest_alarm_rules(
        _sensor_states(hass),
        existing_rule_ids=set(runtime.engine.rules),
        power_threshold_w=msg["power_threshold_w"],
        low_voltage_v=msg["low_voltage_v"],
        high_voltage_v=msg["high_voltage_v"],
        high_solar_water_temp_c=msg["high_solar_water_temp_c"],
    )

    connection.send_result(msg["id"], {"suggested": suggested})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/create_suggested_rules",
        vol.Optional("rule_ids"): [str],
        **SUGGESTED_RULE_THRESHOLD_SCHEMA,
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_create_suggested_rules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create suggested alarm rules from current Home Assistant sensors."""

    runtime = _runtime(hass)
    suggested = suggest_alarm_rules(
        _sensor_states(hass),
        existing_rule_ids=set(runtime.engine.rules),
        power_threshold_w=msg["power_threshold_w"],
        low_voltage_v=msg["low_voltage_v"],
        high_voltage_v=msg["high_voltage_v"],
        high_solar_water_temp_c=msg["high_solar_water_temp_c"],
    )
    selected, skipped_rule_ids = select_suggested_rules(
        suggested, msg.get("rule_ids")
    )

    created = [rule.to_dict() for rule in await runtime.async_create_rules(selected)]

    connection.send_result(
        msg["id"],
        {
            "created_count": len(created),
            "created": created,
            "skipped_rule_ids": skipped_rule_ids,
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/update_rule",
        vol.Required("rule_id"): str,
        vol.Required("changes"): dict,
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_update_rule(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update an alarm rule."""

    runtime = _runtime(hass)
    rule = await runtime.async_update_rule(
        msg["rule_id"], msg["changes"], operator=_operator(connection)
    )
    connection.send_result(msg["id"], {"rule": rule.to_dict()})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/delete_rule",
        vol.Required("rule_id"): str,
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_delete_rule(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete an alarm rule."""

    runtime = _runtime(hass)
    removed_entity_ids = await runtime.async_delete_rule(msg["rule_id"])
    connection.send_result(
        msg["id"], {"deleted": True, "removed_entity_ids": removed_entity_ids}
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/delete_rules",
        vol.Optional("rule_ids"): [str],
        vol.Optional("generated_only", default=False): bool,
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_delete_rules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete selected alarm rules."""

    runtime = _runtime(hass)
    result = await delete_rules(
        runtime.engine,
        rule_ids=msg.get("rule_ids"),
        generated_only=msg["generated_only"],
    )
    removed_entity_ids: list[str] = []
    if result.deleted_rules:
        removed_entity_ids = await runtime.async_rules_changed(
            removed=result.deleted_rules
        )

    connection.send_result(
        msg["id"],
        {
            "deleted_rule_ids": result.deleted_rule_ids,
            "deleted_count": len(result.deleted_rules),
            "skipped_rule_ids": result.skipped_rule_ids,
            "removed_entity_ids": removed_entity_ids,
            "removed_entity_count": len(removed_entity_ids),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/acknowledge",
        vol.Required("rule_id"): str,
        vol.Optional("comment"): str,
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_acknowledge(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Acknowledge one alarm."""

    await _runtime(hass).engine.acknowledge_alarm(
        msg["rule_id"], operator=_operator(connection), comment=msg.get("comment")
    )
    connection.send_result(msg["id"], {"acknowledged": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/acknowledge_all",
        vol.Optional("priority"): str,
        vol.Optional("area"): str,
        vol.Optional("comment"): str,
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_acknowledge_all(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Acknowledge all matching alarms."""

    count = await _runtime(hass).engine.acknowledge_all(
        priority=msg.get("priority"),
        area=msg.get("area"),
        operator=_operator(connection),
        comment=msg.get("comment"),
    )
    connection.send_result(msg["id"], {"acknowledged": count})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/silence",
        vol.Optional("duration_seconds"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_silence(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Silence horn."""

    await _runtime(hass).engine.silence_horn(
        msg.get("duration_seconds"), operator=_operator(connection)
    )
    connection.send_result(msg["id"], {"silenced": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/shelve",
        vol.Required("rule_id"): str,
        vol.Required("duration_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("comment"): str,
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_shelve(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Shelve alarm."""

    await _runtime(hass).engine.shelve_alarm(
        msg["rule_id"],
        duration_minutes=msg["duration_minutes"],
        operator=_operator(connection),
        comment=msg.get("comment"),
    )
    connection.send_result(msg["id"], {"shelved": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/test_sound",
        vol.Optional("priority", default=AlarmPriority.CRITICAL.value): vol.In(
            [priority.value for priority in AlarmPriority]
        ),
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_test_sound(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Test sound."""

    runtime = _runtime(hass)
    await runtime.sound_manager.test_sound(AlarmPriority(msg["priority"]))
    runtime.engine.notify_listeners()
    connection.send_result(msg["id"], {"played": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/export_history",
        vol.Optional("start_time"): str,
        vol.Optional("end_time"): str,
        vol.Optional("format", default="csv"): vol.In(["csv", "json"]),
        vol.Optional("limit", default=EXPORT_HISTORY_MAX_ROWS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=EXPORT_HISTORY_MAX_ROWS)
        ),
    }
)
@websocket_api.async_response
@handle_errors
async def websocket_export_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Export history rows."""

    runtime = _runtime(hass)
    limit = msg["limit"]
    events = await runtime.history_store.query_events(
        limit=limit,
        start_time=_parse_datetime(msg.get("start_time")),
        end_time=_parse_datetime(msg.get("end_time")),
    )
    connection.send_result(
        msg["id"],
        {
            "format": msg["format"],
            "rows": [event.to_dict() for event in events],
            "limit": limit,
            "truncated": len(events) >= limit,
        },
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _sensor_states(hass: HomeAssistant) -> list[Any]:
    async_all = getattr(hass.states, "async_all", None)
    if async_all:
        try:
            states = async_all("sensor")
        except TypeError:
            states = [
                state
                for state in async_all()
                if str(getattr(state, "entity_id", "")).startswith("sensor.")
            ]
        return list(states)

    async_entity_ids = getattr(hass.states, "async_entity_ids", None)
    if async_entity_ids:
        return [
            state
            for entity_id in async_entity_ids("sensor")
            if (state := hass.states.get(entity_id)) is not None
        ]
    return []
