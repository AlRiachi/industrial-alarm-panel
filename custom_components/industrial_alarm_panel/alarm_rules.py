"""Alarm rule evaluation helpers."""

from __future__ import annotations

from typing import Any

from .alarm_models import (
    AlarmCondition,
    AlarmEvaluationResult,
    AlarmRule,
    UNAVAILABLE_STATES,
)

#: Evaluation reasons that mean the source reading has bad quality.
#:
#: A numeric (``above``/``below``) rule cannot decide anything from a reading
#: such as ``unavailable``, ``unknown`` or a non-numeric string. The engine treats
#: such a result as "no information": it performs no lifecycle transition, so an
#: active alarm stays active (and an inactive one stays inactive) until a valid
#: numeric reading arrives. Pending delay timers are cancelled because they can
#: no longer be confirmed. Use the ``unavailable``, ``unavailable_for`` or
#: ``unknown_for`` conditions to alarm on loss of the source itself.
REASON_BAD_QUALITY = "not_numeric"
BAD_QUALITY_REASONS = frozenset({REASON_BAD_QUALITY})


def parse_numeric_state(value: Any) -> float | None:
    """Parse a Home Assistant state string into a number."""

    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in UNAVAILABLE_STATES:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def evaluate_rule(
    rule: AlarmRule,
    source_state: Any,
    previous_state: Any = None,
    *,
    currently_active: bool = False,
) -> AlarmEvaluationResult:
    """Evaluate an alarm rule against a source state.

    For ``above``/``below`` rules a non-numeric source returns ``matched=False``
    with ``reason=REASON_BAD_QUALITY``; callers must treat that as "no
    transition" rather than as a clear condition (see ``BAD_QUALITY_REASONS``).
    """

    state = "" if source_state is None else str(source_state)
    normalized = state.strip().lower()
    condition = rule.condition

    if condition == AlarmCondition.ABOVE:
        value = parse_numeric_state(state)
        if value is None:
            return AlarmEvaluationResult(False, state, None, reason=REASON_BAD_QUALITY)
        threshold = float(rule.threshold or 0)
        clear_threshold = threshold - float(rule.deadband or 0)
        matched = value > (clear_threshold if currently_active else threshold)
        return AlarmEvaluationResult(
            matched,
            state,
            value,
            message=f"{rule.name} above {threshold:g}",
        )

    if condition == AlarmCondition.BELOW:
        value = parse_numeric_state(state)
        if value is None:
            return AlarmEvaluationResult(False, state, None, reason=REASON_BAD_QUALITY)
        threshold = float(rule.threshold or 0)
        clear_threshold = threshold + float(rule.deadband or 0)
        matched = value < (clear_threshold if currently_active else threshold)
        return AlarmEvaluationResult(
            matched,
            state,
            value,
            message=f"{rule.name} below {threshold:g}",
        )

    if condition == AlarmCondition.EQUAL:
        expected = "" if rule.threshold is None else str(rule.threshold)
        return AlarmEvaluationResult(
            state == expected,
            state,
            state,
            message=f"{rule.name} equals {expected}",
        )

    if condition == AlarmCondition.NOT_EQUAL:
        expected = "" if rule.threshold is None else str(rule.threshold)
        return AlarmEvaluationResult(
            state != expected,
            state,
            state,
            message=f"{rule.name} not equal to {expected}",
        )

    if condition == AlarmCondition.CONTAINS:
        needle = "" if rule.threshold is None else str(rule.threshold)
        return AlarmEvaluationResult(
            needle in state,
            state,
            state,
            message=f"{rule.name} contains {needle}",
        )

    if condition == AlarmCondition.IS_ON:
        return AlarmEvaluationResult(normalized == "on", state, state)

    if condition == AlarmCondition.IS_OFF:
        return AlarmEvaluationResult(normalized == "off", state, state)

    if condition == AlarmCondition.STATE_CHANGED:
        changed = previous_state is not None and str(previous_state) != state
        return AlarmEvaluationResult(changed, state, state)

    if condition == AlarmCondition.UNAVAILABLE:
        return AlarmEvaluationResult(normalized == "unavailable", state, state)

    if condition == AlarmCondition.UNAVAILABLE_FOR:
        return AlarmEvaluationResult(normalized == "unavailable", state, state)

    if condition == AlarmCondition.UNKNOWN_FOR:
        return AlarmEvaluationResult(normalized == "unknown", state, state)

    if condition == AlarmCondition.MANUAL:
        return AlarmEvaluationResult(False, state, state, reason="manual_only")

    return AlarmEvaluationResult(False, state, state, reason="unsupported_condition")
