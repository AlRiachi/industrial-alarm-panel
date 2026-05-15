"""Constants for Industrial Alarm Panel."""

from __future__ import annotations

from enum import StrEnum

try:
    from homeassistant.const import Platform
except ModuleNotFoundError:  # Allows pure unit tests without Home Assistant installed.
    class Platform(StrEnum):
        """Subset of HA platform names used by this integration."""

        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        SWITCH = "switch"
        SELECT = "select"
        NUMBER = "number"

DOMAIN = "industrial_alarm_panel"
NAME = "Industrial Alarm Panel"
VERSION = "1.0.8"
EVENT_ALARMS_UPDATED = f"{DOMAIN}_alarms_updated"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
]

RULES_STORAGE_KEY = f"{DOMAIN}.rules"
STATE_STORAGE_KEY = f"{DOMAIN}.state"
RULES_STORAGE_VERSION = 1
STATE_STORAGE_VERSION = 1

PANEL_URL = "industrial-alarms"
PANEL_TITLE = "Industrial Alarms"
PANEL_ICON = "mdi:alarm-light"
FRONTEND_MODULE = f"/{DOMAIN}/frontend/dist/industrial-alarm-panel.js?v={VERSION}"

SERVICE_ACKNOWLEDGE_ALARM = "acknowledge_alarm"
SERVICE_ACKNOWLEDGE_ALL = "acknowledge_all"
SERVICE_SILENCE_HORN = "silence_horn"
SERVICE_UNSILENCE_HORN = "unsilence_horn"
SERVICE_SHELVE_ALARM = "shelve_alarm"
SERVICE_UNSHELVE_ALARM = "unshelve_alarm"
SERVICE_DISABLE_ALARM = "disable_alarm"
SERVICE_ENABLE_ALARM = "enable_alarm"
SERVICE_CREATE_RULE = "create_rule"
SERVICE_UPDATE_RULE = "update_rule"
SERVICE_DELETE_RULE = "delete_rule"
SERVICE_TEST_SOUND = "test_sound"
SERVICE_EXPORT_HISTORY = "export_history"

CONF_INSTANCE_NAME = "instance_name"
CONF_ENABLE_PANEL = "enable_panel"
CONF_ENABLE_BROWSER_SOUND = "enable_browser_sound"
CONF_ENABLE_MEDIA_PLAYER_SOUND = "enable_media_player_sound"
CONF_HISTORY_RETENTION_DAYS = "history_retention_days"
CONF_MAX_ACTIVE_ALARMS = "max_active_alarms"
CONF_MAX_HISTORY_ROWS = "max_history_rows"
CONF_SOUND_MODE = "sound_mode"
CONF_MEDIA_PLAYERS = "media_players"
CONF_REPEAT_UNTIL_SILENCED = "repeat_until_silenced"
CONF_REPEAT_INTERVAL_SECONDS = "repeat_interval_seconds"
CONF_AUTO_HIDE_CLEARED_ACK = "auto_hide_cleared_acknowledged"
CONF_SHOW_CLEARED_UNACK = "show_cleared_unacknowledged"
CONF_ENABLE_FLASHING = "enable_flashing"
CONF_COMPACT_MODE = "enable_compact_mode"
CONF_PANEL_TITLE = "panel_title"
CONF_DEFAULT_TAB = "default_tab"
CONF_STORE_STATUS_CHANGES = "store_status_changes"
CONF_STORE_NORMAL_EVENTS = "store_normal_events"
CONF_REQUIRE_ACK_CLEARED = "require_acknowledgement_for_cleared"
CONF_DEFAULT_DELAY_ON = "default_delay_on_seconds"
CONF_DEFAULT_DELAY_OFF = "default_delay_off_seconds"
CONF_DEFAULT_DEADBAND = "default_deadband"
CONF_ALARM_FLOOD_THRESHOLD = "alarm_flood_threshold"
CONF_ALARM_FLOOD_WINDOW_SECONDS = "alarm_flood_window_seconds"
CONF_AUTO_SHELVE_FLAPPING = "auto_shelve_flapping_alarms"
CONF_FLAPPING_DETECTION_THRESHOLD = "flapping_detection_threshold"
CONF_GROUP_BY = "group_by"

SOUND_MODE_NONE = "none"
SOUND_MODE_BROWSER_ONLY = "browser_only"
SOUND_MODE_MEDIA_PLAYER_ONLY = "media_player_only"
SOUND_MODE_BROWSER_AND_MEDIA = "browser_and_media_player"
SOUND_MODES = [
    SOUND_MODE_NONE,
    SOUND_MODE_BROWSER_ONLY,
    SOUND_MODE_MEDIA_PLAYER_ONLY,
    SOUND_MODE_BROWSER_AND_MEDIA,
]

DEFAULT_OPTIONS = {
    CONF_MAX_ACTIVE_ALARMS: 250,
    CONF_MAX_HISTORY_ROWS: 1000,
    CONF_HISTORY_RETENTION_DAYS: 90,
    CONF_STORE_STATUS_CHANGES: True,
    CONF_STORE_NORMAL_EVENTS: False,
    CONF_AUTO_HIDE_CLEARED_ACK: True,
    CONF_SHOW_CLEARED_UNACK: True,
    CONF_REQUIRE_ACK_CLEARED: True,
    CONF_SOUND_MODE: SOUND_MODE_BROWSER_ONLY,
    CONF_MEDIA_PLAYERS: [],
    CONF_REPEAT_UNTIL_SILENCED: True,
    CONF_REPEAT_INTERVAL_SECONDS: 30,
    CONF_DEFAULT_DELAY_ON: 0,
    CONF_DEFAULT_DELAY_OFF: 0,
    CONF_DEFAULT_DEADBAND: 0,
    CONF_ALARM_FLOOD_THRESHOLD: 25,
    CONF_ALARM_FLOOD_WINDOW_SECONDS: 60,
    CONF_AUTO_SHELVE_FLAPPING: False,
    CONF_FLAPPING_DETECTION_THRESHOLD: 6,
    CONF_PANEL_TITLE: PANEL_TITLE,
    CONF_DEFAULT_TAB: "active",
    CONF_ENABLE_FLASHING: True,
    CONF_COMPACT_MODE: False,
    CONF_GROUP_BY: "priority",
}

DEFAULT_DATA = {
    CONF_INSTANCE_NAME: NAME,
    CONF_ENABLE_PANEL: True,
    CONF_ENABLE_BROWSER_SOUND: True,
    CONF_ENABLE_MEDIA_PLAYER_SOUND: False,
    CONF_HISTORY_RETENTION_DAYS: DEFAULT_OPTIONS[CONF_HISTORY_RETENTION_DAYS],
    CONF_MAX_ACTIVE_ALARMS: DEFAULT_OPTIONS[CONF_MAX_ACTIVE_ALARMS],
    CONF_MAX_HISTORY_ROWS: DEFAULT_OPTIONS[CONF_MAX_HISTORY_ROWS],
}
