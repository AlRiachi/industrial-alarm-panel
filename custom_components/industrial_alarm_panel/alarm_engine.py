"""Central alarm state machine."""

from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from .alarm_models import (
    AlarmEvent,
    AlarmEventType,
    AlarmEvaluationResult,
    AlarmLifecycleState,
    AlarmPriority,
    AlarmRule,
    AlarmRuntimeState,
    AlarmValidationError,
)
from .alarm_rules import evaluate_rule
from .alarm_sound import AlarmSoundManager
from .alarm_store import InMemoryHistoryStore, MemoryRuleStore

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[], None]
AsyncPersist = Callable[[dict[str, AlarmRuntimeState]], Awaitable[None]]


class AlarmEngine:
    """Evaluate source states and maintain alarm lifecycle state."""

    def __init__(
        self,
        rules: Iterable[AlarmRule] | None = None,
        history_store: Any | None = None,
        *,
        sound_manager: AlarmSoundManager | None = None,
        now: Callable[[], datetime] | None = None,
        persist_states: AsyncPersist | None = None,
        initial_states: dict[str, AlarmRuntimeState] | None = None,
        alarm_flood_threshold: int = 25,
        alarm_flood_window_seconds: int = 60,
        flapping_threshold: int = 6,
        flapping_window_seconds: int = 300,
        auto_shelve_flapping: bool = False,
        auto_shelve_minutes: int = 10,
    ) -> None:
        self.rules: dict[str, AlarmRule] = {rule.id: rule for rule in rules or []}
        self.states: dict[str, AlarmRuntimeState] = {
            rule_id: replace(state) for rule_id, state in (initial_states or {}).items()
        }
        for rule_id in self.rules:
            self.states.setdefault(rule_id, AlarmRuntimeState(rule_id=rule_id))
        self.history_store = history_store or InMemoryHistoryStore()
        self.sound_manager = sound_manager
        self._now = now or (lambda: datetime.now(UTC))
        self._persist_states = persist_states
        self._listeners: list[Listener] = []
        self._previous_entity_states: dict[str, str] = {}
        self._recent_activations: deque[datetime] = deque()
        self.alarm_flood_threshold = alarm_flood_threshold
        self.alarm_flood_window_seconds = alarm_flood_window_seconds
        self.flapping_threshold = flapping_threshold
        self.flapping_window_seconds = flapping_window_seconds
        self.auto_shelve_flapping = auto_shelve_flapping
        self.auto_shelve_minutes = auto_shelve_minutes
        self.last_event: AlarmEvent | None = None

    @classmethod
    async def from_store(
        cls,
        rule_store: MemoryRuleStore,
        history_store: Any,
        *,
        sound_manager: AlarmSoundManager | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> "AlarmEngine":
        """Build an engine from a rule/runtime store."""

        rules = await rule_store.async_load_rules()
        states = await rule_store.async_load_states()
        return cls(
            rules,
            history_store,
            sound_manager=sound_manager,
            now=now,
            persist_states=rule_store.async_save_states,
            initial_states=states,
        )

    def add_listener(self, listener: Listener) -> Callable[[], None]:
        """Register an update listener."""

        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    async def _persist(self) -> None:
        if self._persist_states:
            await self._persist_states(self.states)

    def get_alarm(self, rule_id: str) -> AlarmRuntimeState:
        """Return runtime state for a rule."""

        return self.states[rule_id]

    def get_rule(self, rule_id: str) -> AlarmRule:
        """Return a rule."""

        return self.rules[rule_id]

    async def process_state(self, entity_id: str, new_state: Any) -> None:
        """Evaluate all rules tied to an entity state change."""

        previous = self._previous_entity_states.get(entity_id)
        self._previous_entity_states[entity_id] = "" if new_state is None else str(new_state)
        for rule in list(self.rules.values()):
            if rule.entity_id == entity_id:
                await self.evaluate_rule(rule.id, new_state, previous)

    async def evaluate_rule(
        self, rule_id: str, new_state: Any, previous_state: Any = None
    ) -> AlarmEvaluationResult:
        """Evaluate one rule and transition state if needed."""

        rule = self.rules[rule_id]
        runtime = self.states.setdefault(rule_id, AlarmRuntimeState(rule_id=rule_id))
        now = self._now()

        if not rule.enabled or runtime.lifecycle_state == AlarmLifecycleState.DISABLED:
            return AlarmEvaluationResult(False, str(new_state), new_state, reason="disabled")

        if runtime.lifecycle_state == AlarmLifecycleState.SHELVED:
            if runtime.shelve_expiry and runtime.shelve_expiry <= now:
                await self.unshelve_alarm(rule_id, operator="system")
                runtime = self.states[rule_id]
            else:
                runtime.last_state = str(new_state)
                runtime.last_value = new_state
                await self._persist()
                return AlarmEvaluationResult(
                    False, str(new_state), new_state, reason="shelved"
                )

        result = evaluate_rule(
            rule,
            new_state,
            previous_state,
            currently_active=runtime.is_active,
        )
        runtime.last_state = result.source_state
        runtime.last_value = result.source_value

        if result.matched:
            await self._handle_matched(rule, runtime, result)
        else:
            await self._handle_cleared(rule, runtime, result)

        await self._persist()
        self._notify()
        return result

    async def manual_alarm(
        self, rule_id: str, *, message: str | None = None, operator: str | None = None
    ) -> None:
        """Activate a manual alarm by service call."""

        rule = self.rules[rule_id]
        runtime = self.states.setdefault(rule_id, AlarmRuntimeState(rule_id=rule_id))
        result = AlarmEvaluationResult(True, "manual", "manual", message=message)
        await self._handle_matched(rule, runtime, result, operator=operator)
        await self._persist()
        self._notify()

    async def _handle_matched(
        self,
        rule: AlarmRule,
        runtime: AlarmRuntimeState,
        result: AlarmEvaluationResult,
        *,
        operator: str | None = None,
    ) -> None:
        if runtime.is_active:
            return

        previous = runtime.lifecycle_state
        runtime.previous_lifecycle_state = previous
        runtime.lifecycle_state = AlarmLifecycleState.ACTIVE_UNACK
        runtime.active_timestamp = self._now()
        runtime.clear_timestamp = None
        runtime.ack_timestamp = None
        runtime.ack_user = None
        runtime.transition_timestamps.append(runtime.active_timestamp)
        await self._record_event(
            rule,
            AlarmEventType.ACTIVATED,
            previous_state=previous,
            new_state=runtime.lifecycle_state,
            result=result,
            message=result.message or rule.description,
            operator=operator,
        )
        await self._record_activation_protections(rule, runtime)
        if rule.audible and self.sound_manager:
            await self.sound_manager.on_alarm_requires_sound(rule.id, rule.priority)

    async def _handle_cleared(
        self,
        rule: AlarmRule,
        runtime: AlarmRuntimeState,
        result: AlarmEvaluationResult,
    ) -> None:
        if runtime.lifecycle_state not in {
            AlarmLifecycleState.ACTIVE_UNACK,
            AlarmLifecycleState.ACTIVE_ACK,
        }:
            return

        previous = runtime.lifecycle_state
        runtime.previous_lifecycle_state = previous
        runtime.clear_timestamp = self._now()
        if previous == AlarmLifecycleState.ACTIVE_UNACK and not rule.auto_ack_on_clear:
            runtime.lifecycle_state = AlarmLifecycleState.CLEARED_UNACK
        else:
            runtime.lifecycle_state = AlarmLifecycleState.CLEARED_ACK
            if self.sound_manager:
                await self.sound_manager.on_alarm_acknowledged(rule.id)

        await self._record_event(
            rule,
            AlarmEventType.CLEARED,
            previous_state=previous,
            new_state=runtime.lifecycle_state,
            result=result,
        )

    async def acknowledge_alarm(
        self,
        rule_id: str,
        *,
        operator: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Acknowledge one alarm."""

        rule = self.rules[rule_id]
        runtime = self.states[rule_id]
        previous = runtime.lifecycle_state
        if previous == AlarmLifecycleState.ACTIVE_UNACK:
            runtime.lifecycle_state = AlarmLifecycleState.ACTIVE_ACK
        elif previous == AlarmLifecycleState.CLEARED_UNACK:
            runtime.lifecycle_state = AlarmLifecycleState.CLEARED_ACK
        else:
            return

        runtime.previous_lifecycle_state = previous
        runtime.ack_timestamp = self._now()
        runtime.ack_user = operator
        await self._record_event(
            rule,
            AlarmEventType.ACKNOWLEDGED,
            previous_state=previous,
            new_state=runtime.lifecycle_state,
            operator=operator,
            message=comment,
        )
        if self.sound_manager:
            await self.sound_manager.on_alarm_acknowledged(rule.id)
        await self._persist()
        self._notify()

    async def acknowledge_all(
        self,
        *,
        priority: str | None = None,
        area: str | None = None,
        operator: str | None = None,
        comment: str | None = None,
    ) -> int:
        """Acknowledge all matching unacknowledged alarms."""

        count = 0
        for rule in list(self.rules.values()):
            runtime = self.states[rule.id]
            if not runtime.is_unacknowledged:
                continue
            if priority and rule.priority.value != priority:
                continue
            if area and rule.area != area:
                continue
            await self.acknowledge_alarm(rule.id, operator=operator, comment=comment)
            count += 1
        return count

    async def silence_horn(
        self, duration_seconds: int | None = None, *, operator: str | None = None
    ) -> None:
        """Silence audible alarm sound."""

        if self.sound_manager:
            await self.sound_manager.silence(duration_seconds)
        await self._record_system_event(AlarmEventType.SILENCED, operator=operator)
        self._notify()

    async def unsilence_horn(self, *, operator: str | None = None) -> None:
        """Unsilence audible alarm sound."""

        if self.sound_manager:
            await self.sound_manager.unsilence()
        await self._record_system_event(AlarmEventType.UNSILENCED, operator=operator)
        self._notify()

    async def shelve_alarm(
        self,
        rule_id: str,
        *,
        duration_minutes: int,
        operator: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Shelve an alarm rule temporarily."""

        rule = self.rules[rule_id]
        if not rule.shelving_allowed:
            raise AlarmValidationError("shelving is not allowed for this rule")
        runtime = self.states[rule_id]
        previous = runtime.lifecycle_state
        runtime.previous_lifecycle_state = previous
        runtime.lifecycle_state = AlarmLifecycleState.SHELVED
        runtime.shelve_expiry = self._now() + timedelta(minutes=duration_minutes)
        await self._record_event(
            rule,
            AlarmEventType.SHELVED,
            previous_state=previous,
            new_state=runtime.lifecycle_state,
            operator=operator,
            message=comment,
        )
        if self.sound_manager:
            await self.sound_manager.on_alarm_acknowledged(rule.id)
        await self._persist()
        self._notify()

    async def unshelve_alarm(
        self, rule_id: str, *, operator: str | None = None
    ) -> None:
        """Unshelve an alarm rule."""

        rule = self.rules[rule_id]
        runtime = self.states[rule_id]
        previous = runtime.lifecycle_state
        runtime.lifecycle_state = AlarmLifecycleState.NORMAL
        runtime.shelve_expiry = None
        runtime.previous_lifecycle_state = previous
        await self._record_event(
            rule,
            AlarmEventType.UNSHELVED,
            previous_state=previous,
            new_state=runtime.lifecycle_state,
            operator=operator,
        )
        await self._persist()
        self._notify()

    async def disable_alarm(
        self, rule_id: str, *, operator: str | None = None, comment: str | None = None
    ) -> None:
        """Disable an alarm rule."""

        rule = self.rules[rule_id]
        runtime = self.states[rule_id]
        previous = runtime.lifecycle_state
        self.rules[rule_id] = replace(rule, enabled=False)
        runtime.lifecycle_state = AlarmLifecycleState.DISABLED
        runtime.previous_lifecycle_state = previous
        await self._record_event(
            rule,
            AlarmEventType.DISABLED,
            previous_state=previous,
            new_state=runtime.lifecycle_state,
            operator=operator,
            message=comment,
        )
        if self.sound_manager:
            await self.sound_manager.on_alarm_acknowledged(rule_id)
        await self._persist()
        self._notify()

    async def enable_alarm(self, rule_id: str, *, operator: str | None = None) -> None:
        """Enable an alarm rule."""

        rule = self.rules[rule_id]
        runtime = self.states[rule_id]
        previous = runtime.lifecycle_state
        self.rules[rule_id] = replace(rule, enabled=True)
        runtime.lifecycle_state = AlarmLifecycleState.NORMAL
        runtime.previous_lifecycle_state = previous
        await self._record_event(
            rule,
            AlarmEventType.ENABLED,
            previous_state=previous,
            new_state=runtime.lifecycle_state,
            operator=operator,
        )
        await self._persist()
        self._notify()

    async def create_rule(self, data: dict[str, Any]) -> AlarmRule:
        """Create a new alarm rule."""

        rule = AlarmRule.from_dict(data)
        if rule.id in self.rules:
            raise AlarmValidationError(f"rule already exists: {rule.id}")
        self.rules[rule.id] = rule
        self.states[rule.id] = AlarmRuntimeState(rule_id=rule.id)
        await self._record_event(rule, AlarmEventType.RULE_CREATED)
        await self._persist()
        self._notify()
        return rule

    async def update_rule(self, rule_id: str, changes: dict[str, Any]) -> AlarmRule:
        """Update a rule by re-validating the merged rule data."""

        if rule_id not in self.rules:
            raise AlarmValidationError(f"unknown rule: {rule_id}")
        data = self.rules[rule_id].to_dict()
        data.update(changes)
        data["id"] = rule_id
        rule = AlarmRule.from_dict(data)
        self.rules[rule_id] = rule
        await self._record_event(rule, AlarmEventType.RULE_UPDATED)
        self._notify()
        return rule

    async def delete_rule(self, rule_id: str) -> None:
        """Delete an alarm rule."""

        rule = self.rules.pop(rule_id)
        self.states.pop(rule_id, None)
        await self._record_event(rule, AlarmEventType.RULE_DELETED)
        await self._persist()
        self._notify()

    def active_count(self) -> int:
        """Return active alarm count."""

        return sum(state.is_active for state in self.states.values())

    def unacknowledged_count(self) -> int:
        """Return unacknowledged alarm count."""

        return sum(state.is_unacknowledged for state in self.states.values())

    def priority_count(self, priority: AlarmPriority) -> int:
        """Return active alarm count by priority."""

        return sum(
            self.states[rule.id].is_active
            for rule in self.rules.values()
            if rule.priority == priority
        )

    def last_alarm(self) -> dict[str, Any] | None:
        """Return the newest active alarm."""

        active = [
            (self.states[rule.id].active_timestamp, rule, self.states[rule.id])
            for rule in self.rules.values()
            if self.states[rule.id].is_active
        ]
        active = [item for item in active if item[0] is not None]
        if not active:
            return None
        _timestamp, rule, runtime = max(active, key=lambda item: item[0])
        return self.alarm_to_dict(rule, runtime)

    def list_alarms(
        self,
        *,
        include_normal: bool = False,
        include_shelved: bool = True,
        include_disabled: bool = True,
    ) -> list[dict[str, Any]]:
        """List alarms for frontend and websocket APIs."""

        items: list[dict[str, Any]] = []
        for rule in self.rules.values():
            runtime = self.states[rule.id]
            if (
                not include_normal
                and runtime.lifecycle_state == AlarmLifecycleState.NORMAL
            ):
                continue
            if not include_shelved and runtime.lifecycle_state == AlarmLifecycleState.SHELVED:
                continue
            if not include_disabled and runtime.lifecycle_state == AlarmLifecycleState.DISABLED:
                continue
            items.append(self.alarm_to_dict(rule, runtime))
        items.sort(key=lambda item: (-int(item["severity"]), item.get("active_since") or ""))
        return items

    def alarm_to_dict(
        self, rule: AlarmRule, runtime: AlarmRuntimeState
    ) -> dict[str, Any]:
        """Serialize alarm state for frontend and entity attributes."""

        return {
            "id": rule.id,
            "entity_id": rule.entity_id,
            "name": rule.name,
            "tag": rule.tag,
            "area": rule.area,
            "system": rule.system,
            "description": rule.description,
            "priority": rule.priority.value,
            "severity": rule.severity,
            "condition": rule.condition.value,
            "threshold": rule.threshold,
            "deadband": rule.deadband,
            "requires_ack": rule.requires_ack,
            "audible": rule.audible,
            "enabled": rule.enabled,
            "instructions": rule.instructions,
            "lifecycle_state": runtime.lifecycle_state.value,
            "acknowledged": runtime.acknowledged,
            "shelved": runtime.lifecycle_state == AlarmLifecycleState.SHELVED,
            "disabled": runtime.lifecycle_state == AlarmLifecycleState.DISABLED,
            "active_since": runtime.active_timestamp.isoformat()
            if runtime.active_timestamp
            else None,
            "cleared_at": runtime.clear_timestamp.isoformat()
            if runtime.clear_timestamp
            else None,
            "acknowledged_at": runtime.ack_timestamp.isoformat()
            if runtime.ack_timestamp
            else None,
            "ack_user": runtime.ack_user,
            "shelve_expiry": runtime.shelve_expiry.isoformat()
            if runtime.shelve_expiry
            else None,
            "last_value": runtime.last_value,
            "last_source_state": runtime.last_state,
        }

    async def _record_activation_protections(
        self, rule: AlarmRule, runtime: AlarmRuntimeState
    ) -> None:
        now = self._now()
        self._recent_activations.append(now)
        cutoff = now - timedelta(seconds=self.alarm_flood_window_seconds)
        while self._recent_activations and self._recent_activations[0] < cutoff:
            self._recent_activations.popleft()
        if len(self._recent_activations) == self.alarm_flood_threshold:
            await self._record_system_event(
                AlarmEventType.FLOOD_DETECTED,
                message="Alarm flood threshold reached",
            )

        flap_cutoff = now - timedelta(seconds=self.flapping_window_seconds)
        runtime.transition_timestamps = [
            ts for ts in runtime.transition_timestamps if ts >= flap_cutoff
        ]
        if len(runtime.transition_timestamps) >= self.flapping_threshold:
            await self._record_event(
                rule,
                AlarmEventType.FLAPPING_DETECTED,
                message="Alarm flapping threshold reached",
            )
            if self.auto_shelve_flapping:
                await self.shelve_alarm(
                    rule.id,
                    duration_minutes=self.auto_shelve_minutes,
                    operator="system",
                    comment="Auto-shelved after flapping detection",
                )

    async def _record_event(
        self,
        rule: AlarmRule,
        event_type: AlarmEventType,
        *,
        previous_state: AlarmLifecycleState | None = None,
        new_state: AlarmLifecycleState | None = None,
        result: AlarmEvaluationResult | None = None,
        message: str | None = None,
        operator: str | None = None,
    ) -> None:
        event = AlarmEvent(
            rule_id=rule.id,
            entity_id=rule.entity_id,
            tag=rule.tag,
            name=rule.name,
            area=rule.area,
            system=rule.system,
            priority=rule.priority.value,
            event_type=event_type.value,
            previous_state=previous_state.value if previous_state else None,
            new_state=new_state.value if new_state else None,
            source_state=result.source_state if result else None,
            source_value=result.source_value if result else None,
            message=message,
            operator=operator,
            timestamp=self._now(),
        )
        await self.history_store.add_event(event)
        self.last_event = event

    async def _record_system_event(
        self,
        event_type: AlarmEventType,
        *,
        message: str | None = None,
        operator: str | None = None,
    ) -> None:
        event = AlarmEvent(
            rule_id=None,
            entity_id=None,
            event_type=event_type.value,
            message=message,
            operator=operator,
            timestamp=self._now(),
        )
        await self.history_store.add_event(event)
        self.last_event = event

    async def async_shutdown(self) -> None:
        """Flush state before unload."""

        await self._persist()
        close = getattr(self.history_store, "close", None)
        if close:
            await close()
