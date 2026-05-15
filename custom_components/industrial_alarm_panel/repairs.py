"""Repairs support for Industrial Alarm Panel."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN


async def async_create_repair_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Create basic repair warnings for invalid runtime configuration."""

    runtime = hass.data[DOMAIN].get(entry_id)
    if runtime is None:
        return

    for player in runtime.sound_manager.media_players:
        if player not in hass.states.async_entity_ids("media_player"):
            ir.async_create_issue(
                hass,
                DOMAIN,
                f"missing_media_player_{player}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="missing_media_player",
                translation_placeholders={"entity_id": player},
            )

    for rule in runtime.engine.rules.values():
        if rule.entity_id and hass.states.get(rule.entity_id) is None:
            ir.async_create_issue(
                hass,
                DOMAIN,
                f"missing_source_{rule.id}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="missing_source_entity",
                translation_placeholders={
                    "rule_id": rule.id,
                    "entity_id": rule.entity_id,
                },
            )
