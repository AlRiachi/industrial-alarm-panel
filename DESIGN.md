---
name: Industrial Alarm Panel
description: A cockpit crew-alerting display for Home Assistant alarms, dark when normal and lit only by what is abnormal.
colors:
  glass-black: "#05080b"
  panel: "#0b1116"
  panel-raised: "#0f171d"
  key-face: "#0a0f13"
  well: "#080d11"
  hairline: "#1c2730"
  hairline-strong: "#2a3843"
  text: "#d8e1e7"
  text-dim: "#a3b0ba"
  text-faint: "#7d8b96"
  focus: "#7fd8ff"
  warning-red: "#ff4036"
  caution-amber: "#ffab1a"
  medium-yellow: "#f0d23a"
  advisory-cyan: "#3cc8e2"
  info-white: "#e9eef2"
  lit-ink: "#050505"
  destructive-text: "#ff8b84"
  destructive-line: "#6b2a27"
typography:
  display:
    fontFamily: "B612, Segoe UI, Roboto, system-ui, sans-serif"
    fontSize: "34px"
    fontWeight: 700
    lineHeight: 1
    fontFeature: "tnum"
  display-narrow:
    fontFamily: "B612, Segoe UI, Roboto, system-ui, sans-serif"
    fontSize: "40px"
    fontWeight: 700
    lineHeight: 1.05
    fontFeature: "tnum"
  headline:
    fontFamily: "B612, Segoe UI, Roboto, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: "0.04em"
  title:
    fontFamily: "B612, Segoe UI, Roboto, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.25
    letterSpacing: "0.06em"
  message:
    fontFamily: "B612, Segoe UI, Roboto, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    letterSpacing: "0.05em"
  body:
    fontFamily: "B612, Segoe UI, Roboto, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "tnum"
  data:
    fontFamily: "B612, Segoe UI, Roboto, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 400
    fontFeature: "tnum"
  key-face:
    fontFamily: "B612, Segoe UI, Roboto, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "0.12em"
  caption:
    fontFamily: "B612, Segoe UI, Roboto, system-ui, sans-serif"
    fontSize: "10.5px"
    fontWeight: 400
    letterSpacing: "0.14em"
  mono:
    fontFamily: "B612 Mono, ui-monospace, Cascadia Mono, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
rounded:
  hard: "3px"
  dialog: "4px"
  pill: "12px"
spacing:
  hair: "2px"
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  touch: "44px"
components:
  master-key:
    backgroundColor: "{colors.key-face}"
    textColor: "{colors.text-faint}"
    typography: "{typography.key-face}"
    rounded: "{rounded.hard}"
    size: "112px x 64px min"
  master-key-warn-lit:
    backgroundColor: "{colors.warning-red}"
    textColor: "#1a0200"
  master-key-caut-lit:
    backgroundColor: "{colors.caution-amber}"
    textColor: "#1a0e00"
  button-action:
    backgroundColor: "#0a1015"
    textColor: "{colors.text}"
    rounded: "{rounded.hard}"
    padding: "0 14px"
    height: "44px"
  button-action-hover:
    backgroundColor: "#111b22"
  button-danger:
    backgroundColor: "#0a1015"
    textColor: "{colors.destructive-text}"
    rounded: "{rounded.hard}"
    height: "44px"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.text-dim}"
    rounded: "{rounded.hard}"
    padding: "6px 10px"
    height: "36px"
  chip-selected:
    textColor: "{colors.text}"
  field:
    backgroundColor: "{colors.well}"
    textColor: "{colors.text}"
    rounded: "{rounded.hard}"
    padding: "7px 10px"
    height: "36px"
  page-tab:
    backgroundColor: "transparent"
    textColor: "{colors.text-dim}"
    padding: "11px 12px 9px"
  page-tab-selected:
    textColor: "{colors.text}"
  stack-row:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    typography: "{typography.message}"
    padding: "0 14px"
    height: "54px"
  stack-row-selected:
    backgroundColor: "#111c24"
  status-page:
    backgroundColor: "{colors.panel-raised}"
    textColor: "{colors.text}"
    padding: "14px 16px"
  annunciator-tile:
    backgroundColor: "{colors.well}"
    textColor: "{colors.text-dim}"
    rounded: "{rounded.hard}"
    padding: "8px 9px"
    height: "76px"
---

# Design System: Industrial Alarm Panel

Source of truth: the `:host` block of `_styles()` and the `glyph()` function in `custom_components/industrial_alarm_panel/frontend/dist/industrial-alarm-panel.js`. The fonts are self-hosted in `frontend/dist/fonts/` (B612 Regular and Bold, B612 Mono Regular, all OFL). If this file and that stylesheet disagree, the stylesheet is correct and this file needs updating.

## Overview

**Creative North Star: "The Dark Cockpit"**

The panel works like an aircraft crew-alerting display (EICAS/ECAM). It is a near-black glass screen with grey-white text. At the top, a master strip holds backlit WARNING and CAUTION pushbuttons. Below it is one priority-ranked alert stack, and the selected alert's status page sits beside the stack. The screen stays dark and quiet while things are normal. Colour appears only when something is abnormal, and flashing means only that something is still unacknowledged. The default for this category is a SCADA table filled with colour, and this system does not follow it.

The layout is dense like an instrument panel. Rows are separated by hairlines and all numbers use tabular figures. Short labels are set in tracked uppercase, in the style of annunciator captions. Depth comes from three near-black tones and 1px lines, not shadows. Priority is always shown three ways at once: by the glyph's shape, the number inside it, and its colour. The alarm's lifecycle state is shown by how the glyph is drawn, not by a different hue.

The typeface is B612, the face Airbus designed for cockpit displays. It is used for everything, and B612 Mono is used for tags, codes and shelve durations. Motion is limited to two things: the unacknowledged flash, and a 150 ms unfold when a phone opens a status page in place.

**Key Characteristics:**
- True-black glass surface; the normal state is grey-white and unlit.
- Five priority colours, used only on abnormal items and the master keys.
- Priority glyphs combine shape, number and colour; state marks are filled, hollow, struck or dashed.
- Square backlit pushbuttons, each with a caption bar.
- Hairlines and tonal steps instead of shadows; 3px corners throughout.
- On phones, the screen collapses to the single next decision.

## Colors

The palette is almost entirely blue-black and grey. Five saturated priority colours are the only chroma on the screen, and they appear only when something is abnormal.

### Primary
The priority colours all share one role: signalling an abnormal state. None of them is a brand accent.
- **Warning Red** (warning-red): critical priority (1). Lights the MASTER WARN key face, critical glyphs, critical alarm messages while active, critical trend limits and annunciator tiles, and error borders.
- **Caution Amber** (caution-amber): high priority (2). Lights the MASTER CAUT key face and high-priority glyphs and messages. It also marks the sounding-horn state and the unack count on page tabs, which are both calls for attention.
- **Medium Yellow** (medium-yellow): medium priority (3). Used on glyphs, messages and tiles only.
- **Advisory Cyan** (advisory-cyan): low priority (4). Used on glyphs, messages and tiles only.
- **Info White** (info-white): info (5) and status (6). These glyphs are always drawn as outlines, never filled, so they do not compete with the four real priority levels.

### Neutral
- **Glass Black** (glass-black): the host background and the sticky table-header fill.
- **Panel** (panel): the master strip, the page selector and the suggest-rules band.
- **Panel Raised** (panel-raised): the status page, the phone's next-decision block, and the confirm dialog.
- **Key Face** (key-face): the unlit pushbutton face and the horn housing. **Well** (well): the recessed fill of fields, annunciator tiles and switches. These two tones sit darker than the panels so that controls read as inset.
- **Hairline** (hairline) and **Hairline Strong** (hairline-strong): row dividers and section rules, and control borders. Hairline Strong also fills the selected segment of segmented controls.
- **Text** (text), **Text Dim** (text-dim), **Text Faint** (text-faint): three levels of ink. Primary readings and messages use Text. Secondary data and times use Text Dim. Captions, column heads and zero counts use Text Faint (about 5.7:1 on glass-black, so it still passes AA).
- **Lit Ink** (lit-ink): the numeral inside a filled glyph. Lit key faces instead use a dark tint of their own hue (`#1a0200` on red, `#1a0e00` on amber).
- **Focus** (focus): the 2px focus outline and inline text links. Its job is interaction, not alarm state.
- **Destructive Text / Destructive Line** (destructive-text, destructive-line): the text and border of danger buttons and chips (disable, delete), and form errors. This is a muted red, so a destructive control never looks like an active critical alarm.

### Named Rules
**The Dark Cockpit Rule.** Nothing is lit unless something is abnormal. A priority colour may appear only on an item in an abnormal lifecycle state, on the master key or legend count that summarises those items, or on that item's trend limit. Chrome, headings, navigation and empty states stay grey-white.

**The Lit Face Rule.** A lit surface is filled with its priority colour and carries dark ink. Priority colour is never used as text on another priority colour, and never as a tint wash across a whole row.

## Typography

**Display Font:** B612 (with Segoe UI, Roboto, system-ui)
**Body Font:** B612, 14px/1.45 at the host
**Label/Mono Font:** B612 Mono (with ui-monospace, Cascadia Mono, Consolas)

**Character:** B612 was built for legibility on avionics displays, and its sturdy, open shapes stay readable on a wall tablet across a room. The panel sets `font-variant-numeric: tabular-nums`, so values and times line up in columns and do not shift as they update.

### Hierarchy
- **Display** (700, 34px, line-height 1): the live reading on the status page, with the unit in 15px Text Dim. On phones, the next-decision reading uses **Display Narrow** (700, 40px).
- **Headline** (400, 22px, 1.15, +0.04em, uppercase): the alarm name in the phone's next-decision block, coloured by priority. When nothing needs a decision, a calm version is used instead: 18px sentence case in Text.
- **Title** (400, 15px, 1.25, +0.06em, uppercase, balanced wrap): the status-page heading.
- **Message** (400, 13px, +0.05em, uppercase): alarm messages in the stack. The area and system line under each message is 11.5px Text Faint.
- **Body** (400, 14px, 1.45): base prose, dialogs and the SYS page. **Data** (12.5px) is used for tables, facts, instructions and timelines.
- **Key Face** (700, 13px, +0.12em, uppercase): the words on the pushbuttons and action buttons (action buttons use 12.5px).
- **Caption** (400, 10.5px, +0.14em, uppercase, Text Faint or Text Dim): column heads, fact labels, trend axes, pushbutton caption bars (10px), SYS section heads (11px, +0.16em).
- **Mono** (400, 11 to 12px): tags, entity-derived codes, shelve durations, keyboard keys, and the numeral inside glyphs (10px).

### Named Rules
**The Caption Rule.** Tracked uppercase text is a caption that names a value or a control, like LIMIT, SINCE, INSTRUCTIONS or CRITICAL 1. Each caption labels data sitting directly next to it. It is never a decorative line above a heading.

**The Steady Numerals Rule.** Every value, count and time is rendered with tabular figures. Clocks use 24-hour time with seconds on the alert stack.

## Layout

The layout is an app shell with three bands stacked at the top. The **master strip** is a five-column grid: menu (on narrow screens only), WARN, CAUT, the priority legend filling the remaining width, the horn housing, and ACK ALL. Below it are the **page selector** (ALERTS, UNACK, HISTORY, SHELVED, DISABLED, RULES, SYS, each with a count) and then the **filter line**. Under the bands, alarm pages split into a ranked **stack** (`minmax(0, 2fr)`) and a **status page** (`minmax(320px, 1fr)`), divided by a single hairline.

- **Stack rows** use a six-column grid: glyph 26px, time 92px, tag 150px, message (fills the rest), value 118px, state 104px. Columns are 12px apart, rows have 14px side padding, and each row is at least 54px tall (38px in compact density).
- **Wide alarm pages** (not narrow and wider than 860px) lock the panel to `100vh`. The stack and the status page then scroll independently, and the status page's action block stays pinned to its bottom edge. This keeps ACK and SHELVE reachable on tablets.
- **At 1100px or less**, the tag column is dropped.
- **At 860px or less**, the master strip wraps to two columns, ACK ALL spans the full width, and the split becomes a single column. Rows collapse to glyph, message and value.
- **Narrow** (Home Assistant's `narrow` property) switches to phone mode. The master strip shows the menu, WARN and CAUT, followed by a full-width horn bar and the legend. A **next-decision block** shows the top unacknowledged alarm in large type with ACK and ACK ALL. The side status page is hidden, and tapping a row unfolds its status page directly under that row.
- **Touch** (`pointer: coarse` or at most 1366px wide, and always when narrow): every chip, field, segment, shelve button and horn button is at least 44px.
- **Rhythm:** internal padding is 12px at the edges of the bands and 16px inside the status page. Gaps between controls are 6 to 10px. Tiles on the annunciator board have 6px gutters.

## Elevation & Depth

The panel is flat. Depth comes from tone: glass-black is the base, panel and panel-raised sit on top of it, and key-face and well sit below it as insets. Hairlines separate every band, row and section. Selection is shown by a lighter fill with a 1px inner outline, never by lifting the item.

### Shadow Vocabulary
- **Toast** (`box-shadow: 0 6px 24px rgba(0, 0, 0, .5)`): the only shadow in the system. It is used only for the transient toast that floats above the stack.
- **Modal scrim** (`::backdrop` `rgba(0, 0, 0, .6)`): shown behind the confirm dialog for bulk and destructive actions.

### Named Rules
**The Hairline Rule.** Structure is drawn with 1px lines in hairline or hairline-strong. Anything that floats above the page (at the moment, only the toast) gets a single ambient shadow. Nothing else gets one.

## Shapes

Every control, key, tile, field, card and instruction box uses a hard 3px corner. The confirm dialog uses 4px. Only the toggle switch (12px track) and the horn's status dot are round. The only other curves are the circle glyphs for low and info priority.

The priority glyphs are the system's signature shapes. They are drawn on a 22-unit grid with a 1.6 stroke:
- **Critical (1):** diamond.
- **High (2):** triangle.
- **Medium (3):** square.
- **Low (4) and Info (5):** circle.
- **Status (6):** hexagon.

The priority number is set inside each shape. A glyph is drawn in one of four state marks:
- **Filled:** active.
- **Hollow:** cleared but not yet acknowledged.
- **Struck:** shelved, with a diagonal line through it.
- **Dashed:** disabled, with a 2.5/2.5 dash.

The same marks carry over to text and tiles. A shelved message gets a line-through, and a disabled tile gets a dashed border at 0.6 opacity.

### Named Rules
**The Redundant Priority Rule.** Priority is always shown by shape, number and colour together. Never render a priority glyph without its numeral, and never use a coloured dot or bar alone.

**The State Is A Mark Rule.** Lifecycle state changes how the glyph is drawn: filled, hollow, struck or dashed. It never changes the hue. Info and status glyphs are always drawn hollow.

## Components

### Master Pushbuttons
Square backlit keys, each with a caption bar.
- **Shape:** at least 112 by 64px, 3px corners, a hairline-strong border. The unlit face is key-face with Text Faint lettering in Key Face type. The caption bar is `#070b0e`, set in 10px caption type, with a hairline above it.
- **Lit:** WARN fills its face with warning-red and CAUT with caution-amber, each with dark hue-tinted ink. The caption shows the live count (CRITICAL 1, HIGH/MED 2).
- **Flash:** while any matching alarm is unacknowledged, the face alternates between lit and an unlit outline in the same hue, with a 1s `steps(1, end)` cycle. Pressing the key acknowledges and steadies it.
- **ACK ALL:** the same key form, using Text when enabled. Its caption shows the unack count, and it is disabled when that count is 0.
- **Horn housing:** a keyed box. The top line shows the horn state with a 9px dot (amber and blinking while sounding), and a SILENCE button fills the rest.

### Buttons
- **Shape:** at least 44px tall, 3px corners, 1px hairline-strong border, 700 weight at 12.5px with +0.12em tracking, uppercase, 14px side padding.
- **Primary (ACK):** the same fill as other buttons, with a Text-coloured border. It is marked out by its outline, not by colour.
- **Big:** 54px tall at 14px. Used for the phone's next-decision ACK and ACK ALL.
- **Danger:** destructive-text with a destructive-line border.
- **Hover:** a slightly lighter fill (`#111b22`). **Focus:** a 2px focus outline offset by 2px. **Disabled:** 0.45 opacity.
- **Link:** a focus-coloured, underlined text button, offset by 3px. Used for inline "Edit rule" links.

### Chips and Segmented Controls
- **Chip:** transparent, with a hairline-strong border, Text Dim at 12px and +0.08em. Minimum 36px tall, or 44px on touch.
- **Selected or expanded chip:** Text colour with a Text Dim border. A **strong** chip uses a Text border.
- **Segmented:** a single bordered strip. The selected segment is filled with hairline-strong.
- **Shelve presets:** B612 Mono 12px outline buttons (1h, 4h, 8h, 1d, 3d, 7d), each at least 40px wide (44px on touch).

### Inputs / Fields
- **Style:** a well fill, a hairline-strong border, 3px corners, 7px/10px padding at 13px, at least 36px tall (44px on touch). Placeholder text is Text Faint.
- **Focus:** the global 2px focus outline.
- **Error:** a destructive-text line below the form. Checkboxes use `accent-color` Text at 18px.
- **Switch:** a 42 by 24px track with a 16px knob that slides 18px in 150ms. It uses Text when on and Text Faint when off.

### Navigation (Page Selector)
- The page selector sits on the panel band as a row of text tabs: 12px, +0.12em, uppercase, Text Dim.
- Each tab carries an 11px count in Text Faint. The UNACK count turns caution-amber when there are unacknowledged alarms.
- **Selected:** Text colour with a 2px Text underline.
- **Narrow:** the tabs wrap onto two lines instead of scrolling.

### Alert Stack Row
- The stack is a button grid ranked by priority and time. Rows are separated by hairlines, and hovering tints a row `#0c1318`.
- **Selected:** a `#111c24` fill with a 1px inner outline in hairline-strong.
- **Active alarms:** the message text takes the priority colour. Cleared, pending and dim rows drop to Text Dim.
- **Unacknowledged rows:** the glyph flashes by swapping its fill with its numeral colour. If flashing is turned off or the user prefers reduced motion, the glyph gets a steady 2px outline in its priority colour instead.
- **State column:** tracked caption text (UNACK, ACK, CLR · UNACK), in Text when unacknowledged.

### Status Page
- The status page sits on panel-raised. It opens with a 34px glyph and a Title heading, followed by a Display readout with the limit aligned right.
- Next comes an 88px step-line trend over the last six hours. The line is drawn in Text, with a dashed limit line in the priority colour, an 8% priority-coloured area fill, and a dot marking the latest value.
- Below the trend are a two-column fact list, a bordered instructions box, and an event timeline.
- An action block is pinned to the bottom: ACK and DISABLE side by side, with the shelve presets underneath.

### Annunciator Board (Rules)
- The rules page is a grid of tiles, each at least 150px wide, 76px tall and 6px apart. Each tile shows a tag, the rule name in uppercase and a mono condition.
- A tile lights with its priority fill and dark ink when its alarm is active, and flashes while that alarm is unacknowledged.
- A cleared-but-unacknowledged tile shows only a priority-coloured border. Shelved tiles strike through the name, and disabled tiles use a dashed border.
- The tile being edited gets a 2px Text outline, and its editor opens beside the board as a status page.

### Named Rules
**The One Flash Rule.** Flashing means "unacknowledged" and nothing else. It uses one timing (`--iap-flash: 1s`, `steps(1, end)`, which is 1 Hz and well below 3 Hz). Every flashing element must have a steady fallback that applies under `prefers-reduced-motion` and under the panel's own flash-off setting.

## Do's and Don'ts

### Do:
- **Do** add new colours as `--iap-*` custom properties in the `:host` block, and use them by name.
- **Do** render every priority with `glyph(priority, mode)`, so shape, numeral and colour always travel together.
- **Do** map every new visual state to an ISA-18.2 lifecycle state, using the filled, hollow, struck and dashed marks.
- **Do** keep all touch targets at least 44px under `pointer: coarse`, on screens 1366px wide or less, and in `narrow` mode.
- **Do** use hairlines, the three near-black tones, and 3px corners for any new container.
- **Do** give tracked uppercase captions only to labels that name the value or control next to them.
- **Do** check every new layout at desktop, wide tablet (app-shell scroll with pinned actions), 860px, and `narrow`.

### Don't:
- **Don't** put priority colours on chrome, headings, tabs, empty states or decoration. The screen must be dark when nothing is abnormal.
- **Don't** show priority by colour alone. Don't use colour to show lifecycle state either.
- **Don't** flash anything that is not unacknowledged, and don't add a flash without a steady fallback.
- **Don't** add drop shadows, gradients or glows to panels, rows, keys or tiles. The toast is the only floating layer.
- **Don't** load fonts or assets from a CDN. Everything ships in `frontend/dist/`.
- **Don't** replace B612 with a system display face, or render icons as font glyphs or emoji. Icons are inline SVG.
- **Don't** colour a destructive control with warning-red. Use the destructive-text and destructive-line pair.
