"""Industrial Alarm Panel integration."""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .alarm_engine import AlarmEngine
from .alarm_sound import AlarmSoundManager
from .alarm_store import (
    HomeAssistantRuleStore,
    SQLiteHistoryStore,
    schedule_history_retention,
)
from .const import (
    CONF_ALARM_FLOOD_THRESHOLD,
    CONF_ALARM_FLOOD_WINDOW_SECONDS,
    CONF_AUTO_SHELVE_FLAPPING,
    CONF_DEFAULT_DEADBAND,
    CONF_DEFAULT_DELAY_OFF,
    CONF_DEFAULT_DELAY_ON,
    CONF_FLAPPING_DETECTION_THRESHOLD,
    CONF_HISTORY_RETENTION_DAYS,
    CONF_MEDIA_PLAYERS,
    CONF_MEDIA_SOUND_URL,
    CONF_REPEAT_INTERVAL_SECONDS,
    CONF_REPEAT_UNTIL_SILENCED,
    CONF_SOUND_MODE,
    CONF_STORE_NORMAL_EVENTS,
    DEFAULT_OPTIONS,
    DOMAIN,
    PLATFORMS,
    RULES_STORAGE_KEY,
    STATE_STORAGE_KEY,
)
from .runtime import IndustrialAlarmConfigEntry, IndustrialAlarmPanelRuntime

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

try:  # Allows pure unit tests to import the package without Home Assistant.
    from homeassistant.helpers import config_validation as cv

    CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
except ModuleNotFoundError:  # pragma: no cover
    CONFIG_SCHEMA = None

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "IndustrialAlarmConfigEntry",
    "IndustrialAlarmPanelRuntime",
    "async_setup",
    "async_setup_entry",
    "async_unload_entry",
]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register services and websocket commands once for the domain."""

    from .services import async_setup_services
    from .websocket_api import async_register_websocket_api

    await async_setup_services(hass)
    async_register_websocket_api(hass)
    return True


def media_content_id(url_template: str, priority: Any) -> str | None:
    """Return the media URL for a priority, or None if no URL is configured.

    ``url_template`` may contain ``[priority]`` (or ``{priority}``), replaced by
    critical/high/medium/low/info/status. The integration ships no audio files: the user supplies them, for
    example under ``/config/www/`` and referenced as ``/local/...``.
    """

    template = (url_template or "").strip()
    if not template:
        return None
    value = getattr(priority, "value", priority)
    return template.replace("[priority]", str(value)).replace("{priority}", str(value))


async def async_setup_entry(
    hass: HomeAssistant, entry: IndustrialAlarmConfigEntry
) -> bool:
    """Set up Industrial Alarm Panel from a config entry."""

    from homeassistant.core import Event, callback
    from homeassistant.helpers.event import (
        async_call_later,
        async_track_state_change_event,
        async_track_time_interval,
    )

    from homeassistant.util import dt as dt_util

    from .alarm_panel import async_register_panel
    from .frontend_events import attach_alarm_update_event_listener

    options = {**DEFAULT_OPTIONS, **entry.data, **entry.options}
    rule_store = HomeAssistantRuleStore(hass, RULES_STORAGE_KEY, STATE_STORAGE_KEY)
    history_path = Path(hass.config.path("industrial_alarm_panel_history.db"))
    history_store = SQLiteHistoryStore(history_path)
    await history_store.async_setup()

    warned_missing_url = False

    async def _media_call(rule_id: str, priority: Any) -> None:
        nonlocal warned_missing_url
        media_players = options.get(CONF_MEDIA_PLAYERS) or []
        if not media_players:
            return
        content_id = media_content_id(options.get(CONF_MEDIA_SOUND_URL, ""), priority)
        if content_id is None:
            if not warned_missing_url:
                warned_missing_url = True
                _LOGGER.warning(
                    "Media player alarm sound is enabled but no media sound URL is "
                    "configured; set 'Media sound URL' in the integration options"
                )
            return
        await hass.services.async_call(
            "media_player",
            "play_media",
            target={"entity_id": media_players},
            service_data={
                "media_content_id": content_id,
                "media_content_type": "music",
            },
            blocking=False,
        )

    sound_manager = AlarmSoundManager(
        sound_mode=options.get(CONF_SOUND_MODE, DEFAULT_OPTIONS[CONF_SOUND_MODE]),
        repeat_interval_seconds=int(
            options.get(
                CONF_REPEAT_INTERVAL_SECONDS,
                DEFAULT_OPTIONS[CONF_REPEAT_INTERVAL_SECONDS],
            )
        ),
        repeat_until_silenced=bool(
            options.get(
                CONF_REPEAT_UNTIL_SILENCED, DEFAULT_OPTIONS[CONF_REPEAT_UNTIL_SILENCED]
            )
        ),
        media_players=list(options.get(CONF_MEDIA_PLAYERS, [])),
        media_call=_media_call,
        now=dt_util.utcnow,
    )
    engine = await AlarmEngine.from_store(
        rule_store,
        history_store,
        sound_manager=sound_manager,
        now=dt_util.utcnow,
        alarm_flood_threshold=int(options[CONF_ALARM_FLOOD_THRESHOLD]),
        alarm_flood_window_seconds=int(options[CONF_ALARM_FLOOD_WINDOW_SECONDS]),
        auto_shelve_flapping=bool(options[CONF_AUTO_SHELVE_FLAPPING]),
        flapping_threshold=int(options[CONF_FLAPPING_DETECTION_THRESHOLD]),
        store_normal_events=bool(options[CONF_STORE_NORMAL_EVENTS]),
        default_delay_on_seconds=int(options[CONF_DEFAULT_DELAY_ON] or 0),
        default_delay_off_seconds=int(options[CONF_DEFAULT_DELAY_OFF] or 0),
        default_deadband=float(options[CONF_DEFAULT_DEADBAND] or 0),
    )

    runtime = IndustrialAlarmPanelRuntime(
        entry_id=entry.entry_id,
        rule_store=rule_store,
        history_store=history_store,
        sound_manager=sound_manager,
        engine=engine,
        hass=hass,
        options=options,
    )
    entry.runtime_data = runtime
    runtime.remove_frontend_update_listener = attach_alarm_update_event_listener(
        hass, entry.entry_id, engine
    )

    # One timer covers delayed alarm transitions, shelve expiry and horn timers.
    def _next_due_at() -> datetime | None:
        due_times = [
            due
            for due in (engine.next_due_transition_at(), sound_manager.next_timer_due())
            if due is not None
        ]
        return min(due_times) if due_times else None

    @callback
    def _reschedule_delay_timer() -> None:
        if runtime.remove_delay_timer:
            runtime.remove_delay_timer()
            runtime.remove_delay_timer = None
        if runtime.reschedule_timers is None:
            return  # unloading

        due_at = _next_due_at()
        if due_at is None:
            return

        delay_seconds = max(0.0, (due_at - dt_util.utcnow()).total_seconds())
        runtime.remove_delay_timer = async_call_later(
            hass, delay_seconds, _delay_timer_due
        )

    async def _process_delay_timer() -> None:
        try:
            await engine.process_due_transitions()
            await engine.async_process_sound_timers()
        finally:
            _reschedule_delay_timer()

    @callback
    def _delay_timer_due(_now: datetime) -> None:
        runtime.remove_delay_timer = None
        entry.async_create_task(
            hass, _process_delay_timer(), f"{DOMAIN} due transitions"
        )

    # Any committed change (ack, silence, new alarm...) may move the next due time.
    remove_reschedule_listener = engine.add_listener(_reschedule_delay_timer)

    async def _process_state_change(entity_id: str, state: Any) -> None:
        await engine.process_state(entity_id, state)

    @callback
    def _state_changed(event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        entry.async_create_task(
            hass,
            _process_state_change(new_state.entity_id, new_state.state),
            f"{DOMAIN} state change",
        )

    def _subscribe(entity_ids: list[str]) -> Any:
        return async_track_state_change_event(hass, entity_ids, _state_changed)

    runtime.reschedule_timers = _reschedule_delay_timer
    runtime.state_listener_factory = _subscribe
    runtime.refresh_state_listener()

    runtime.remove_retention_timer = schedule_history_retention(
        hass,
        history_store,
        int(options[CONF_HISTORY_RETENTION_DAYS]),
        async_track_time_interval,
    )

    runtime.remove_panel = await async_register_panel(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Raise alarms for sources that are already out of range (setup or reload).
    await engine.async_evaluate_sources(runtime.get_source_state)
    _reschedule_delay_timer()

    entry.async_on_unload(remove_reschedule_listener)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: IndustrialAlarmConfigEntry
) -> bool:
    """Unload a config entry."""

    runtime = entry.runtime_data
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        if runtime.remove_state_listener:
            runtime.remove_state_listener()
            runtime.remove_state_listener = None
        runtime.state_listener_factory = None
        runtime.reschedule_timers = None
        if runtime.remove_delay_timer:
            runtime.remove_delay_timer()
            runtime.remove_delay_timer = None
        if runtime.remove_retention_timer:
            runtime.remove_retention_timer()
            runtime.remove_retention_timer = None
        if runtime.remove_frontend_update_listener:
            runtime.remove_frontend_update_listener()
        if runtime.remove_panel:
            try:
                runtime.remove_panel()
            except Exception:  # pragma: no cover - HA frontend API compatibility
                _LOGGER.debug("Panel unregister callback failed", exc_info=True)
        await runtime.engine.async_shutdown()
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: IndustrialAlarmConfigEntry
) -> None:
    """Reload entry when options change."""

    await hass.config_entries.async_reload(entry.entry_id)
