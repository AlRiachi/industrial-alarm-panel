"""Pure helpers for suggested rule selection and bulk rule cleanup."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .alarm_models import AlarmRule, AlarmValidationError
from .const import DOMAIN


class _RegistryEntry(Protocol):
    entity_id: str
    unique_id: str
    config_entry_id: str


@dataclass(slots=True)
class RuleDeletionResult:
    """Result of a bulk rule deletion request."""

    deleted_rules: list[AlarmRule] = field(default_factory=list)
    skipped_rule_ids: list[str] = field(default_factory=list)

    @property
    def deleted_rule_ids(self) -> list[str]:
        """Return deleted rule IDs in deletion order."""

        return [rule.id for rule in self.deleted_rules]


def is_generated_rule_id(rule_id: str) -> bool:
    """Return whether a rule ID belongs to generated suggestions."""

    return rule_id.startswith("auto_")


def select_suggested_rules(
    suggested_rules: Sequence[dict[str, Any]], rule_ids: Sequence[str] | None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Select suggested rules by ID while preserving request order."""

    if rule_ids is None:
        return list(suggested_rules), []

    suggested_by_id = {str(rule["id"]): rule for rule in suggested_rules}
    selected: list[dict[str, Any]] = []
    skipped: list[str] = []
    seen: set[str] = set()

    for rule_id in rule_ids:
        if rule_id in seen:
            continue
        seen.add(rule_id)

        rule = suggested_by_id.get(rule_id)
        if rule is None:
            skipped.append(rule_id)
            continue
        selected.append(rule)

    return selected, skipped


async def delete_rules(
    engine: Any,
    *,
    generated_only: bool = False,
    rule_ids: Sequence[str] | None = None,
) -> RuleDeletionResult:
    """Delete selected rules from an alarm engine."""

    if not generated_only and rule_ids is None:
        raise AlarmValidationError(
            "delete_rules requires rule_ids or generated_only=True"
        )

    requested_rule_ids = _deduplicate(rule_ids) if rule_ids is not None else None
    skipped_rule_ids: list[str] = []

    if requested_rule_ids is None:
        target_rule_ids = [
            rule_id for rule_id in engine.rules if is_generated_rule_id(rule_id)
        ]
    else:
        target_rule_ids = []
        for rule_id in requested_rule_ids:
            rule = engine.rules.get(rule_id)
            if rule is None or (generated_only and not is_generated_rule_id(rule_id)):
                skipped_rule_ids.append(rule_id)
                continue
            target_rule_ids.append(rule_id)

    deleted_rules: list[AlarmRule] = []
    for rule_id in target_rule_ids:
        rule = engine.rules[rule_id]
        await engine.delete_rule(rule_id)
        deleted_rules.append(rule)

    return RuleDeletionResult(deleted_rules, skipped_rule_ids)


def per_rule_entity_unique_ids(entry_id: str, rule: AlarmRule) -> set[str]:
    """Return unique IDs used by per-rule entities for a rule."""

    return {
        f"{DOMAIN}_{entry_id}_alarm_{rule.id}",
        f"{DOMAIN}_{entry_id}_ack_{rule.slug}_{rule.id}",
        f"{DOMAIN}_{entry_id}_shelve_{rule.slug}_{rule.id}",
        f"{DOMAIN}_{entry_id}_disable_{rule.slug}_{rule.id}",
    }


def matching_per_rule_entity_entries(
    entry_id: str, rules: Iterable[AlarmRule], entries: Iterable[_RegistryEntry]
) -> list[_RegistryEntry]:
    """Return registry entries for current per-rule entities in one config entry."""

    unique_ids = {
        unique_id
        for rule in rules
        for unique_id in per_rule_entity_unique_ids(entry_id, rule)
    }

    return [
        entry
        for entry in entries
        if entry.config_entry_id == entry_id and entry.unique_id in unique_ids
    ]


def _deduplicate(rule_ids: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for rule_id in rule_ids:
        if rule_id in seen:
            continue
        seen.add(rule_id)
        deduplicated.append(rule_id)
    return deduplicated
