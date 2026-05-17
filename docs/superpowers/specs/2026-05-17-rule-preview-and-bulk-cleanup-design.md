# Rule Preview and Bulk Cleanup Design

## Context

The current Rules tab has a `Create Suggested Rules` action that scans Home
Assistant sensors and immediately creates every generated suggestion. Each stored
rule creates one binary sensor and three per-rule action buttons after the
integration reloads. An accidental bulk suggested-rule creation can therefore add
hundreds of Home Assistant entities.

The feature needs two related outcomes:

- High priority: make accidental suggested-rule creation recoverable and harder
  to trigger.
- Secondary: make normal rule cleanup easier through selected bulk deletion.

## Goals

- Let operators preview suggested rules before creating them.
- Let operators create only selected suggestions.
- Provide a dedicated cleanup action for generated rules.
- Provide selected bulk deletion for any rules in the Rules table.
- Delete stale per-rule Home Assistant entity registry entries created by this
  integration when rules are removed.
- Never delete the source entities monitored by rules.

## Non-Goals

- No full undo stack or batch history system.
- No changes to alarm lifecycle behavior.
- No changes to suggested-rule heuristics beyond exposing them as a preview.
- No automatic deletion of user automations, dashboards, or references that may
  point at removed alarm entities.

## Backend API

Add a preview websocket command:

- `industrial_alarm_panel/list_suggested_rules`
- Input: the same threshold fields currently accepted by
  `create_suggested_rules`.
- Output: `suggested`, a list of rule dictionaries that are not already present
  in `runtime.engine.rules`.
- Behavior: read-only. It must not save rules, reload the entry, or create
  entities.

Update suggested-rule creation:

- `industrial_alarm_panel/create_suggested_rules` should accept optional
  `rule_ids`.
- If `rule_ids` is omitted, preserve existing behavior for compatibility.
- If `rule_ids` is provided, create only matching suggested rules.
- Return `created_count`, `created`, and `skipped_rule_ids`.

Add a bulk delete websocket command:

- `industrial_alarm_panel/delete_rules`
- Input:
  - `rule_ids`: optional explicit list of rule IDs.
  - `generated_only`: optional boolean, default `false`.
- Validation:
  - At least one of `rule_ids` or `generated_only` must be supplied.
  - If `generated_only` is true, the delete set is restricted to generated rule
    IDs.
  - Unknown explicit rule IDs are reported as skipped rather than failing the
    entire operation.
- Output: `deleted_rule_ids`, `deleted_count`, `skipped_rule_ids`,
  `removed_entity_ids`, and `removed_entity_count`.

Generated rules are identified by the existing stable ID convention:

- A generated rule ID starts with `auto_`.
- Only rules in this integration's rule store are eligible. Matching source
  sensor IDs or unrelated Home Assistant entities are never targeted.

## Entity Registry Cleanup

Deleting a rule removes the stored rule and its runtime state. The new bulk
delete command should also remove stale registry entries for the integration's
per-rule entities:

- `binary_sensor` alarm entity for the rule.
- `button` acknowledge entity for the rule.
- `button` shelve entity for the rule.
- `button` disable entity for the rule.

Entity registry cleanup should use Home Assistant's entity registry helper:

- Import `homeassistant.helpers.entity_registry as er`.
- Use `er.async_get(hass)` to access the registry.
- Find entries for the current config entry whose `unique_id` matches the
  integration's per-rule unique-id format.
- Call `entity_registry.async_remove(entity_id)` for matching entries.

Cleanup must be best-effort. If a registry entry does not exist, the command
should still delete the rule and report the entries it did remove.

After deleting rules and registry entries, save the rule store and reload the
config entry once.

## Frontend Workflow

The Rules tab gets a suggested-rule preview section:

- Threshold inputs remain in place.
- Replace the single immediate create action with:
  - `Preview Suggested Rules`.
  - A preview table with checkboxes, entity, name, condition, threshold, and
    priority.
  - `Create Selected`.
  - `Create All`, shown only after preview and using the preview count.
- The UI should show how many Home Assistant entities selected suggestions will
  create. Use four entities per selected rule.

The Rules table gets bulk selection:

- Add a checkbox column.
- Add a selected count.
- Add `Delete Selected`.
- Add a prominent `Remove Auto-Generated Rules` action in the suggested-rule
  section because accidental generated-rule cleanup is the priority use case.

Destructive actions need explicit confirmation:

- `Remove Auto-Generated Rules` confirmation includes the count of matching
  generated rules and the estimated per-rule entity count.
- `Delete Selected` confirmation includes the selected rule count and estimated
  per-rule entity count.

The confirmation can use `window.confirm` for this iteration to stay consistent
with the existing plain web component and avoid adding modal infrastructure.

## Error Handling

- Preview errors show an inline error in the suggested-rule section.
- Create and delete results show inline notices with counts.
- If a bulk delete partially skips unknown rule IDs, the notice should include
  the skipped count.
- Existing rule form drafts must remain protected from refresh while editing.

## Testing

Python tests:

- Suggested-rule preview command returns generated candidates without creating
  rules.
- Creating suggested rules with `rule_ids` creates only selected suggestions.
- Bulk deleting with `generated_only` removes only `auto_` rules.
- Bulk deleting explicit rules removes selected rules and skips unknown IDs.
- Entity registry cleanup computes the expected unique IDs for per-rule entities
  and removes matching registry entries.

Frontend/static tests:

- The bundled frontend contains the new preview command.
- The bundled frontend contains selected suggested-rule creation.
- The bundled frontend contains bulk deletion and generated-rule cleanup actions.
- The Rules table contains checkbox selection.

## Compatibility

The existing `create_suggested_rules` behavior remains compatible when no
`rule_ids` argument is provided. Existing service APIs remain unchanged. This
feature is exposed through the panel websocket API because the issue is panel
workflow and cleanup related.
