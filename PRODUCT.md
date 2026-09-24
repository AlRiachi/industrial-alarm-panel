# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Home Assistant users installing a public HACS integration: homeowners with solar, meters and appliances, and people running small plants or technical rooms. One person is usually both the "operator" and the administrator.

They look at the panel in three situations:
- **Desktop browser:** the HA sidebar on a PC. Setting up rules, reviewing history, clearing the backlog.
- **Phone:** the HA companion app, usually right after a notification. Seeing what fired and acknowledging or shelving it, one-handed, on a narrow screen.
- **Wall tablet or kiosk:** an always-on screen read from a distance and operated by touch. Seeing at a glance whether anything is wrong and silencing the horn.

## Product Purpose

A DCS-style alarm annunciator for Home Assistant. Rules watch HA entities, and alarms move through a managed lifecycle (active, acknowledged, cleared, shelved, disabled) with priorities, sound, and an operator history.

It turns scattered automations and notifications into one place that answers three questions: what is abnormal now, what needs my acknowledgement, and what happened. Success means an abnormal condition is noticed, understood and acted on quickly, without alarm fatigue.

## Positioning

It brings real control-room alarm management to Home Assistant: ISA-18.2 lifecycle semantics, per-alarm acknowledgement, shelving with expiry, horn silencing, suggested rules and an audit trail. Ordinary HA notifications and automations have none of these.

## Operating Context

- **Integration:** runs as a custom sidebar panel (`/industrial-alarms`) inside the Home Assistant frontend, alongside HA's own UI. It also creates HA entities, services and websocket commands.
- **Sound:** comes from the browser (after a user gesture) and/or HA media players.
- **Updates:** alarm updates are pushed over the HA event bus.

## Capabilities and Constraints

- **Alarm lifecycle:** NORMAL, ACTIVE_UNACK, ACTIVE_ACK, CLEARED_UNACK, SHELVED, DISABLED.
- **Priorities:** critical, high, medium, low, info, status.
- **Rules:** above/below/equal/contains/on/off/state-changed/unavailable conditions, with delays, deadbands and repeats. Suggested rules can be previewed and bulk-created or deleted.
- **Operator actions:**
  - acknowledge one or all
  - silence the horn
  - shelve with preset durations (1h to 7d)
  - enable and disable rules
- **Panel tabs:** Active, Unacknowledged, History, Shelved, Disabled, Rules, Settings.
- **In the original spec but not yet built in the UI:** alarm details drawer, history filters and CSV export, rule edit/clone/enable toggle, rule test against current state, compact density option.
- **Technical constraints:** the panel is a single dependency-free custom element (vanilla JS, shadow DOM, no build step) shipped in `frontend/dist/`. It must work inside HA's frontend, respect HA's sidebar/`narrow` behaviour, and not depend on external CDNs.

## Evidence on Hand

- Screenshot of the current panel: `docs/images/industrial-alarm-panel-preview.png`.
- Original product spec: `prompt.md`.
- No real user testimonials or install counts exist, and none may be invented.

## Product Principles

1. **Abnormal must stand out; normal must stay quiet.** Attention is the scarce resource. Follow ISA-101 practice: colour signals abnormal state and never decorates.
2. **Priority is always readable redundantly.** Shape, colour and number together, so it works for colour-blind users and on dim or glaring screens.
3. **The next action is one tap away.** Acknowledge, silence and shelve are always reachable, whether on a desktop, a phone or a wall tablet.
4. **Lifecycle truth over decoration.** Every visual state maps to an ISA-18.2 lifecycle state, and flashing means "unacknowledged" only.
5. **Safe for strangers' homes and plants.** Defaults, wording and destructive actions must make sense to any HACS user and confirm before bulk changes.

## Accessibility & Inclusion

- **Readability:** WCAG 2.1 AA contrast, and priority must never be conveyed by colour alone.
- **Flashing:** stays below 3 Hz and respects `prefers-reduced-motion` (fall back to a steady marker).
- **Touch:** targets of at least 44px on phone and tablet.
- **Keyboard:** operable on desktop.
