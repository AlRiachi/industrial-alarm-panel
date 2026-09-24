"""Runtime data for one Industrial Alarm Panel config entry."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any

from .alarm_engine import AlarmEngine
from .alarm_models import AlarmRule
from .alarm_sound import AlarmSoundManager
from .alarm_store import HomeAssistantRuleStore, SQLiteHistoryStore
from .const import DOMAIN
from .rule_management import matching_per_rule_entity_entries

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

#: Builds the per-rule entities one platform owns for a rule.
RuleEntityFactory = Callable[[AlarmRule], list[Any]]


class IntegrationNotLoadedError(RuntimeError):
    """Raised when no loaded Industrial Alarm Panel entry exists."""

    def __str__(self) -> str:
        return "Industrial Alarm Panel is not loaded"


@dataclass(slots=True)
class IndustrialAlarmPanelRuntime:
    """Runtime objects for one config entry."""

    entry_id: str
    rule_store: HomeAssistantRuleStore
    history_store: SQLiteHistoryStore
    sound_manager: AlarmSoundManager
    engine: AlarmEngine
    hass: Any = None
    options: dict[str, Any] = field(default_factory=dict)
    remove_state_listener: Any | None = None
    remove_delay_timer: Any | None = None
    remove_frontend_update_listener: Any | None = None
    remove_panel: Any | None = None
    remove_retention_timer: Any | None = None
    tracked_entities: frozenset[str] = frozenset()
    #: (async_add_entities, factory) per platform that owns per-rule entities.
    rule_entity_platforms: list[tuple[Callable[..., Any], RuleEntityFactory]] = field(
        default_factory=list
    )
    #: Subscribes to state changes of the given entity IDs; returns unsubscribe.
    state_listener_factory: Callable[[list[str]], Callable[[], None]] | None = None
    #: Re-arms the single engine/sound timer.
    reschedule_timers: Callable[[], None] | None = None

    def register_rule_entity_platform(
        self, async_add_entities: Callable[..., Any], factory: RuleEntityFactory
    ) -> None:
        """Remember how a platform creates per-rule entities, and add current ones."""

        self.rule_entity_platforms.append((async_add_entities, factory))
        entities = [
            entity for rule in list(self.engine.rules.values()) for entity in factory(rule)
        ]
        if entities:
            async_add_entities(entities)

    def refresh_state_listener(self) -> None:
        """Re-subscribe to source entities only if the watched set changed."""

        watched = frozenset(self.engine.tracked_entity_ids())
        if watched == self.tracked_entities and (
            self.remove_state_listener is not None or not watched
        ):
            return
        if self.remove_state_listener is not None:
            self.remove_state_listener()
            self.remove_state_listener = None
        self.tracked_entities = watched
        if watched and self.state_listener_factory is not None:
            self.remove_state_listener = self.state_listener_factory(sorted(watched))

    def get_source_state(self, entity_id: str) -> str | None:
        """Return the current Home Assistant state string of a source entity."""

        if self.hass is None:
            return None
        state = self.hass.states.get(entity_id)
        return None if state is None else state.state

    async def async_rules_changed(
        self,
        *,
        added: Iterable[AlarmRule] = (),
        removed: Iterable[AlarmRule] = (),
        updated: Iterable[AlarmRule] = (),
    ) -> list[str]:
        """Apply rule definition changes in place without reloading the entry.

        Saves rule definitions, re-subscribes source listeners when the watched
        entity set changed, adds per-rule entities for new rules, removes the
        registry entries (and therefore the entities) of deleted rules and
        evaluates new/edited rules against their current source state.
        Returns the removed entity IDs.
        """

        added = list(added)
        removed = list(removed)
        updated = list(updated)
        await self.rule_store.async_save_rules(self.engine.rules.values())
        self.refresh_state_listener()

        removed_entity_ids: list[str] = []
        if removed and self.hass is not None:
            removed_entity_ids = remove_per_rule_entity_registry_entries(
                self.hass, self.entry_id, removed
            )

        if added:
            for async_add_entities, factory in self.rule_entity_platforms:
                entities = [entity for rule in added for entity in factory(rule)]
                if entities:
                    async_add_entities(entities)

        reevaluate = [rule.id for rule in (*added, *updated) if rule.id in self.engine.rules]
        if reevaluate:
            await self.engine.async_evaluate_sources(self.get_source_state, reevaluate)

        if self.reschedule_timers is not None:
            self.reschedule_timers()
        return removed_entity_ids

    async def async_create_rules(
        self, rules_data: Sequence[dict[str, Any]]
    ) -> list[AlarmRule]:
        """Create rules and their entities in place."""

        created: list[AlarmRule] = []
        try:
            for rule_data in rules_data:
                created.append(await self.engine.create_rule(rule_data))
        finally:
            if created:
                await self.async_rules_changed(added=created)
        return created

    async def async_update_rule(
        self, rule_id: str, changes: dict[str, Any], *, operator: str | None = None
    ) -> AlarmRule:
        """Update a rule in place (entities keep their IDs; names refresh)."""

        rule = await self.engine.update_rule(rule_id, changes, operator=operator)
        await self.async_rules_changed(updated=[rule])
        return rule

    async def async_delete_rule(self, rule_id: str) -> list[str]:
        """Delete one rule and its entities; return removed entity IDs."""

        rule = self.engine.rules.get(rule_id)
        await self.engine.delete_rule(rule_id)
        return await self.async_rules_changed(removed=[rule] if rule else [])


def remove_per_rule_entity_registry_entries(
    hass: Any, entry_id: str, rules: list[Any]
) -> list[str]:
    """Remove entity registry entries belonging to deleted per-rule entities.

    Removing the registry entry also removes the live entity from its platform.
    """

    from homeassistant.helpers import entity_registry as er

    entity_registry = er.async_get(hass)
    entries_for_config_entry = getattr(er, "async_entries_for_config_entry", None)
    if entries_for_config_entry is not None:
        entries = entries_for_config_entry(entity_registry, entry_id)
    else:
        entries = entity_registry.entities.values()

    matches = matching_per_rule_entity_entries(entry_id, rules, entries)
    removed_entity_ids = [entry.entity_id for entry in matches]
    for entity_id in removed_entity_ids:
        entity_registry.async_remove(entity_id)

    return removed_entity_ids


def async_get_runtime(hass: HomeAssistant) -> IndustrialAlarmPanelRuntime:
    """Return the runtime of the loaded config entry (resolved at call time)."""

    from homeassistant.config_entries import ConfigEntryState

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        runtime = getattr(entry, "runtime_data", None)
        if isinstance(runtime, IndustrialAlarmPanelRuntime):
            return runtime
    raise IntegrationNotLoadedError


type IndustrialAlarmConfigEntry = ConfigEntry[IndustrialAlarmPanelRuntime]
