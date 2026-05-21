"""Alarm models and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import re
from typing import Any


class AlarmValidationError(ValueError):
    """Raised when an alarm rule is invalid."""


class AlarmPriority(StrEnum):
    """DCS alarm priority levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    STATUS = "status"


class AlarmLifecycleState(StrEnum):
    """DCS alarm lifecycle states."""

    NORMAL = "NORMAL"
    ACTIVE_UNACK = "ACTIVE_UNACK"
    ACTIVE_ACK = "ACTIVE_ACK"
    CLEARED_UNACK = "CLEARED_UNACK"
    CLEARED_ACK = "CLEARED_ACK"
    SHELVED = "SHELVED"
    DISABLED = "DISABLED"
    SUPPRESSED = "SUPPRESSED"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class AlarmCondition(StrEnum):
    """Supported alarm condition types."""

    ABOVE = "above"
    BELOW = "below"
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    CONTAINS = "contains"
    IS_ON = "is_on"
    IS_OFF = "is_off"
    STATE_CHANGED = "state_changed"
    UNAVAILABLE = "unavailable"
    UNAVAILABLE_FOR = "unavailable_for"
    UNKNOWN_FOR = "unknown_for"
    MANUAL = "manual"


class AlarmEventType(StrEnum):
    """History event types."""

    ACTIVATED = "activated"
    CLEARED = "cleared"
    ACKNOWLEDGED = "acknowledged"
    SILENCED = "silenced"
    UNSILENCED = "unsilenced"
    SHELVED = "shelved"
    UNSHELVED = "unshelved"
    DISABLED = "disabled"
    ENABLED = "enabled"
    SUPPRESSED = "suppressed"
    UNSUPPRESSED = "unsuppressed"
    STATUS_CHANGED = "status_changed"
    RULE_CREATED = "rule_created"
    RULE_UPDATED = "rule_updated"
    RULE_DELETED = "rule_deleted"
    SOUND_STARTED = "sound_started"
    SOUND_STOPPED = "sound_stopped"
    FLOOD_DETECTED = "alarm_flood_detected"
    FLAPPING_DETECTED = "flapping_detected"


PRIORITY_PROFILES: dict[AlarmPriority, dict[str, Any]] = {
    AlarmPriority.CRITICAL: {
        "label": "Critical",
        "severity": 100,
        "color": "#e31b23",
        "flash": True,
        "sound_profile": "critical",
        "requires_ack": True,
        "visible_by_default": True,
    },
    AlarmPriority.HIGH: {
        "label": "High",
        "severity": 80,
        "color": "#ff8c00",
        "flash": True,
        "sound_profile": "high",
        "requires_ack": True,
        "visible_by_default": True,
    },
    AlarmPriority.MEDIUM: {
        "label": "Medium",
        "severity": 60,
        "color": "#ffd400",
        "flash": True,
        "sound_profile": "medium",
        "requires_ack": True,
        "visible_by_default": True,
    },
    AlarmPriority.LOW: {
        "label": "Low",
        "severity": 40,
        "color": "#3f8cff",
        "flash": False,
        "sound_profile": "low",
        "requires_ack": True,
        "visible_by_default": True,
    },
    AlarmPriority.INFO: {
        "label": "Info",
        "severity": 20,
        "color": "#8aa4b2",
        "flash": False,
        "sound_profile": "info",
        "requires_ack": False,
        "visible_by_default": False,
    },
    AlarmPriority.STATUS: {
        "label": "Status",
        "severity": 10,
        "color": "#54c6d6",
        "flash": False,
        "sound_profile": "info",
        "requires_ack": False,
        "visible_by_default": False,
    },
}

NUMERIC_CONDITIONS = {AlarmCondition.ABOVE, AlarmCondition.BELOW}
UNAVAILABLE_STATES = {"unavailable", "unknown", "none", ""}


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "alarm"


def _coerce_priority(value: str | AlarmPriority | None) -> AlarmPriority:
    if value is None:
        return AlarmPriority.MEDIUM
    if isinstance(value, AlarmPriority):
        return value
    try:
        return AlarmPriority(str(value))
    except ValueError as exc:
        raise AlarmValidationError(f"Unsupported priority: {value}") from exc


def _coerce_condition(value: str | AlarmCondition | None) -> AlarmCondition:
    if value is None:
        raise AlarmValidationError("condition is required")
    if isinstance(value, AlarmCondition):
        return value
    try:
        return AlarmCondition(str(value))
    except ValueError as exc:
        raise AlarmValidationError(f"Unsupported condition: {value}") from exc


def _coerce_float(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AlarmValidationError(f"{field_name} must be numeric") from exc


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return None


def _format_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(slots=True)
class AlarmRule:
    """Stored alarm rule definition."""

    id: str
    entity_id: str
    name: str
    condition: AlarmCondition
    enabled: bool = True
    tag: str | None = None
    area: str | None = None
    system: str | None = None
    description: str | None = None
    threshold: float | str | None = None
    deadband: float = 0.0
    priority: AlarmPriority = AlarmPriority.MEDIUM
    requires_ack: bool = True
    audible: bool = True
    sound_profile: str | None = None
    delay_on_seconds: int = 0
    delay_off_seconds: int = 0
    min_active_duration_seconds: int = 0
    repeat_alarm_after_seconds: int = 0
    show_when_cleared: bool = True
    auto_ack_on_clear: bool = False
    shelving_allowed: bool = True
    instructions: str | None = None
    duration: int | None = None
    template: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def slug(self) -> str:
        """Return a stable entity suffix for this rule."""

        return _slugify(self.id)

    @property
    def severity(self) -> int:
        """Return numeric severity."""

        return int(PRIORITY_PROFILES[self.priority]["severity"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlarmRule":
        """Create and validate a rule from stored data or service input."""

        rule_id = str(data.get("id") or "").strip()
        entity_id = str(data.get("entity_id") or "").strip()
        name = str(data.get("name") or "").strip()
        condition = _coerce_condition(data.get("condition"))
        priority = _coerce_priority(data.get("priority"))
        threshold = data.get("threshold")

        if not rule_id:
            raise AlarmValidationError("id is required")
        if condition != AlarmCondition.MANUAL and not entity_id:
            raise AlarmValidationError("entity_id is required")
        if not name:
            raise AlarmValidationError("name is required")
        if condition in NUMERIC_CONDITIONS and threshold is None:
            raise AlarmValidationError("threshold is required for numeric conditions")

        numeric_threshold = _coerce_float(threshold, "threshold")
        deadband = _coerce_float(data.get("deadband", 0), "deadband") or 0.0
        sound_profile = data.get("sound_profile") or PRIORITY_PROFILES[priority]["sound_profile"]

        return cls(
            id=rule_id,
            entity_id=entity_id,
            name=name,
            condition=condition,
            enabled=bool(data.get("enabled", True)),
            tag=data.get("tag"),
            area=data.get("area"),
            system=data.get("system"),
            description=data.get("description"),
            threshold=numeric_threshold if numeric_threshold is not None else threshold,
            deadband=deadband,
            priority=priority,
            requires_ack=bool(
                data.get("requires_ack", PRIORITY_PROFILES[priority]["requires_ack"])
            ),
            audible=bool(data.get("audible", True)),
            sound_profile=str(sound_profile),
            delay_on_seconds=int(data.get("delay_on_seconds", 0) or 0),
            delay_off_seconds=int(data.get("delay_off_seconds", 0) or 0),
            min_active_duration_seconds=int(
                data.get("min_active_duration_seconds", 0) or 0
            ),
            repeat_alarm_after_seconds=int(
                data.get("repeat_alarm_after_seconds", 0) or 0
            ),
            show_when_cleared=bool(data.get("show_when_cleared", True)),
            auto_ack_on_clear=bool(data.get("auto_ack_on_clear", False)),
            shelving_allowed=bool(data.get("shelving_allowed", True)),
            instructions=data.get("instructions"),
            duration=int(data["duration"]) if data.get("duration") is not None else None,
            template=data.get("template"),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the rule for storage."""

        return {
            "id": self.id,
            "enabled": self.enabled,
            "entity_id": self.entity_id,
            "name": self.name,
            "tag": self.tag,
            "area": self.area,
            "system": self.system,
            "description": self.description,
            "condition": self.condition.value,
            "threshold": self.threshold,
            "deadband": self.deadband,
            "priority": self.priority.value,
            "requires_ack": self.requires_ack,
            "audible": self.audible,
            "sound_profile": self.sound_profile,
            "delay_on_seconds": self.delay_on_seconds,
            "delay_off_seconds": self.delay_off_seconds,
            "min_active_duration_seconds": self.min_active_duration_seconds,
            "repeat_alarm_after_seconds": self.repeat_alarm_after_seconds,
            "show_when_cleared": self.show_when_cleared,
            "auto_ack_on_clear": self.auto_ack_on_clear,
            "shelving_allowed": self.shelving_allowed,
            "instructions": self.instructions,
            "duration": self.duration,
            "template": self.template,
            "created_at": _format_datetime(self.created_at),
            "updated_at": _format_datetime(self.updated_at),
        }


@dataclass(slots=True)
class AlarmRuntimeState:
    """Runtime state persisted across Home Assistant restarts."""

    rule_id: str
    lifecycle_state: AlarmLifecycleState = AlarmLifecycleState.NORMAL
    active_timestamp: datetime | None = None
    clear_timestamp: datetime | None = None
    ack_timestamp: datetime | None = None
    ack_user: str | None = None
    shelve_expiry: datetime | None = None
    last_sound_timestamp: datetime | None = None
    last_value: Any = None
    last_state: str | None = None
    previous_lifecycle_state: AlarmLifecycleState | None = None
    pending_active_since: datetime | None = None
    pending_clear_since: datetime | None = None
    transition_timestamps: list[datetime] = field(default_factory=list)

    @property
    def acknowledged(self) -> bool:
        """Return if the current alarm has operator acknowledgement."""

        return self.lifecycle_state in {
            AlarmLifecycleState.ACTIVE_ACK,
            AlarmLifecycleState.CLEARED_ACK,
        }

    @property
    def is_active(self) -> bool:
        """Return true if this state represents an active alarm."""

        return self.lifecycle_state in {
            AlarmLifecycleState.ACTIVE_UNACK,
            AlarmLifecycleState.ACTIVE_ACK,
        }

    @property
    def is_unacknowledged(self) -> bool:
        """Return true if this state requires acknowledgement."""

        return self.lifecycle_state in {
            AlarmLifecycleState.ACTIVE_UNACK,
            AlarmLifecycleState.CLEARED_UNACK,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize runtime state."""

        return {
            "rule_id": self.rule_id,
            "lifecycle_state": self.lifecycle_state.value,
            "active_timestamp": _format_datetime(self.active_timestamp),
            "clear_timestamp": _format_datetime(self.clear_timestamp),
            "ack_timestamp": _format_datetime(self.ack_timestamp),
            "ack_user": self.ack_user,
            "shelve_expiry": _format_datetime(self.shelve_expiry),
            "last_sound_timestamp": _format_datetime(self.last_sound_timestamp),
            "last_value": self.last_value,
            "last_state": self.last_state,
            "previous_lifecycle_state": self.previous_lifecycle_state.value
            if self.previous_lifecycle_state
            else None,
            "pending_active_since": _format_datetime(self.pending_active_since),
            "pending_clear_since": _format_datetime(self.pending_clear_since),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlarmRuntimeState":
        """Deserialize runtime state."""

        return cls(
            rule_id=str(data["rule_id"]),
            lifecycle_state=AlarmLifecycleState(data.get("lifecycle_state", "NORMAL")),
            active_timestamp=_parse_datetime(data.get("active_timestamp")),
            clear_timestamp=_parse_datetime(data.get("clear_timestamp")),
            ack_timestamp=_parse_datetime(data.get("ack_timestamp")),
            ack_user=data.get("ack_user"),
            shelve_expiry=_parse_datetime(data.get("shelve_expiry")),
            last_sound_timestamp=_parse_datetime(data.get("last_sound_timestamp")),
            last_value=data.get("last_value"),
            last_state=data.get("last_state"),
            previous_lifecycle_state=AlarmLifecycleState(
                data["previous_lifecycle_state"]
            )
            if data.get("previous_lifecycle_state")
            else None,
            pending_active_since=_parse_datetime(data.get("pending_active_since")),
            pending_clear_since=_parse_datetime(data.get("pending_clear_since")),
        )


@dataclass(slots=True)
class AlarmEvaluationResult:
    """Result from evaluating a rule against a Home Assistant state."""

    matched: bool
    source_state: str
    source_value: Any = None
    message: str | None = None
    reason: str | None = None


@dataclass(slots=True)
class AlarmEvent:
    """History event row."""

    rule_id: str | None
    entity_id: str | None
    event_type: str
    timestamp: datetime
    id: int | None = None
    tag: str | None = None
    name: str | None = None
    area: str | None = None
    system: str | None = None
    priority: str | None = None
    previous_state: str | None = None
    new_state: str | None = None
    source_state: str | None = None
    source_value: Any = None
    message: str | None = None
    operator: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event for APIs and diagnostics."""

        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "entity_id": self.entity_id,
            "tag": self.tag,
            "name": self.name,
            "area": self.area,
            "system": self.system,
            "priority": self.priority,
            "event_type": self.event_type,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "source_state": self.source_state,
            "source_value": self.source_value,
            "message": self.message,
            "operator": self.operator,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
