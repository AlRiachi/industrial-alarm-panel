# Rule Preview and Bulk Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe suggested-rule preview, selected creation, generated-rule cleanup, and selected bulk rule deletion with Home Assistant entity registry cleanup.

**Architecture:** Put rule-selection and deletion semantics in a pure Python helper so they can be tested without Home Assistant installed. Wire the helper into websocket commands, then update the existing bundled plain web component UI in `frontend/dist/industrial-alarm-panel.js` because this repo does not include a frontend build pipeline.

**Tech Stack:** Python 3.12, Home Assistant custom integration APIs, pytest/unittest, plain JavaScript custom element.

---

## File Structure

- Create `custom_components/industrial_alarm_panel/rule_management.py`: pure rule-management helpers for generated-rule detection, selected suggested-rule creation, bulk deletion, and expected per-rule entity unique IDs.
- Create `tests/test_rule_management.py`: pure unit tests for the helper module.
- Modify `custom_components/industrial_alarm_panel/websocket_api.py`: add preview and bulk delete websocket commands, selected suggested-rule creation, and entity registry cleanup.
- Modify `custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js`: add preview table, checkbox selection, selected creation, generated cleanup, and selected deletion.
- Modify `custom_components/industrial_alarm_panel/frontend/src/api.ts`: list the new command names for source parity.
- Modify `tests/test_static_ha_compat.py`: static assertions for new frontend/websocket behavior and version bump.
- Modify `README.md`: document preview, selected creation, and cleanup.
- Modify `custom_components/industrial_alarm_panel/const.py`, `custom_components/industrial_alarm_panel/manifest.json`, and `pyproject.toml`: bump version from `1.0.9` to `1.0.10`.

### Task 1: Pure Rule Management Helpers

**Files:**
- Create: `custom_components/industrial_alarm_panel/rule_management.py`
- Create: `tests/test_rule_management.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rule_management.py` with:

```python
import unittest

from custom_components.industrial_alarm_panel.alarm_engine import AlarmEngine
from custom_components.industrial_alarm_panel.alarm_models import (
    AlarmRule,
    AlarmValidationError,
)
from custom_components.industrial_alarm_panel.alarm_store import InMemoryHistoryStore
from custom_components.industrial_alarm_panel.rule_management import (
    delete_rules,
    is_generated_rule_id,
    matching_per_rule_entity_entries,
    per_rule_entity_unique_ids,
    select_suggested_rules,
)


class FakeRegistryEntry:
    def __init__(self, entity_id: str, unique_id: str, config_entry_id: str) -> None:
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.config_entry_id = config_entry_id


def make_rule(rule_id: str, entity_id: str = "sensor.source") -> AlarmRule:
    return AlarmRule.from_dict(
        {
            "id": rule_id,
            "entity_id": entity_id,
            "name": rule_id.replace("_", " ").title(),
            "condition": "above",
            "threshold": 10,
            "priority": "medium",
        }
    )


class RuleManagementTests(unittest.IsolatedAsyncioTestCase):
    def test_generated_rule_ids_use_auto_prefix(self) -> None:
        self.assertTrue(is_generated_rule_id("auto_sensor_main_power_unavailable"))
        self.assertFalse(is_generated_rule_id("manual_temperature_high"))

    def test_select_suggested_rules_keeps_requested_order_and_reports_skips(self) -> None:
        suggested = [
            {"id": "auto_a", "name": "A"},
            {"id": "auto_b", "name": "B"},
            {"id": "auto_c", "name": "C"},
        ]

        selected, skipped = select_suggested_rules(suggested, ["auto_c", "missing", "auto_a"])

        self.assertEqual([rule["id"] for rule in selected], ["auto_c", "auto_a"])
        self.assertEqual(skipped, ["missing"])

    def test_select_suggested_rules_omitted_ids_preserves_all_suggestions(self) -> None:
        suggested = [{"id": "auto_a"}, {"id": "auto_b"}]

        selected, skipped = select_suggested_rules(suggested, None)

        self.assertEqual(selected, suggested)
        self.assertEqual(skipped, [])

    async def test_delete_generated_only_removes_only_auto_rules(self) -> None:
        engine = AlarmEngine(
            [
                make_rule("auto_sensor_power_high_consumption"),
                make_rule("manual_temperature_high"),
            ],
            InMemoryHistoryStore(),
        )

        result = await delete_rules(engine, generated_only=True)

        self.assertEqual(result.deleted_rule_ids, ["auto_sensor_power_high_consumption"])
        self.assertEqual(result.skipped_rule_ids, [])
        self.assertNotIn("auto_sensor_power_high_consumption", engine.rules)
        self.assertIn("manual_temperature_high", engine.rules)

    async def test_delete_explicit_rules_skips_unknown_ids(self) -> None:
        engine = AlarmEngine([make_rule("rule_a"), make_rule("rule_b")], InMemoryHistoryStore())

        result = await delete_rules(engine, rule_ids=["missing", "rule_b"])

        self.assertEqual(result.deleted_rule_ids, ["rule_b"])
        self.assertEqual(result.skipped_rule_ids, ["missing"])
        self.assertIn("rule_a", engine.rules)
        self.assertNotIn("rule_b", engine.rules)

    async def test_delete_requires_explicit_ids_or_generated_only(self) -> None:
        engine = AlarmEngine([], InMemoryHistoryStore())

        with self.assertRaises(AlarmValidationError):
            await delete_rules(engine)

    def test_per_rule_entity_unique_ids_match_existing_entity_classes(self) -> None:
        rule = make_rule("auto_sensor_powertag_main_power_high_consumption")

        self.assertEqual(
            per_rule_entity_unique_ids("entry-1", rule),
            {
                "industrial_alarm_panel_entry-1_alarm_auto_sensor_powertag_main_power_high_consumption",
                "industrial_alarm_panel_entry-1_ack_auto_sensor_powertag_main_power_high_consumption_auto_sensor_powertag_main_power_high_consumption",
                "industrial_alarm_panel_entry-1_shelve_auto_sensor_powertag_main_power_high_consumption_auto_sensor_powertag_main_power_high_consumption",
                "industrial_alarm_panel_entry-1_disable_auto_sensor_powertag_main_power_high_consumption_auto_sensor_powertag_main_power_high_consumption",
            },
        )

    def test_matching_registry_entries_returns_only_current_entry_per_rule_entities(self) -> None:
        rule = make_rule("auto_sensor_power_high_consumption")
        expected_unique_id = (
            "industrial_alarm_panel_entry-1_alarm_auto_sensor_power_high_consumption"
        )
        entries = [
            FakeRegistryEntry("binary_sensor.match", expected_unique_id, "entry-1"),
            FakeRegistryEntry("binary_sensor.other_entry", expected_unique_id, "entry-2"),
            FakeRegistryEntry("sensor.source", "sensor.source_unique", "entry-1"),
        ]

        matches = matching_per_rule_entity_entries("entry-1", [rule], entries)

        self.assertEqual([entry.entity_id for entry in matches], ["binary_sensor.match"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_rule_management.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'custom_components.industrial_alarm_panel.rule_management'`.

- [ ] **Step 3: Add the helper implementation**

Create `custom_components/industrial_alarm_panel/rule_management.py` with:

```python
"""Rule preview, selection, and deletion helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .alarm_models import AlarmRule, AlarmValidationError
from .const import DOMAIN

PER_RULE_BUTTON_ACTIONS = ("ack", "shelve", "disable")


@dataclass(frozen=True)
class RuleDeletionResult:
    """Result from deleting one or more alarm rules."""

    deleted_rules: tuple[AlarmRule, ...]
    skipped_rule_ids: list[str]

    @property
    def deleted_rule_ids(self) -> list[str]:
        """Return deleted rule IDs in deletion order."""

        return [rule.id for rule in self.deleted_rules]


def is_generated_rule_id(rule_id: str) -> bool:
    """Return true if a rule ID follows the suggested-rule convention."""

    return str(rule_id).startswith("auto_")


def select_suggested_rules(
    suggested_rules: Sequence[dict[str, Any]],
    rule_ids: Sequence[str] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Select suggested rule dictionaries by requested IDs."""

    if rule_ids is None:
        return list(suggested_rules), []

    by_id = {str(rule["id"]): rule for rule in suggested_rules}
    selected: list[dict[str, Any]] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for rule_id in rule_ids:
        rule_id = str(rule_id)
        if rule_id in seen:
            continue
        seen.add(rule_id)
        if rule := by_id.get(rule_id):
            selected.append(rule)
        else:
            skipped.append(rule_id)
    return selected, skipped


async def delete_rules(
    engine: Any,
    *,
    rule_ids: Sequence[str] | None = None,
    generated_only: bool = False,
) -> RuleDeletionResult:
    """Delete selected rules from an alarm engine."""

    requested = list(dict.fromkeys(str(rule_id) for rule_id in (rule_ids or [])))
    if not requested and not generated_only:
        raise AlarmValidationError("rule_ids or generated_only is required")

    if generated_only:
        generated_ids = [
            rule_id for rule_id in engine.rules if is_generated_rule_id(rule_id)
        ]
        target_ids = (
            [rule_id for rule_id in requested if rule_id in generated_ids]
            if requested
            else generated_ids
        )
    else:
        target_ids = requested

    deleted_rules: list[AlarmRule] = []
    skipped_rule_ids: list[str] = []
    for rule_id in target_ids:
        rule = engine.rules.get(rule_id)
        if rule is None:
            skipped_rule_ids.append(rule_id)
            continue
        deleted_rules.append(rule)
        await engine.delete_rule(rule_id)

    if generated_only and requested:
        deleted_or_skipped = {rule.id for rule in deleted_rules} | set(skipped_rule_ids)
        skipped_rule_ids.extend(
            rule_id for rule_id in requested if rule_id not in deleted_or_skipped
        )

    return RuleDeletionResult(tuple(deleted_rules), skipped_rule_ids)


def per_rule_entity_unique_ids(entry_id: str, rule: AlarmRule) -> set[str]:
    """Return unique IDs for all Home Assistant entities created for one rule."""

    base = f"{DOMAIN}_{entry_id}"
    unique_ids = {f"{base}_alarm_{rule.id}"}
    unique_ids.update(
        f"{base}_{action}_{rule.slug}_{rule.id}" for action in PER_RULE_BUTTON_ACTIONS
    )
    return unique_ids


def matching_per_rule_entity_entries(
    entry_id: str,
    rules: Iterable[AlarmRule],
    registry_entries: Iterable[Any],
) -> list[Any]:
    """Return registry entries that belong to the deleted per-rule entities."""

    expected_unique_ids: set[str] = set()
    for rule in rules:
        expected_unique_ids.update(per_rule_entity_unique_ids(entry_id, rule))

    return [
        entry
        for entry in registry_entries
        if getattr(entry, "config_entry_id", None) == entry_id
        and getattr(entry, "unique_id", None) in expected_unique_ids
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/test_rule_management.py -q
```

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/industrial_alarm_panel/rule_management.py tests/test_rule_management.py
git commit -m "Add rule management helpers"
```

### Task 2: Websocket Preview, Selected Create, and Bulk Delete

**Files:**
- Modify: `custom_components/industrial_alarm_panel/websocket_api.py`
- Modify: `tests/test_static_ha_compat.py`

- [ ] **Step 1: Write failing static API tests**

In `tests/test_static_ha_compat.py`, replace `test_websocket_registers_suggested_rule_command` with:

```python
    def test_websocket_registers_suggested_rule_management_commands(self) -> None:
        source = Path("custom_components/industrial_alarm_panel/websocket_api.py").read_text()

        self.assertIn("websocket_list_suggested_rules", source)
        self.assertIn("websocket_create_suggested_rules", source)
        self.assertIn("websocket_delete_rules", source)
        self.assertIn("select_suggested_rules", source)
        self.assertIn("delete_rules(", source)
        self.assertIn("generated_only", source)
        self.assertIn("rule_ids", source)
        self.assertIn("remove_per_rule_entity_registry_entries", source)
```

- [ ] **Step 2: Run the static API test to verify it fails**

Run:

```bash
pytest tests/test_static_ha_compat.py::StaticHomeAssistantCompatibilityTests::test_websocket_registers_suggested_rule_management_commands -q
```

Expected: FAIL because `websocket_list_suggested_rules`, `websocket_delete_rules`, and registry cleanup are not present.

- [ ] **Step 3: Modify websocket imports and registration**

In `custom_components/industrial_alarm_panel/websocket_api.py`, add this import:

```python
from .rule_management import (
    delete_rules,
    matching_per_rule_entity_entries,
    select_suggested_rules,
)
```

In `async_register_websocket_api`, register the new commands around the existing rule commands:

```python
    websocket_api.async_register_command(hass, websocket_list_rules)
    websocket_api.async_register_command(hass, websocket_list_suggested_rules)
    websocket_api.async_register_command(hass, websocket_create_rule)
    websocket_api.async_register_command(hass, websocket_create_suggested_rules)
    websocket_api.async_register_command(hass, websocket_update_rule)
    websocket_api.async_register_command(hass, websocket_delete_rule)
    websocket_api.async_register_command(hass, websocket_delete_rules)
```

- [ ] **Step 4: Add shared schemas and suggested-rule preview command**

Add these definitions above `websocket_create_suggested_rules`:

```python
SUGGESTED_RULE_THRESHOLDS_SCHEMA = {
    vol.Optional("power_threshold_w", default=2000): vol.All(
        vol.Coerce(float), vol.Range(min=1)
    ),
    vol.Optional("low_voltage_v", default=207): vol.All(
        vol.Coerce(float), vol.Range(min=1)
    ),
    vol.Optional("high_voltage_v", default=253): vol.All(
        vol.Coerce(float), vol.Range(min=1)
    ),
    vol.Optional("high_solar_water_temp_c", default=75): vol.All(
        vol.Coerce(float), vol.Range(min=1)
    ),
}


def _suggested_rules_for_message(hass: HomeAssistant, msg: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = _runtime(hass)
    return suggest_alarm_rules(
        _sensor_states(hass),
        existing_rule_ids=set(runtime.engine.rules),
        power_threshold_w=msg["power_threshold_w"],
        low_voltage_v=msg["low_voltage_v"],
        high_voltage_v=msg["high_voltage_v"],
        high_solar_water_temp_c=msg["high_solar_water_temp_c"],
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/list_suggested_rules",
        **SUGGESTED_RULE_THRESHOLDS_SCHEMA,
    }
)
@websocket_api.async_response
async def websocket_list_suggested_rules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Preview suggested alarm rules from current Home Assistant sensors."""

    connection.send_result(
        msg["id"],
        {"suggested": _suggested_rules_for_message(hass, msg)},
    )
```

- [ ] **Step 5: Update selected suggested-rule creation**

Replace the `websocket_create_suggested_rules` decorator schema with:

```python
@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/create_suggested_rules",
        **SUGGESTED_RULE_THRESHOLDS_SCHEMA,
        vol.Optional("rule_ids"): [str],
    }
)
```

Replace the body of `websocket_create_suggested_rules` with:

```python
    runtime = _runtime(hass)
    suggested = _suggested_rules_for_message(hass, msg)
    selected, skipped_rule_ids = select_suggested_rules(
        suggested,
        msg.get("rule_ids"),
    )

    created = []
    for rule_data in selected:
        rule = await runtime.engine.create_rule(rule_data)
        created.append(rule.to_dict())

    if created:
        await runtime.rule_store.async_save_rules(runtime.engine.rules.values())
        hass.async_create_task(hass.config_entries.async_reload(runtime.entry_id))

    connection.send_result(
        msg["id"],
        {
            "created_count": len(created),
            "created": created,
            "skipped_rule_ids": skipped_rule_ids,
        },
    )
```

- [ ] **Step 6: Add bulk delete command and registry cleanup**

Add this helper above `websocket_delete_rules`:

```python
def remove_per_rule_entity_registry_entries(
    hass: HomeAssistant,
    entry_id: str,
    rules: list[Any] | tuple[Any, ...],
) -> list[str]:
    """Remove stale HA entity registry entries for deleted per-rule entities."""

    from homeassistant.helpers import entity_registry as er

    entity_registry = er.async_get(hass)
    entries_for_config_entry = getattr(er, "async_entries_for_config_entry", None)
    if entries_for_config_entry:
        registry_entries = entries_for_config_entry(entity_registry, entry_id)
    else:
        registry_entries = list(entity_registry.entities.values())

    removed_entity_ids: list[str] = []
    for entry in matching_per_rule_entity_entries(
        entry_id,
        rules,
        registry_entries,
    ):
        entity_registry.async_remove(entry.entity_id)
        removed_entity_ids.append(entry.entity_id)
    return removed_entity_ids
```

Add the websocket command after `websocket_delete_rule`:

```python
@websocket_api.websocket_command(
    {
        vol.Required("type"): "industrial_alarm_panel/delete_rules",
        vol.Optional("rule_ids"): [str],
        vol.Optional("generated_only", default=False): bool,
    }
)
@websocket_api.async_response
async def websocket_delete_rules(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete multiple alarm rules and stale per-rule entities."""

    runtime = _runtime(hass)
    result = await delete_rules(
        runtime.engine,
        rule_ids=msg.get("rule_ids"),
        generated_only=msg["generated_only"],
    )
    removed_entity_ids = remove_per_rule_entity_registry_entries(
        hass,
        runtime.entry_id,
        result.deleted_rules,
    )
    if result.deleted_rules:
        await runtime.rule_store.async_save_rules(runtime.engine.rules.values())
        hass.async_create_task(hass.config_entries.async_reload(runtime.entry_id))

    connection.send_result(
        msg["id"],
        {
            "deleted_rule_ids": result.deleted_rule_ids,
            "deleted_count": len(result.deleted_rule_ids),
            "skipped_rule_ids": result.skipped_rule_ids,
            "removed_entity_ids": removed_entity_ids,
            "removed_entity_count": len(removed_entity_ids),
        },
    )
```

- [ ] **Step 7: Run the static API test**

Run:

```bash
pytest tests/test_static_ha_compat.py::StaticHomeAssistantCompatibilityTests::test_websocket_registers_suggested_rule_management_commands -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add custom_components/industrial_alarm_panel/websocket_api.py tests/test_static_ha_compat.py
git commit -m "Add websocket rule management commands"
```

### Task 3: Frontend Preview and Bulk Cleanup UI

**Files:**
- Modify: `custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js`
- Modify: `custom_components/industrial_alarm_panel/frontend/src/api.ts`
- Modify: `tests/test_static_ha_compat.py`

- [ ] **Step 1: Write failing frontend static tests**

Add these tests to `tests/test_static_ha_compat.py`:

```python
    def test_frontend_previews_and_selects_suggested_rules(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("list_suggested_rules", source)
        self.assertIn("_previewSuggestedRules", source)
        self.assertIn("_selectedSuggestedRuleIds", source)
        self.assertIn("Create Selected", source)
        self.assertIn("Create All", source)
        self.assertIn("data-suggested-select", source)

    def test_frontend_can_bulk_delete_rules(self) -> None:
        source = Path(
            "custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js"
        ).read_text()

        self.assertIn("delete_rules", source)
        self.assertIn("_selectedRuleIds", source)
        self.assertIn("_deleteSelectedRules", source)
        self.assertIn("_removeAutoGeneratedRules", source)
        self.assertIn("Remove Auto-Generated Rules", source)
        self.assertIn("data-rule-select", source)
```

- [ ] **Step 2: Run frontend static tests to verify they fail**

Run:

```bash
pytest tests/test_static_ha_compat.py::StaticHomeAssistantCompatibilityTests::test_frontend_previews_and_selects_suggested_rules tests/test_static_ha_compat.py::StaticHomeAssistantCompatibilityTests::test_frontend_can_bulk_delete_rules -q
```

Expected: FAIL because the frontend has only immediate suggested-rule creation and no bulk deletion.

- [ ] **Step 3: Add command names to source API**

In `custom_components/industrial_alarm_panel/frontend/src/api.ts`, add:

```typescript
  listSuggestedRules: `${DOMAIN}/list_suggested_rules`,
  createSuggestedRules: `${DOMAIN}/create_suggested_rules`,
  deleteRules: `${DOMAIN}/delete_rules`,
```

The `commands` object should include these next to the existing rule commands:

```typescript
  listRules: `${DOMAIN}/list_rules`,
  listSuggestedRules: `${DOMAIN}/list_suggested_rules`,
  createRule: `${DOMAIN}/create_rule`,
  createSuggestedRules: `${DOMAIN}/create_suggested_rules`,
  updateRule: `${DOMAIN}/update_rule`,
  deleteRule: `${DOMAIN}/delete_rule`,
  deleteRules: `${DOMAIN}/delete_rules`,
```

- [ ] **Step 4: Add frontend state fields**

In the `IndustrialAlarmPanel` constructor in `frontend/dist/industrial-alarm-panel.js`, after `_suggestedRulesResult`, add:

```javascript
    this._suggestedRules = [];
    this._selectedSuggestedRuleIds = new Set();
    this._selectedRuleIds = new Set();
    this._rulesResult = null;
```

- [ ] **Step 5: Prune selected IDs after rules load**

In `_load`, after `this._rules = rules?.rules || [];`, add:

```javascript
      const currentRuleIds = new Set(this._rules.map((rule) => rule.id));
      this._selectedRuleIds = new Set([...this._selectedRuleIds].filter((ruleId) => currentRuleIds.has(ruleId)));
      this._suggestedRules = this._suggestedRules.filter((rule) => !currentRuleIds.has(rule.id));
      this._selectedSuggestedRuleIds = new Set([...this._selectedSuggestedRuleIds].filter((ruleId) => this._suggestedRules.some((rule) => rule.id === ruleId)));
```

- [ ] **Step 6: Replace the suggested-rule controls in `_rulesView`**

In `_rulesView`, define these local values after `const suggestionDraft = this._suggestionDraft;`:

```javascript
    const generatedRules = this._rules.filter((rule) => String(rule.id || "").startsWith("auto_"));
    const selectedRulesCount = this._selectedRuleIds.size;
    const selectedSuggestedCount = this._selectedSuggestedRuleIds.size;
```

Replace the suggested-rule section with:

```javascript
        <div class="suggested-rules">
          <h2>Suggested Rules</h2>
          <div class="suggested-rules-controls">
            <label>High W <input type="number" min="1" step="50" value="${this._escape(suggestionDraft.power_threshold_w)}" data-suggest="power_threshold_w"></label>
            <label>Low V <input type="number" min="1" step="1" value="${this._escape(suggestionDraft.low_voltage_v)}" data-suggest="low_voltage_v"></label>
            <label>High V <input type="number" min="1" step="1" value="${this._escape(suggestionDraft.high_voltage_v)}" data-suggest="high_voltage_v"></label>
            <label>Solar C <input type="number" min="1" step="1" value="${this._escape(suggestionDraft.high_solar_water_temp_c)}" data-suggest="high_solar_water_temp_c"></label>
            <button class="secondary" data-action="preview-suggested-rules">Preview Suggested Rules</button>
            <button class="primary" data-action="create-selected-suggested-rules" ${selectedSuggestedCount ? "" : "disabled"}>Create Selected</button>
            <button class="primary" data-action="create-all-suggested-rules" ${this._suggestedRules.length ? "" : "disabled"}>Create All</button>
            <button class="danger" data-action="remove-auto-generated-rules" ${generatedRules.length ? "" : "disabled"}>Remove Auto-Generated Rules</button>
          </div>
          <div class="rule-action-summary">
            ${this._suggestedRules.length ? `${this._suggestedRules.length} suggestions ready, ${selectedSuggestedCount} selected, ${selectedSuggestedCount * 4} entities estimated` : "Preview suggestions before creating rules"}
            ${generatedRules.length ? ` · ${generatedRules.length} auto-generated rules can be removed` : ""}
          </div>
          ${this._suggestedRulesResult ? `<div class="notice">${this._escape(this._suggestedRulesResult)}</div>` : ""}
          ${this._suggestedRules.length ? this._suggestedRulesTable() : ""}
        </div>
```

Before the rules table, add:

```javascript
        <div class="bulk-actions">
          <span>${selectedRulesCount} selected, ${selectedRulesCount * 4} per-rule entities estimated</span>
          <button class="danger" data-action="delete-selected-rules" ${selectedRulesCount ? "" : "disabled"}>Delete Selected</button>
          ${this._rulesResult ? `<span class="notice inline">${this._escape(this._rulesResult)}</span>` : ""}
        </div>
```

Update the rules table header and body to include a checkbox column:

```javascript
            <thead><tr><th>Select</th><th>ID</th><th>Entity</th><th>Name</th><th>Condition</th><th>Priority</th><th>Enabled</th></tr></thead>
            <tbody>${this._rules.map((rule) => `<tr><td><input type="checkbox" data-rule-select="${this._escape(rule.id)}" ${this._selectedRuleIds.has(rule.id) ? "checked" : ""}></td><td>${this._escape(rule.id)}</td><td>${this._escape(rule.entity_id)}</td><td>${this._escape(rule.name)}</td><td>${this._escape(rule.condition)}</td><td>${this._escape(rule.priority)}</td><td>${rule.enabled ? "yes" : "no"}</td></tr>`).join("")}</tbody>
```

- [ ] **Step 7: Add suggested preview table renderer**

Add this method after `_rulesView`:

```javascript
  _suggestedRulesTable() {
    return `
      <div class="table-shell suggested-preview">
        <table data-table-id="suggested-rules">
          <thead><tr><th>Select</th><th>ID</th><th>Entity</th><th>Name</th><th>Condition</th><th>Threshold</th><th>Priority</th></tr></thead>
          <tbody>${this._suggestedRules.map((rule) => `<tr><td><input type="checkbox" data-suggested-select="${this._escape(rule.id)}" ${this._selectedSuggestedRuleIds.has(rule.id) ? "checked" : ""}></td><td>${this._escape(rule.id)}</td><td>${this._escape(rule.entity_id)}</td><td>${this._escape(rule.name)}</td><td>${this._escape(rule.condition)}</td><td>${this._escape(rule.threshold ?? "")}</td><td>${this._escape(rule.priority)}</td></tr>`).join("")}</tbody>
        </table>
      </div>
    `;
  }
```

- [ ] **Step 8: Wire new frontend actions**

In `_wire`, replace the existing `create-suggested-rules` listener with:

```javascript
    this.shadowRoot.querySelector("[data-action='preview-suggested-rules']")?.addEventListener("click", () => this._previewSuggestedRules());
    this.shadowRoot.querySelector("[data-action='create-selected-suggested-rules']")?.addEventListener("click", () => this._createSelectedSuggestedRules());
    this.shadowRoot.querySelector("[data-action='create-all-suggested-rules']")?.addEventListener("click", () => this._createAllSuggestedRules());
    this.shadowRoot.querySelector("[data-action='remove-auto-generated-rules']")?.addEventListener("click", () => this._removeAutoGeneratedRules());
    this.shadowRoot.querySelector("[data-action='delete-selected-rules']")?.addEventListener("click", () => this._deleteSelectedRules());
```

Add checkbox listeners before `_wireColumnResizers()`:

```javascript
    this.shadowRoot.querySelectorAll("[data-suggested-select]").forEach((field) => {
      field.addEventListener("change", () => {
        this._setMembership(this._selectedSuggestedRuleIds, field.dataset.suggestedSelect, field.checked);
        this._render();
      });
    });
    this.shadowRoot.querySelectorAll("[data-rule-select]").forEach((field) => {
      field.addEventListener("change", () => {
        this._setMembership(this._selectedRuleIds, field.dataset.ruleSelect, field.checked);
        this._render();
      });
    });
```

- [ ] **Step 9: Add frontend action methods**

Replace `_createSuggestedRules` with these methods:

```javascript
  _suggestionPayload() {
    const fields = {};
    Object.entries(this._suggestionDraft).forEach(([key, value]) => {
      if (value !== "") fields[key] = Number(value);
    });
    return fields;
  }

  _setMembership(set, value, selected) {
    if (!value) return;
    if (selected) set.add(value);
    else set.delete(value);
  }

  async _previewSuggestedRules() {
    try {
      const result = await this._callWS({
        type: "industrial_alarm_panel/list_suggested_rules",
        ...this._suggestionPayload(),
      });
      this._suggestedRules = result?.suggested || [];
      this._selectedSuggestedRuleIds = new Set(this._suggestedRules.map((rule) => rule.id));
      this._suggestedRulesResult = this._suggestedRules.length
        ? `${this._suggestedRules.length} suggested rules found`
        : "No new suggested alarm rules";
    } catch (err) {
      this._suggestedRulesResult = err.message || String(err);
    }
    this._render();
  }

  async _createSelectedSuggestedRules() {
    const ruleIds = [...this._selectedSuggestedRuleIds];
    if (!ruleIds.length) return;
    const entityCount = ruleIds.length * 4;
    if (!window.confirm(`Create ${ruleIds.length} suggested rules and about ${entityCount} Home Assistant entities?`)) return;
    await this._createSuggestedRules(ruleIds);
  }

  async _createAllSuggestedRules() {
    const ruleIds = this._suggestedRules.map((rule) => rule.id);
    if (!ruleIds.length) return;
    const entityCount = ruleIds.length * 4;
    if (!window.confirm(`Create all ${ruleIds.length} suggested rules and about ${entityCount} Home Assistant entities?`)) return;
    await this._createSuggestedRules(ruleIds);
  }

  async _createSuggestedRules(ruleIds) {
    try {
      const result = await this._callWS({
        type: "industrial_alarm_panel/create_suggested_rules",
        ...this._suggestionPayload(),
        rule_ids: ruleIds,
      });
      const count = result?.created_count || 0;
      const skipped = result?.skipped_rule_ids?.length || 0;
      this._suggestedRulesResult = count
        ? `Created ${count} suggested alarm rules${skipped ? `, skipped ${skipped}` : ""}`
        : `No new suggested alarm rules${skipped ? `, skipped ${skipped}` : ""}`;
      this._selectedSuggestedRuleIds = new Set();
      await this._load();
    } catch (err) {
      this._suggestedRulesResult = err.message || String(err);
    }
    this._render();
  }

  async _deleteRules(payload, count, label) {
    const entityCount = count * 4;
    if (!count) return;
    if (!window.confirm(`${label} ${count} rules and about ${entityCount} Home Assistant entities? Source entities will not be removed.`)) return;
    try {
      const result = await this._callWS({
        type: "industrial_alarm_panel/delete_rules",
        ...payload,
      });
      const deleted = result?.deleted_count || 0;
      const removed = result?.removed_entity_count || 0;
      const skipped = result?.skipped_rule_ids?.length || 0;
      this._rulesResult = `Deleted ${deleted} rules, removed ${removed} entities${skipped ? `, skipped ${skipped}` : ""}`;
      this._selectedRuleIds = new Set();
      await this._load();
    } catch (err) {
      this._rulesResult = err.message || String(err);
    }
    this._render();
  }

  async _deleteSelectedRules() {
    const ruleIds = [...this._selectedRuleIds];
    await this._deleteRules({ rule_ids: ruleIds }, ruleIds.length, "Delete selected");
  }

  async _removeAutoGeneratedRules() {
    const count = this._rules.filter((rule) => String(rule.id || "").startsWith("auto_")).length;
    await this._deleteRules({ generated_only: true }, count, "Remove auto-generated");
  }
```

- [ ] **Step 10: Preserve form-editing refresh behavior and add styles**

Update `_isEditingRulesForm` to:

```javascript
    return Boolean(active.matches("[data-new], [data-suggest]"));
```

Keep checkboxes out of this selector so checkbox clicks can immediately re-render selection state.

In `_styles`, add:

```css
      .bulk-actions, .rule-action-summary { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 8px 0 12px; color: #b8c7d4; font-size: 13px; }
      .notice.inline { margin-top: 0; }
      .suggested-preview { padding: 10px 0 0; }
      input[type="checkbox"] { min-width: 0; width: 18px; height: 18px; }
```

- [ ] **Step 11: Run frontend static tests**

Run:

```bash
pytest tests/test_static_ha_compat.py::StaticHomeAssistantCompatibilityTests::test_frontend_previews_and_selects_suggested_rules tests/test_static_ha_compat.py::StaticHomeAssistantCompatibilityTests::test_frontend_can_bulk_delete_rules -q
node --check custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js
```

Expected: both pytest tests PASS and `node --check` exits 0.

- [ ] **Step 12: Commit**

```bash
git add custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js custom_components/industrial_alarm_panel/frontend/src/api.ts tests/test_static_ha_compat.py
git commit -m "Add frontend rule preview and bulk cleanup"
```

### Task 4: Version and Documentation

**Files:**
- Modify: `custom_components/industrial_alarm_panel/const.py`
- Modify: `custom_components/industrial_alarm_panel/manifest.json`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `tests/test_static_ha_compat.py`

- [ ] **Step 1: Write the failing version expectation**

In `tests/test_static_ha_compat.py`, rename the version test to `test_frontend_version_is_bumped_for_rule_management_ui` and update assertions:

```python
    def test_frontend_version_is_bumped_for_rule_management_ui(self) -> None:
        const_source = Path("custom_components/industrial_alarm_panel/const.py").read_text()
        manifest_source = Path(
            "custom_components/industrial_alarm_panel/manifest.json"
        ).read_text()
        pyproject_source = Path("pyproject.toml").read_text()

        self.assertIn('VERSION = "1.0.10"', const_source)
        self.assertIn('"version": "1.0.10"', manifest_source)
        self.assertIn('version = "1.0.10"', pyproject_source)
```

- [ ] **Step 2: Run the version test to verify it fails**

Run:

```bash
pytest tests/test_static_ha_compat.py::StaticHomeAssistantCompatibilityTests::test_frontend_version_is_bumped_for_rule_management_ui -q
```

Expected: FAIL because the repo still says `1.0.9`.

- [ ] **Step 3: Bump versions**

Change:

- `custom_components/industrial_alarm_panel/const.py`: `VERSION = "1.0.10"`
- `custom_components/industrial_alarm_panel/manifest.json`: `"version": "1.0.10"`
- `pyproject.toml`: `version = "1.0.10"`

- [ ] **Step 4: Update README suggested rules section**

Replace the first paragraph under `### Suggested Rules` with:

```markdown
Open **Industrial Alarms > Rules > Suggested Rules** and click **Preview Suggested Rules** to scan current Home Assistant `sensor.*` entities before creating anything. Select the suggestions you want, then click **Create Selected**. **Create All** is still available after preview, but it asks for confirmation and shows the estimated Home Assistant entity count.
```

Replace the paragraph that starts `The generator detects candidates` with:

```markdown
The generator detects candidates from `device_class`, unit of measurement, entity ID, and friendly name. It skips generated rule IDs that already exist so repeated previews or creates do not duplicate rules. Generated suggested rules use IDs beginning with `auto_`.
```

Add this paragraph after that:

```markdown
If too many suggested rules were created, use **Remove Auto-Generated Rules** in the same section. It removes stored `auto_` rules and the per-rule alarm/button entities created by this integration, but it does not remove the original source sensors. For manual cleanup, select rows in the Rules table and click **Delete Selected**.
```

- [ ] **Step 5: Run version and static tests**

Run:

```bash
pytest tests/test_static_ha_compat.py -q
```

Expected: all static tests PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/industrial_alarm_panel/const.py custom_components/industrial_alarm_panel/manifest.json pyproject.toml README.md tests/test_static_ha_compat.py
git commit -m "Document rule management workflow"
```

### Task 5: Final Verification

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run focused Python tests**

Run:

```bash
pytest tests/test_rule_management.py tests/test_rule_suggestions.py tests/test_alarm_engine.py tests/test_static_ha_compat.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run all tests available in this environment**

Run:

```bash
pytest -q
```

Expected: tests that do not require Home Assistant PASS, and Home Assistant import tests SKIP if Home Assistant is not installed.

- [ ] **Step 3: Check frontend JavaScript syntax**

Run:

```bash
node --check custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js
```

Expected: exits 0 with no syntax errors.

- [ ] **Step 4: Inspect final git diff**

Run:

```bash
git status --short
git diff --stat HEAD
```

Expected: only intended files changed since the last task commit, or a clean worktree if each task was committed. `prompt.md` may remain untracked from before this work and must not be committed unless the user explicitly asks.

- [ ] **Step 5: Final commit if verification caused fixups**

If verification required fixup edits, commit only those fixups:

```bash
git add custom_components/industrial_alarm_panel tests README.md pyproject.toml
git commit -m "Fix rule management verification issues"
```

If no fixups were needed, do not create an empty commit.
