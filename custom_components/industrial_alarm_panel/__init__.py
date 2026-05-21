"""Industrial Alarm Panel integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .alarm_engine import AlarmEngine
from .alarm_sound import AlarmSoundManager
from .alarm_store import HomeAssistantRuleStore, SQLiteHistoryStore
from .const import (
    CONF_ALARM_FLOOD_THRESHOLD,
    CONF_ALARM_FLOOD_WINDOW_SECONDS,
    CONF_AUTO_SHELVE_FLAPPING,
    CONF_HISTORY_RETENTION_DAYS,
    CONF_MEDIA_PLAYERS,
    CONF_REPEAT_INTERVAL_SECONDS,
    CONF_SOUND_MODE,
    DEFAULT_OPTIONS,
    DOMAIN,
    PLATFORMS,
    RULES_STORAGE_KEY,
    STATE_STORAGE_KEY,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class IndustrialAlarmPanelRuntime:
    """Runtime objects for one config entry."""

    entry_id: str
    rule_store: HomeAssistantRuleStore
    history_store: SQLiteHistoryStore
    sound_manager: AlarmSoundManager
    engine: AlarmEngine
    remove_state_listener: Any | None = None
    remove_delay_timer: Any | None = None
    remove_frontend_update_listener: Any | None = None
    remove_panel: Any | None = None


IndustrialAlarmConfigEntry = Any


async def async_setup_entry(
    hass: HomeAssistant, entry: IndustrialAlarmConfigEntry
) -> bool:
    """Set up Industrial Alarm Panel from a config entry."""

    from homeassistant.core import Event, callback
    from homeassistant.helpers.event import (
        async_call_later,
        async_track_state_change_event,
    )

    from .alarm_panel import async_register_panel
    from .frontend_events import attach_alarm_update_event_listener
    from .services import async_setup_services
    from .websocket_api import async_register_websocket_api

    options = {**DEFAULT_OPTIONS, **entry.data, **entry.options}
    rule_store = HomeAssistantRuleStore(hass, RULES_STORAGE_KEY, STATE_STORAGE_KEY)
    history_path = Path(hass.config.path("industrial_alarm_panel_history.db"))
    history_store = SQLiteHistoryStore(history_path)
    await history_store.async_setup()

    async def _media_call(rule_id: str, priority: Any) -> None:
        media_players = options.get(CONF_MEDIA_PLAYERS) or []
        if not media_players:
            return
        media_content_id = (
            f"/local/industrial_alarm_panel/sounds/{priority.value}.mp3"
        )
        await hass.services.async_call(
            "media_player",
            "play_media",
            target={"entity_id": media_players},
            service_data={
                "media_content_id": media_content_id,
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
        media_players=list(options.get(CONF_MEDIA_PLAYERS, [])),
        media_call=_media_call,
    )
    engine = await AlarmEngine.from_store(
        rule_store,
        history_store,
        sound_manager=sound_manager,
    )
    engine.alarm_flood_threshold = int(
        options.get(CONF_ALARM_FLOOD_THRESHOLD, DEFAULT_OPTIONS[CONF_ALARM_FLOOD_THRESHOLD])
    )
    engine.alarm_flood_window_seconds = int(
        options.get(
            CONF_ALARM_FLOOD_WINDOW_SECONDS,
            DEFAULT_OPTIONS[CONF_ALARM_FLOOD_WINDOW_SECONDS],
        )
    )
    engine.auto_shelve_flapping = bool(
        options.get(CONF_AUTO_SHELVE_FLAPPING, DEFAULT_OPTIONS[CONF_AUTO_SHELVE_FLAPPING])
    )

    runtime = IndustrialAlarmPanelRuntime(
        entry_id=entry.entry_id,
        rule_store=rule_store,
        history_store=history_store,
        sound_manager=sound_manager,
        engine=engine,
    )
    entry.runtime_data = runtime
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    runtime.remove_frontend_update_listener = attach_alarm_update_event_listener(
        hass, entry.entry_id, engine
    )

    def _reschedule_delay_timer() -> None:
        if runtime.remove_delay_timer:
            runtime.remove_delay_timer()
            runtime.remove_delay_timer = None

        due_at = engine.next_due_transition_at()
        if due_at is None:
            return

        delay_seconds = max(0.0, (due_at - datetime.now(UTC)).total_seconds())
        runtime.remove_delay_timer = async_call_later(
            hass, delay_seconds, _delay_timer_due
        )

    async def _process_delay_timer() -> None:
        await engine.process_due_transitions()
        _reschedule_delay_timer()

    @callback
    def _delay_timer_due(_now: datetime) -> None:
        runtime.remove_delay_timer = None
        hass.async_create_task(_process_delay_timer())

    async def _process_state_change(entity_id: str, state: Any) -> None:
        await engine.process_state(entity_id, state)
        _reschedule_delay_timer()

    tracked_entities = sorted(
        {rule.entity_id for rule in engine.rules.values() if rule.entity_id}
    )
    if tracked_entities:

        @callback
        def _state_changed(event: Event) -> None:
            new_state = event.data.get("new_state")
            if new_state is None:
                return
            hass.async_create_task(
                _process_state_change(new_state.entity_id, new_state.state)
            )

        runtime.remove_state_listener = async_track_state_change_event(
            hass, tracked_entities, _state_changed
        )

    _reschedule_delay_timer()

    await async_setup_services(hass)
    async_register_websocket_api(hass)
    runtime.remove_panel = await async_register_panel(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(lambda: hass.data[DOMAIN].pop(entry.entry_id, None))
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
        if runtime.remove_delay_timer:
            runtime.remove_delay_timer()
        if runtime.remove_frontend_update_listener:
            runtime.remove_frontend_update_listener()
        if runtime.remove_panel:
            try:
                runtime.remove_panel()
            except Exception:  # pragma: no cover - HA frontend API compatibility
                _LOGGER.debug("Panel unregister callback failed", exc_info=True)
        await runtime.engine.async_shutdown()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: IndustrialAlarmConfigEntry
) -> None:
    """Reload entry when options change."""

    await hass.config_entries.async_reload(entry.entry_id)
