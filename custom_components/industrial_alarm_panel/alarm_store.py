"""Alarm rule, runtime, and history storage."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any

from .alarm_models import AlarmEvent, AlarmRule, AlarmRuntimeState

_LOGGER = logging.getLogger(__name__)

#: Runtime state is written at most once per this many seconds (debounced).
STATE_SAVE_DELAY_SECONDS = 3
#: How often history retention cleanup runs.
RETENTION_INTERVAL = timedelta(days=1)

SoundStateFn = Callable[[], dict[str, Any]]

SCHEMA = """
CREATE TABLE IF NOT EXISTS alarm_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id TEXT,
  entity_id TEXT,
  tag TEXT,
  name TEXT,
  area TEXT,
  system TEXT,
  priority TEXT,
  event_type TEXT NOT NULL,
  previous_state TEXT,
  new_state TEXT,
  source_state TEXT,
  source_value TEXT,
  message TEXT,
  operator TEXT,
  timestamp TEXT NOT NULL,
  metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_alarm_events_timestamp
  ON alarm_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_alarm_events_rule_id
  ON alarm_events(rule_id);
CREATE TABLE IF NOT EXISTS alarm_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_json TEXT NOT NULL,
  timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operator_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  rule_id TEXT,
  operator TEXT,
  comment TEXT,
  timestamp TEXT NOT NULL,
  metadata_json TEXT
);
"""


class InMemoryHistoryStore:
    """Small async-compatible history store used by tests and fallback paths."""

    def __init__(self) -> None:
        self.events: list[AlarmEvent] = []

    async def async_setup(self) -> None:
        """Prepare the store."""

    async def add_event(self, event: AlarmEvent) -> None:
        """Add a history event."""

        self.events.append(replace(event, id=len(self.events) + 1))

    async def query_events(
        self,
        *,
        limit: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        **filters: Any,
    ) -> list[AlarmEvent]:
        """Query events newest first."""

        events = list(self.events)
        if start_time:
            events = [event for event in events if event.timestamp >= start_time]
        if end_time:
            events = [event for event in events if event.timestamp <= end_time]
        for field, value in filters.items():
            if value is not None:
                events = [event for event in events if getattr(event, field) == value]
        events.sort(key=lambda event: event.timestamp, reverse=True)
        return events[:limit] if limit else events

    async def cleanup_retention(
        self, retention_days: int, now: datetime | None = None
    ) -> int:
        """Delete events older than retention_days."""

        cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
        before = len(self.events)
        self.events = [event for event in self.events if event.timestamp >= cutoff]
        return before - len(self.events)

    async def close(self) -> None:
        """Close resources."""


class SQLiteHistoryStore:
    """SQLite-backed alarm history store.

    Operations are dispatched to a worker thread so Home Assistant's event loop is
    not blocked by disk I/O.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def async_setup(self) -> None:
        """Create the history database schema."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._setup_sync)

    def _setup_sync(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.executescript(SCHEMA)

    async def add_event(self, event: AlarmEvent) -> None:
        """Insert one history event."""

        await asyncio.to_thread(self._add_event_sync, event)

    def _add_event_sync(self, event: AlarmEvent) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO alarm_events (
                  rule_id, entity_id, tag, name, area, system, priority,
                  event_type, previous_state, new_state, source_state, source_value,
                  message, operator, timestamp, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.rule_id,
                    event.entity_id,
                    event.tag,
                    event.name,
                    event.area,
                    event.system,
                    event.priority,
                    event.event_type,
                    event.previous_state,
                    event.new_state,
                    event.source_state,
                    json.dumps(event.source_value)
                    if event.source_value is not None
                    else None,
                    event.message,
                    event.operator,
                    event.timestamp.isoformat(),
                    json.dumps(event.metadata),
                ),
            )

    async def query_events(
        self,
        *,
        limit: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        rule_id: str | None = None,
        priority: str | None = None,
        area: str | None = None,
        system: str | None = None,
        event_type: str | None = None,
    ) -> list[AlarmEvent]:
        """Query history events newest first."""

        return await asyncio.to_thread(
            self._query_events_sync,
            limit,
            start_time,
            end_time,
            rule_id,
            priority,
            area,
            system,
            event_type,
        )

    def _query_events_sync(
        self,
        limit: int | None,
        start_time: datetime | None,
        end_time: datetime | None,
        rule_id: str | None,
        priority: str | None,
        area: str | None,
        system: str | None,
        event_type: str | None,
    ) -> list[AlarmEvent]:
        clauses: list[str] = []
        params: list[Any] = []
        filter_map = {
            "rule_id": rule_id,
            "priority": priority,
            "area": area,
            "system": system,
            "event_type": event_type,
        }
        for key, value in filter_map.items():
            if value is not None:
                clauses.append(f"{key} = ?")
                params.append(value)
        if start_time is not None:
            clauses.append("timestamp >= ?")
            params.append(start_time.isoformat())
        if end_time is not None:
            clauses.append("timestamp <= ?")
            params.append(end_time.isoformat())
        query = "SELECT * FROM alarm_events"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp DESC, id DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, params).fetchall()
        return [_event_from_row(row) for row in rows]

    async def cleanup_retention(
        self, retention_days: int, now: datetime | None = None
    ) -> int:
        """Delete old events and return the deleted count."""

        cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
        return await asyncio.to_thread(self._cleanup_retention_sync, cutoff)

    def _cleanup_retention_sync(self, cutoff: datetime) -> int:
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                "DELETE FROM alarm_events WHERE timestamp < ?",
                (cutoff.isoformat(),),
            )
            return cursor.rowcount

    async def close(self) -> None:
        """Close resources."""


def _event_from_row(row: sqlite3.Row) -> AlarmEvent:
    metadata = json.loads(row["metadata_json"] or "{}")
    source_value = (
        json.loads(row["source_value"]) if row["source_value"] is not None else None
    )
    return AlarmEvent(
        id=row["id"],
        rule_id=row["rule_id"],
        entity_id=row["entity_id"],
        tag=row["tag"],
        name=row["name"],
        area=row["area"],
        system=row["system"],
        priority=row["priority"],
        event_type=row["event_type"],
        previous_state=row["previous_state"],
        new_state=row["new_state"],
        source_state=row["source_state"],
        source_value=source_value,
        message=row["message"],
        operator=row["operator"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        metadata=metadata,
    )


class MemoryRuleStore:
    """Rule and runtime state store used when HA storage is unavailable."""

    def __init__(
        self,
        rules: Iterable[AlarmRule] | None = None,
        states: Iterable[AlarmRuntimeState] | None = None,
    ) -> None:
        self._rules = {rule.id: rule for rule in rules or []}
        self._states = {state.rule_id: state for state in states or []}
        self.sound_state: dict[str, Any] = {}
        self.sound_state_fn: SoundStateFn | None = None
        self.save_count = 0

    async def async_load_rules(self) -> list[AlarmRule]:
        """Load rules."""

        return list(self._rules.values())

    async def async_save_rules(self, rules: Iterable[AlarmRule]) -> None:
        """Persist rules."""

        self._rules = {rule.id: rule for rule in rules}

    async def async_load_states(self) -> dict[str, AlarmRuntimeState]:
        """Load runtime states."""

        return dict(self._states)

    async def async_save_states(
        self, states: dict[str, AlarmRuntimeState]
    ) -> None:
        """Persist runtime states."""

        self.save_count += 1
        self._states = dict(states)
        if self.sound_state_fn is not None:
            self.sound_state = self.sound_state_fn()

    async def async_flush_states(
        self, states: dict[str, AlarmRuntimeState]
    ) -> None:
        """Persist runtime states immediately."""

        await self.async_save_states(states)


class HomeAssistantRuleStore:
    """Home Assistant storage helper wrapper.

    Rule definitions are saved immediately (they change rarely). Runtime state is
    saved with ``Store.async_delay_save`` so bursts of alarm transitions produce a
    single write; ``async_flush_states`` forces a write on unload. Home Assistant
    also flushes pending delayed writes on shutdown.
    """

    def __init__(self, hass: Any, rules_key: str, state_key: str) -> None:
        from homeassistant.helpers.storage import Store

        self._rules_store = Store(hass, 1, rules_key, minor_version=0)
        self._state_store = Store(hass, 1, state_key, minor_version=0)
        self.sound_state: dict[str, Any] = {}
        self.sound_state_fn: SoundStateFn | None = None

    async def async_load_rules(self) -> list[AlarmRule]:
        """Load rule definitions from Home Assistant storage."""

        data = await self._rules_store.async_load() or {"rules": []}
        return [AlarmRule.from_dict(item) for item in data.get("rules", [])]

    async def async_save_rules(self, rules: Iterable[AlarmRule]) -> None:
        """Save rules to Home Assistant storage."""

        await self._rules_store.async_save(
            {"version": 1, "minor_version": 0, "rules": [rule.to_dict() for rule in rules]}
        )

    async def async_load_states(self) -> dict[str, AlarmRuntimeState]:
        """Load runtime state from Home Assistant storage."""

        data = await self._state_store.async_load() or {"states": {}}
        self.sound_state = dict(data.get("sound") or {})
        return {
            rule_id: AlarmRuntimeState.from_dict({"rule_id": rule_id, **state})
            for rule_id, state in data.get("states", {}).items()
        }

    def _state_data(self, states: dict[str, AlarmRuntimeState]) -> dict[str, Any]:
        data: dict[str, Any] = {
            "version": 1,
            "minor_version": 0,
            "states": {rule_id: state.to_dict() for rule_id, state in states.items()},
        }
        if self.sound_state_fn is not None:
            data["sound"] = self.sound_state_fn()
        return data

    async def async_save_states(
        self, states: dict[str, AlarmRuntimeState]
    ) -> None:
        """Schedule a debounced write of runtime state.

        The data is serialized when the write happens, so the latest state is
        always stored.
        """

        self._state_store.async_delay_save(
            lambda: self._state_data(states), STATE_SAVE_DELAY_SECONDS
        )

    async def async_flush_states(
        self, states: dict[str, AlarmRuntimeState]
    ) -> None:
        """Write runtime state immediately (used on unload)."""

        await self._state_store.async_save(self._state_data(states))


def schedule_history_retention(
    hass: Any,
    history_store: Any,
    retention_days: int,
    track_time_interval: Callable[..., Callable[[], None]],
) -> Callable[[], None]:
    """Run history retention cleanup now and then once per day.

    Returns the unsubscribe callback of the daily timer.
    """

    async def _cleanup(_now: datetime | None = None) -> int:
        try:
            deleted = await history_store.cleanup_retention(int(retention_days))
        except Exception:  # pragma: no cover - defensive around disk I/O
            _LOGGER.exception("Alarm history retention cleanup failed")
            return 0
        if deleted:
            _LOGGER.debug(
                "Removed %s alarm history rows older than %s days",
                deleted,
                retention_days,
            )
        return deleted

    remove = track_time_interval(hass, _cleanup, RETENTION_INTERVAL)
    hass.async_create_task(_cleanup())
    return remove
