"""Central alarm state machine."""

from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from .alarm_models import (
    AlarmCondition,
    AlarmEvent,
    AlarmEventType,
    AlarmEvaluationResult,
    AlarmLifecycleState,
    AlarmPriority,
    AlarmRule,
    AlarmRuleNotFoundError,
    AlarmRuntimeState,
    AlarmValidationError,
)
from .alarm_rules import BAD_QUALITY_REASONS, evaluate_rule
from .alarm_sound import AlarmSoundManager
from .alarm_store import InMemoryHistoryStore, MemoryRuleStore

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[], None]
AsyncPersist = Callable[[dict[str, AlarmRuntimeState]], Awaitable[None]]

#: Conditions that describe an event rather than a level; they are not
#: re-evaluated from a cached/current value (startup, unshelve, enable, edit).
EVENT_CONDITIONS = frozenset({AlarmCondition.STATE_CHANGED, AlarmCondition.MANUAL})


class AlarmEngine:
    """Evaluate source states and maintain alarm lifecycle state.

    State changes are batched: internal transitions mark rules as changed and a
    public operation ends with ``_commit()``, which persists runtime state and
    notifies listeners once, and only when something material changed. A source
    reading that does not change the alarm's lifecycle, acknowledgement,
    shelving, pending timers or counters causes no save and no notification.
    """

    def __init__(
        self,
        rules: Iterable[AlarmRule] | None = None,
        history_store: Any | None = None,
        *,
        sound_manager: AlarmSoundManager | None = None,
        now: Callable[[], datetime] | None = None,
        persist_states: AsyncPersist | None = None,
        flush_states: AsyncPersist | None = None,
        initial_states: dict[str, AlarmRuntimeState] | None = None,
        alarm_flood_threshold: int = 25,
        alarm_flood_window_seconds: int = 60,
        flapping_threshold: int = 6,
        flapping_window_seconds: int = 300,
        auto_shelve_flapping: bool = False,
        auto_shelve_minutes: int = 10,
        store_normal_events: bool = False,
        default_delay_on_seconds: int = 0,
        default_delay_off_seconds: int = 0,
        default_deadband: float = 0.0,
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
        self._flush_states = flush_states
        self._listeners: list[Listener] = []
        self._rule_listeners: dict[str, list[Listener]] = {}
        self._entity_index: dict[str, list[str]] = {}
        self._previous_entity_states: dict[str, str] = {}
        self._recent_activations: deque[datetime] = deque()
        self._needs_save = False
        self._needs_notify = False
        self._changed_rule_ids: set[str] = set()
        self.last_changed_rule_ids: list[str] = []
        self.alarm_flood_threshold = alarm_flood_threshold
        self.alarm_flood_window_seconds = alarm_flood_window_seconds
        self.flapping_threshold = flapping_threshold
        self.flapping_window_seconds = flapping_window_seconds
        self.auto_shelve_flapping = auto_shelve_flapping
        self.auto_shelve_minutes = auto_shelve_minutes
        self.store_normal_events = store_normal_events
        self.default_delay_on_seconds = default_delay_on_seconds
        self.default_delay_off_seconds = default_delay_off_seconds
        self.default_deadband = default_deadband
        self.last_event: AlarmEvent | None = None
        self._rebuild_entity_index()

    @classmethod
    async def from_store(
        cls,
        rule_store: MemoryRuleStore,
        history_store: Any,
        *,
        sound_manager: AlarmSoundManager | None = None,
        now: Callable[[], datetime] | None = None,
        **kwargs: Any,
    ) -> "AlarmEngine":
        """Build an engine from a rule/runtime store and restore horn state."""

        rules = await rule_store.async_load_rules()
        states = await rule_store.async_load_states()
        engine = cls(
            rules,
            history_store,
            sound_manager=sound_manager,
            now=now,
            persist_states=rule_store.async_save_states,
            flush_states=getattr(rule_store, "async_flush_states", None),
            initial_states=states,
            **kwargs,
        )
        if sound_manager is not None:
            if hasattr(rule_store, "sound_state_fn"):
                rule_store.sound_state_fn = sound_manager.to_state
            engine.restore_sound_state(getattr(rule_store, "sound_state", None))
        return engine

    # ------------------------------------------------------------------
    # Listeners, change tracking and persistence
    # ------------------------------------------------------------------

    def add_listener(self, listener: Listener) -> Callable[[], None]:
        """Register a listener called after any committed change."""

        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def add_rule_listener(
        self, rule_id: str, listener: Listener
    ) -> Callable[[], None]:
        """Register a listener called only when ``rule_id`` changed."""

        self._rule_listeners.setdefault(rule_id, []).append(listener)

        def remove() -> None:
            listeners = self._rule_listeners.get(rule_id)
            if listeners and listener in listeners:
                listeners.remove(listener)
                if not listeners:
                    self._rule_listeners.pop(rule_id, None)

        return remove

    def _mark_changed(self, rule_id: str | None = None, *, persist: bool = True) -> None:
        self._needs_notify = True
        if persist:
            self._needs_save = True
        if rule_id is not None:
            self._changed_rule_ids.add(rule_id)

    async def _commit(self) -> None:
        """Persist and notify once if anything changed since the last commit."""

        if not (self._needs_save or self._needs_notify):
            return
        needs_save = self._needs_save
        changed = sorted(self._changed_rule_ids)
        self._needs_save = False
        self._needs_notify = False
        self._changed_rule_ids = set()
        if needs_save:
            await self._persist()
        self._notify(changed)

    def _notify(self, rule_ids: Iterable[str] = ()) -> None:
        rule_ids = list(rule_ids)
        self.last_changed_rule_ids = rule_ids
        for listener in list(self._listeners):
            self._call_listener(listener)
        for rule_id in rule_ids:
            for listener in list(self._rule_listeners.get(rule_id, ())):
                self._call_listener(listener)

    @staticmethod
    def _call_listener(listener: Listener) -> None:
        try:
            listener()
        except Exception:  # pragma: no cover - a broken listener must not stop others
            _LOGGER.exception("Alarm update listener failed")

    def notify_listeners(self, rule_ids: Iterable[str] = ()) -> None:
        """Notify listeners after external runtime state changes (e.g. sound)."""

        self._notify(rule_ids)

    async def _persist(self) -> None:
        if self._persist_states:
            await self._persist_states(self.states)

    async def async_flush(self) -> None:
        """Write runtime state immediately."""

        flush = self._flush_states or self._persist_states
        if flush:
            await flush(self.states)

    @staticmethod
    def _material_snapshot(runtime: AlarmRuntimeState) -> tuple[Any, ...]:
        """Return the persisted fields whose change is worth saving/notifying.

        ``last_value``/``last_state`` are deliberately excluded: they change on
        every source reading and are written along with the next material change
        (and on flush).
        """

        return (
            runtime.lifecycle_state,
            runtime.previous_lifecycle_state,
            runtime.active_timestamp,
            runtime.clear_timestamp,
            runtime.ack_timestamp,
            runtime.ack_user,
            runtime.shelve_expiry,
            runtime.last_sound_timestamp,
            runtime.pending_active_since,
            runtime.pending_clear_since,
            len(runtime.transition_timestamps),
        )

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def _require_rule(self, rule_id: str) -> AlarmRule:
        rule = self.rules.get(rule_id)
        if rule is None:
            raise AlarmRuleNotFoundError(rule_id)
        return rule

    def _runtime(self, rule_id: str) -> AlarmRuntimeState:
        return self.states.setdefault(rule_id, AlarmRuntimeState(rule_id=rule_id))

    def get_alarm(self, rule_id: str) -> AlarmRuntimeState:
        """Return runtime state for a rule."""

        return self.states[rule_id]

    def get_rule(self, rule_id: str) -> AlarmRule:
        """Return a rule."""

        return self.rules[rule_id]

    def _rebuild_entity_index(self) -> None:
        index: dict[str, list[str]] = {}
        for rule in self.rules.values():
            if rule.entity_id:
                index.setdefault(rule.entity_id, []).append(rule.id)
        self._entity_index = index

    def tracked_entity_ids(self) -> set[str]:
        """Return source entity IDs watched by at least one rule."""

        return set(self._entity_index)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def process_state(self, entity_id: str, new_state: Any) -> None:
        """Evaluate all rules tied to an entity state change."""

        previous = self._previous_entity_states.get(entity_id)
        self._previous_entity_states[entity_id] = "" if new_state is None else str(new_state)
        for rule_id in list(self._entity_index.get(entity_id, ())):
            if rule_id in self.rules:
                await self._evaluate_rule(rule_id, new_state, previous)
        await self._commit()

    async def async_evaluate_sources(
        self,
        get_state: Callable[[str], Any],
        rule_ids: Iterable[str] | None = None,
    ) -> None:
        """Evaluate rules against the current value of their source entities.

        Used on setup/reload and after rule edits so sources that are already
        out of range raise alarms without waiting for the next state change.
        ``get_state`` returns the raw state string or ``None`` if unknown.
        Event-style conditions (``state_changed``/``manual``) are skipped.
        """

        wanted = set(rule_ids) if rule_ids is not None else None
        for entity_id, entity_rule_ids in list(self._entity_index.items()):
            targets = [
                rule_id
                for rule_id in entity_rule_ids
                if (wanted is None or rule_id in wanted)
                and self.rules[rule_id].condition not in EVENT_CONDITIONS
            ]
            if not targets:
                continue
            state = get_state(entity_id)
            if state is None:
                continue
            self._previous_entity_states.setdefault(entity_id, str(state))
            for rule_id in targets:
                await self._evaluate_rule(rule_id, state)
        await self._commit()

    async def process_due_transitions(self) -> None:
        """Apply delayed transitions and shelve expiries due at the current time."""

        now = self._now()
        for rule in list(self.rules.values()):
            runtime = self._runtime(rule.id)
            due_at = self._rule_due_transition_at(rule, runtime)
            if due_at is None or due_at > now:
                continue

            if runtime.lifecycle_state == AlarmLifecycleState.SHELVED:
                await self._unshelve(rule, runtime, operator="system")
                await self._reevaluate_cached(rule.id)
            elif runtime.last_state is not None:
                await self._evaluate_rule(rule.id, runtime.last_state)

            # Never leave a due time in the past: it would re-arm the timer at 0s.
            still_due = self._rule_due_transition_at(rule, runtime)
            if still_due is not None and still_due <= now:
                runtime.pending_active_since = None
                runtime.pending_clear_since = None
                self._mark_changed(rule.id)
        await self._commit()

    def next_due_transition_at(self) -> datetime | None:
        """Return the next delayed transition or shelve expiry, if any."""

        due_times: list[datetime] = []
        for rule in self.rules.values():
            runtime = self._runtime(rule.id)
            due_at = self._rule_due_transition_at(rule, runtime)
            if due_at is not None:
                due_times.append(due_at)
        return min(due_times) if due_times else None

    async def evaluate_rule(
        self, rule_id: str, new_state: Any, previous_state: Any = None
    ) -> AlarmEvaluationResult:
        """Evaluate one rule and transition state if needed."""

        result = await self._evaluate_rule(rule_id, new_state, previous_state)
        await self._commit()
        return result

    async def _reevaluate_cached(self, rule_id: str) -> None:
        """Re-evaluate a level rule from its last known source state."""

        rule = self.rules.get(rule_id)
        runtime = self.states.get(rule_id)
        if (
            rule is None
            or runtime is None
            or runtime.last_state is None
            or rule.condition in EVENT_CONDITIONS
        ):
            return
        await self._evaluate_rule(rule_id, runtime.last_state)

    async def _evaluate_rule(
        self, rule_id: str, new_state: Any, previous_state: Any = None
    ) -> AlarmEvaluationResult:
        rule = self._require_rule(rule_id)
        runtime = self._runtime(rule_id)
        before = self._material_snapshot(runtime)
        previous_source = runtime.last_state
        result = await self._evaluate_rule_inner(
            rule, runtime, new_state, previous_state
        )
        if self._material_snapshot(runtime) != before:
            self._mark_changed(rule_id)
        elif (
            self.store_normal_events
            and result.reason is None
            and previous_source is not None
            and previous_source != runtime.last_state
        ):
            await self._record_event(
                rule,
                AlarmEventType.STATUS_CHANGED,
                previous_state=runtime.lifecycle_state,
                new_state=runtime.lifecycle_state,
                result=result,
            )
            self._mark_changed(rule_id, persist=False)
        return result

    async def _evaluate_rule_inner(
        self,
        rule: AlarmRule,
        runtime: AlarmRuntimeState,
        new_state: Any,
        previous_state: Any,
    ) -> AlarmEvaluationResult:
        now = self._now()
        state_text = "" if new_state is None else str(new_state)

        if not rule.enabled or runtime.lifecycle_state == AlarmLifecycleState.DISABLED:
            runtime.last_state = state_text
            runtime.last_value = new_state
            runtime.pending_active_since = None
            runtime.pending_clear_since = None
            return AlarmEvaluationResult(False, str(new_state), new_state, reason="disabled")

        if runtime.lifecycle_state == AlarmLifecycleState.SHELVED:
            if runtime.shelve_expiry and runtime.shelve_expiry <= now:
                await self._unshelve(rule, runtime, operator="system")
            else:
                runtime.last_state = state_text
                runtime.last_value = new_state
                runtime.pending_active_since = None
                runtime.pending_clear_since = None
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

        if result.reason in BAD_QUALITY_REASONS:
            # Bad quality: no transition in either direction. Pending delay
            # timers cannot be confirmed, so they restart on the next good value.
            runtime.pending_active_since = None
            runtime.pending_clear_since = None
            return result

        if result.matched:
            await self._handle_matched_evaluation(rule, runtime, result, now)
        else:
            await self._handle_cleared_evaluation(rule, runtime, result, now)
        return result

    async def manual_alarm(
        self, rule_id: str, *, message: str | None = None, operator: str | None = None
    ) -> None:
        """Activate a manual alarm by service call."""

        rule = self._require_rule(rule_id)
        runtime = self._runtime(rule_id)
        result = AlarmEvaluationResult(True, "manual", "manual", message=message)
        await self._handle_matched(rule, runtime, result, operator=operator)
        self._mark_changed(rule_id)
        await self._commit()

    async def _handle_matched_evaluation(
        self,
        rule: AlarmRule,
        runtime: AlarmRuntimeState,
        result: AlarmEvaluationResult,
        now: datetime,
        *,
        operator: str | None = None,
    ) -> None:
        runtime.pending_clear_since = None
        if runtime.is_active:
            runtime.pending_active_since = None
            return

        delay_on_seconds = self._positive_seconds(rule.delay_on_seconds)
        if delay_on_seconds:
            if runtime.pending_active_since is None:
                runtime.pending_active_since = now
            due_at = runtime.pending_active_since + timedelta(seconds=delay_on_seconds)
            if now < due_at:
                return

        runtime.pending_active_since = None
        await self._handle_matched(rule, runtime, result, operator=operator)

    async def _handle_cleared_evaluation(
        self,
        rule: AlarmRule,
        runtime: AlarmRuntimeState,
        result: AlarmEvaluationResult,
        now: datetime,
    ) -> None:
        runtime.pending_active_since = None
        if not runtime.is_active:
            runtime.pending_clear_since = None
            return

        if self._clear_delay_required(rule, runtime, now):
            if runtime.pending_clear_since is None:
                runtime.pending_clear_since = now
            due_at = self._clear_due_transition_at(rule, runtime)
            if due_at is not None and now < due_at:
                return

        runtime.pending_clear_since = None
        await self._handle_cleared(rule, runtime, result)

    async def _handle_matched(
        self,
        rule: AlarmRule,
        runtime: AlarmRuntimeState,
        result: AlarmEvaluationResult,
        *,
        operator: str | None = None,
    ) -> None:
        runtime.pending_active_since = None
        runtime.pending_clear_since = None
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
        auto_shelved = await self._record_activation_protections(rule, runtime)
        if auto_shelved:
            # Flapping protection shelved the alarm: do not sound the horn.
            return
        if rule.audible and self.sound_manager:
            await self.sound_manager.on_alarm_requires_sound(rule.id, rule.priority)

    async def _handle_cleared(
        self,
        rule: AlarmRule,
        runtime: AlarmRuntimeState,
        result: AlarmEvaluationResult,
    ) -> None:
        runtime.pending_active_since = None
        runtime.pending_clear_since = None
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

    # ------------------------------------------------------------------
    # Operator actions
    # ------------------------------------------------------------------

    async def acknowledge_alarm(
        self,
        rule_id: str,
        *,
        operator: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Acknowledge one alarm."""

        rule = self._require_rule(rule_id)
        await self._acknowledge(rule, operator=operator, comment=comment)
        await self._commit()

    async def _acknowledge(
        self,
        rule: AlarmRule,
        *,
        operator: str | None = None,
        comment: str | None = None,
    ) -> bool:
        runtime = self._runtime(rule.id)
        previous = runtime.lifecycle_state
        if previous == AlarmLifecycleState.ACTIVE_UNACK:
            runtime.lifecycle_state = AlarmLifecycleState.ACTIVE_ACK
        elif previous == AlarmLifecycleState.CLEARED_UNACK:
            runtime.lifecycle_state = AlarmLifecycleState.CLEARED_ACK
        else:
            return False

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
        self._mark_changed(rule.id)
        return True

    async def acknowledge_all(
        self,
        *,
        priority: str | None = None,
        area: str | None = None,
        operator: str | None = None,
        comment: str | None = None,
    ) -> int:
        """Acknowledge all matching unacknowledged alarms (one save, one notify)."""

        count = 0
        for rule in list(self.rules.values()):
            runtime = self._runtime(rule.id)
            if not runtime.is_unacknowledged:
                continue
            if priority and rule.priority.value != priority:
                continue
            if area and rule.area != area:
                continue
            if await self._acknowledge(rule, operator=operator, comment=comment):
                count += 1
        await self._commit()
        return count

    async def silence_horn(
        self, duration_seconds: int | None = None, *, operator: str | None = None
    ) -> None:
        """Silence audible alarm sound."""

        if self.sound_manager:
            await self.sound_manager.silence(duration_seconds)
        await self._record_system_event(AlarmEventType.SILENCED, operator=operator)
        self._mark_changed()
        await self._commit()

    async def unsilence_horn(self, *, operator: str | None = None) -> None:
        """Unsilence audible alarm sound."""

        if self.sound_manager:
            await self.sound_manager.unsilence()
        await self._record_system_event(AlarmEventType.UNSILENCED, operator=operator)
        self._mark_changed()
        await self._commit()

    async def async_process_sound_timers(self) -> None:
        """Apply timed sound behaviour (silence expiry, repeat, test end)."""

        if self.sound_manager is None:
            return
        silenced_before = self.sound_manager.silenced
        changed = await self.sound_manager.async_process_timers(self._now())
        if changed:
            if silenced_before and not self.sound_manager.silenced:
                await self._record_system_event(
                    AlarmEventType.UNSILENCED,
                    operator="system",
                    message="Timed silence expired",
                )
            self._mark_changed()
            await self._commit()

    def restore_sound_state(self, sound_state: dict[str, Any] | None) -> None:
        """Rebuild the audible alarm set and horn state after a restart."""

        if self.sound_manager is None:
            return
        audible = {
            rule.id: rule.priority
            for rule in self.rules.values()
            if rule.audible
            and rule.enabled
            and self._runtime(rule.id).is_unacknowledged
        }
        self.sound_manager.restore(audible, sound_state)

    async def shelve_alarm(
        self,
        rule_id: str,
        *,
        duration_minutes: int,
        operator: str | None = None,
        comment: str | None = None,
    ) -> None:
        """Shelve an alarm rule temporarily."""

        rule = self._require_rule(rule_id)
        await self._shelve(
            rule, duration_minutes=duration_minutes, operator=operator, comment=comment
        )
        await self._commit()

    async def _shelve(
        self,
        rule: AlarmRule,
        *,
        duration_minutes: int,
        operator: str | None = None,
        comment: str | None = None,
    ) -> None:
        if not rule.shelving_allowed:
            raise AlarmValidationError("shelving is not allowed for this rule")
        runtime = self._runtime(rule.id)
        previous = runtime.lifecycle_state
        runtime.pending_active_since = None
        runtime.pending_clear_since = None
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
        self._mark_changed(rule.id)

    async def unshelve_alarm(
        self, rule_id: str, *, operator: str | None = None
    ) -> None:
        """Unshelve an alarm rule and re-evaluate its last source state."""

        rule = self._require_rule(rule_id)
        await self._unshelve(rule, self._runtime(rule_id), operator=operator)
        await self._reevaluate_cached(rule_id)
        await self._commit()

    async def _unshelve(
        self,
        rule: AlarmRule,
        runtime: AlarmRuntimeState,
        *,
        operator: str | None = None,
    ) -> None:
        previous = runtime.lifecycle_state
        runtime.pending_active_since = None
        runtime.pending_clear_since = None
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
        self._mark_changed(rule.id)

    async def disable_alarm(
        self, rule_id: str, *, operator: str | None = None, comment: str | None = None
    ) -> None:
        """Disable an alarm rule."""

        self._require_rule(rule_id)
        await self._disable(rule_id, operator=operator, comment=comment)
        await self._commit()

    async def _disable(
        self, rule_id: str, *, operator: str | None = None, comment: str | None = None
    ) -> None:
        rule = self.rules[rule_id]
        runtime = self._runtime(rule_id)
        previous = runtime.lifecycle_state
        self.rules[rule_id] = replace(rule, enabled=False)
        runtime.pending_active_since = None
        runtime.pending_clear_since = None
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
        self._mark_changed(rule_id)

    async def enable_alarm(self, rule_id: str, *, operator: str | None = None) -> None:
        """Enable an alarm rule and re-evaluate its last source state."""

        self._require_rule(rule_id)
        await self._enable(rule_id, operator=operator)
        await self._reevaluate_cached(rule_id)
        await self._commit()

    async def _enable(self, rule_id: str, *, operator: str | None = None) -> None:
        rule = self.rules[rule_id]
        runtime = self._runtime(rule_id)
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
        self._mark_changed(rule_id)

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def _apply_rule_defaults(self, data: dict[str, Any]) -> dict[str, Any]:
        """Fill option-level defaults for fields a new rule did not specify."""

        data = dict(data)
        defaults = {
            "delay_on_seconds": self.default_delay_on_seconds,
            "delay_off_seconds": self.default_delay_off_seconds,
            "deadband": self.default_deadband,
        }
        for key, value in defaults.items():
            if data.get(key) in (None, "") and value:
                data[key] = value
        return data

    async def create_rule(self, data: dict[str, Any]) -> AlarmRule:
        """Create a new alarm rule."""

        rule = AlarmRule.from_dict(self._apply_rule_defaults(data))
        if rule.id in self.rules:
            raise AlarmValidationError(f"rule already exists: {rule.id}")
        self.rules[rule.id] = rule
        self.states[rule.id] = AlarmRuntimeState(rule_id=rule.id)
        self._rebuild_entity_index()
        await self._record_event(rule, AlarmEventType.RULE_CREATED)
        self._mark_changed(rule.id)
        await self._commit()
        return rule

    async def update_rule(
        self,
        rule_id: str,
        changes: dict[str, Any],
        *,
        operator: str | None = None,
    ) -> AlarmRule:
        """Update a rule by re-validating the merged rule data.

        Changing ``enabled`` performs the same lifecycle transition as the
        enable/disable operations. Changing ``entity_id`` drops the cached
        source reading of the old entity.
        """

        old = self._require_rule(rule_id)
        data = old.to_dict()
        data.update(changes)
        data["id"] = rule_id
        rule = AlarmRule.from_dict(data)
        self.rules[rule_id] = rule
        runtime = self._runtime(rule_id)
        if rule.entity_id != old.entity_id:
            runtime.last_state = None
            runtime.last_value = None
            runtime.pending_active_since = None
            runtime.pending_clear_since = None
        self._rebuild_entity_index()
        await self._record_event(rule, AlarmEventType.RULE_UPDATED, operator=operator)
        if old.enabled and not rule.enabled:
            await self._disable(rule_id, operator=operator)
        elif not old.enabled and rule.enabled:
            await self._enable(rule_id, operator=operator)
            await self._reevaluate_cached(rule_id)
        elif rule.enabled and (
            rule.condition != old.condition
            or rule.threshold != old.threshold
            or rule.deadband != old.deadband
        ):
            await self._reevaluate_cached(rule_id)
        if old.audible and not rule.audible and self.sound_manager:
            await self.sound_manager.on_alarm_acknowledged(rule_id)
        self._mark_changed(rule_id)
        await self._commit()
        return self.rules[rule_id]

    async def delete_rule(self, rule_id: str) -> None:
        """Delete an alarm rule.

        Per-rule listeners of the deleted rule are dropped before notifying, so
        removed per-alarm entities are never asked to render a missing rule.
        """

        rule = self.rules.pop(rule_id, None)
        if rule is None:
            raise AlarmRuleNotFoundError(rule_id)
        self.states.pop(rule_id, None)
        self._rule_listeners.pop(rule_id, None)
        self._rebuild_entity_index()
        if self.sound_manager:
            await self.sound_manager.on_alarm_acknowledged(rule_id)
        await self._record_event(rule, AlarmEventType.RULE_DELETED)
        self._mark_changed(rule_id)
        await self._commit()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

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

    def _rule_due_transition_at(
        self, rule: AlarmRule, runtime: AlarmRuntimeState
    ) -> datetime | None:
        """Return when a rule's pending transition or shelve expiry is due."""

        if runtime.lifecycle_state == AlarmLifecycleState.SHELVED:
            return runtime.shelve_expiry

        if (
            runtime.pending_active_since is not None
            and not runtime.is_active
            and self._positive_seconds(rule.delay_on_seconds)
        ):
            return runtime.pending_active_since + timedelta(
                seconds=self._positive_seconds(rule.delay_on_seconds)
            )

        if runtime.pending_clear_since is not None and runtime.is_active:
            return self._clear_due_transition_at(rule, runtime)

        return None

    def _clear_due_transition_at(
        self, rule: AlarmRule, runtime: AlarmRuntimeState
    ) -> datetime | None:
        """Return the earliest time an active alarm is allowed to clear."""

        due_times: list[datetime] = []
        delay_off_seconds = self._positive_seconds(rule.delay_off_seconds)
        min_active_duration_seconds = self._positive_seconds(
            rule.min_active_duration_seconds
        )

        if delay_off_seconds and runtime.pending_clear_since is not None:
            due_times.append(
                runtime.pending_clear_since + timedelta(seconds=delay_off_seconds)
            )
        if min_active_duration_seconds and runtime.active_timestamp is not None:
            due_times.append(
                runtime.active_timestamp
                + timedelta(seconds=min_active_duration_seconds)
            )

        return max(due_times) if due_times else None

    def _clear_delay_required(
        self, rule: AlarmRule, runtime: AlarmRuntimeState, now: datetime
    ) -> bool:
        """Return whether a clear transition should wait before clearing."""

        if self._positive_seconds(rule.delay_off_seconds):
            return True
        min_active_duration_seconds = self._positive_seconds(
            rule.min_active_duration_seconds
        )
        return (
            bool(min_active_duration_seconds)
            and runtime.active_timestamp is not None
            and now
            < runtime.active_timestamp
            + timedelta(seconds=min_active_duration_seconds)
        )

    @staticmethod
    def _positive_seconds(value: int | None) -> int:
        return max(0, int(value or 0))

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

    # ------------------------------------------------------------------
    # Protections and history
    # ------------------------------------------------------------------

    async def _record_activation_protections(
        self, rule: AlarmRule, runtime: AlarmRuntimeState
    ) -> bool:
        """Record flood/flapping protections; return True if auto-shelved."""

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
            if self.auto_shelve_flapping and rule.shelving_allowed:
                await self._shelve(
                    rule,
                    duration_minutes=self.auto_shelve_minutes,
                    operator="system",
                    comment="Auto-shelved after flapping detection",
                )
                return True
        return False

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

        await self.async_flush()
        close = getattr(self.history_store, "close", None)
        if close:
            await close()
