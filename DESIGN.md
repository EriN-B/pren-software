---
name: PREN Dog Simulator
description: The competition run as a timed race, with the dog's world and its camera side by side.
colors:
  ground: "#f2f2f0"
  panel: "#ffffff"
  line: "#dadad5"
  line-soft: "#ebebe7"
  ink: "#111111"
  ink-2: "#3a3a36"
  muted: "#64645f"
  race-red: "#e30613"
  race-red-ink: "#c00510"
  red-tint: "#fdecec"
  timing-green: "#1e9e4a"
  timing-green-ink: "#167a38"
  amber-ink: "#8a5300"
  amber-tint: "#fff5e0"
  uart-blue: "#2a55b0"
  stage: "#1b1b19"
typography:
  display:
    fontFamily: "Barlow Semi Condensed, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "46px"
    fontWeight: 300
    lineHeight: 1
    letterSpacing: "-0.01em"
    fontFeature: "tnum"
  headline:
    fontFamily: "Barlow Semi Condensed, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "19px"
    fontWeight: 400
    lineHeight: 1.2
    fontFeature: "tnum"
  title:
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    letterSpacing: "-0.005em"
  label:
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "12px"
    fontWeight: 600
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
  caption:
    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "11px"
    fontWeight: 400
  mono:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: "20px"
    fontFeature: "tnum"
rounded:
  bar: "2px"
  sm: "4px"
  md: "6px"
spacing:
  xxs: "4px"
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "6px 10px"
  button-hover:
    backgroundColor: "{colors.ground}"
  button-active:
    backgroundColor: "{colors.line-soft}"
  button-quiet:
    textColor: "{colors.muted}"
    rounded: "{rounded.md}"
    padding: "6px 10px"
  button-estop:
    backgroundColor: "{colors.race-red}"
    textColor: "{colors.panel}"
    rounded: "{rounded.md}"
    padding: "10px 18px"
  button-estop-engaged:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.race-red-ink}"
    rounded: "{rounded.md}"
    padding: "10px 18px"
  segmented-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.panel}"
  split:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.muted}"
    typography: "{typography.headline}"
    padding: "6px 12px"
  split-live:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.panel}"
  split-done:
    textColor: "{colors.timing-green-ink}"
  split-live-over:
    backgroundColor: "{colors.race-red}"
    textColor: "{colors.panel}"
  view-panel:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.md}"
  view-head:
    height: "36px"
    padding: "0 12px"
    typography: "{typography.label}"
  input-search:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "4px 8px"
  log-row:
    typography: "{typography.mono}"
    padding: "1px 16px"
  log-row-warning:
    backgroundColor: "{colors.amber-tint}"
    textColor: "{colors.amber-ink}"
  log-row-error:
    backgroundColor: "{colors.red-tint}"
    textColor: "{colors.race-red-ink}"
---

# Design System: PREN Dog Simulator

## Overview

**Creative North Star: "The Timing Board"**

The simulator reads like race timing graphics laid over an engineering tool. One large run clock and four phase splits (Commands, Search, Found, Return) sit in the header and say where the run stands; everything else is quiet white panels on a warm light grey, separated by hairlines, waiting to be read. Colour is a timing signal, not decoration: black marks the live phase, green marks what is done or what the core detected, race red marks Not-Aus, overruns and errors.

Density is developer-grade (13 px body, 12 px monospace logs, 36 px panel heads) but the clock and splits are large and light enough to read across a room during a demo. The weight stays light: a 300-weight condensed clock, 400/600 system sans, 1 px hairlines, no heavy chrome. Solid fills are reserved for state: the live split, the active segment, the Not-Aus button, and the whole header when Not-Aus is engaged.

The world is light-themed by commitment. The only dark surfaces are the camera stages, where images need a neutral black surround.

**Key Characteristics:**
- A run clock and phase splits as the primary information, not a grid of titled dashboard panels.
- White panels, warm grey ground, 1 px hairlines, one 6 px radius.
- Three signal colours with fixed meanings: ink for live, green for done and hits, red for stop, overruns and errors.
- Condensed light timing numerals; tabular figures on every number that changes.
- Truth versus perception kept visibly distinct: dashed ink for real positions, solid green for core detections.

## Colors

A near-neutral warm-grey palette carrying three signal colours whose meanings never change.

### Primary
- **Race Red** (race-red): the Not-Aus button, the live split when it runs over budget, the over-budget bar fill, motor load at maximum, and the whole header when Not-Aus is engaged. Fills and strokes only.
- **Race Red Text** (race-red-ink): red as text on white (5.6:1): over-budget clock and split figures, overrun deltas, error log levels, the engaged Not-Aus label.

### Secondary
- **Timing Green** (timing-green): the connected state dot and core detection boxes and chips in the dog camera. Fills and strokes only.
- **Timing Green Text** (timing-green-ink): green as text on white (5.3:1): done split figures, time left on the search split.

### Tertiary
- **Warning Amber** (amber-ink on amber-tint): warning log rows only.
- **UART Blue** (uart-blue): the UART source column in the log, so Pico traffic separates from core and sim host lines.

### Neutral
- **Warm Ground** (ground): the app background behind panels; also row hover, code and kbd fills, and log run marks.
- **Panel White** (panel): every panel, the header, the dock, buttons and inputs.
- **Hairline** (line): panel, button, input and split borders. **Soft Hairline** (line-soft): dividers inside a panel, track fills for bars.
- **Ink** (ink): text, the live split, the active segment, focus rings, the budget bar fill while running. **Ink 2** (ink-2): secondary values and motor bars.
- **Label Grey** (muted): labels, meta text, idle split figures, timestamps.
- **Stage** (stage): the near-black surround of the dog camera and the webcam.

### Named Rules
**The Fixed Signal Rule.** Ink means live, green means done or detected, red means stop, over budget or error. A colour never takes a second meaning on another surface.

**The Ink Variant Rule.** Red and green as text on white always use their text-safe variants (race-red-ink, timing-green-ink); the bright values are for fills, strokes and white-on-colour labels.

## Typography

**Display Font:** Barlow Semi Condensed 300/400, self-hosted (npm @fontsource/barlow-semi-condensed 5.2.5), falling back to the system sans
**Body Font:** system-ui (with -apple-system, Segoe UI, sans-serif)
**Label/Mono Font:** ui-monospace (with SF Mono, Menlo, Consolas, monospace)

**Character:** A condensed light grotesque gives the clock and splits the look of a timing board; the system sans keeps the tool chrome native and quiet; monospace carries the logs and live readouts where columns must align.

### Hierarchy
- **Display** (300, 46 px, 1): the run clock only. 34 px on phones. Idle grey (#85857f, large text) without a core, ink while running, race-red-ink over budget.
- **Headline** (400, 19 px, 1.2): split times. 16 px on phones.
- **Title** (600, 16 px): the product name in the header.
- **Label** (600, 12 px): panel and rail block headings; a 400-weight grey aside may follow in the same line.
- **Body** (400, 13 px, 1.4): controls, states, hints, facts.
- **Caption** (400, 11 px): split names, clock budget line, torque readouts.
- **Mono** (400, 12 px, 20 px line): log lines, sensor and motor values, sim time, code and kbd.

### Named Rules
**The Tabular Rule.** Every number that updates (clock, splits, sim time, facts, motor values, log timestamps) uses tabular figures so it never jitters.

**The Light Clock Rule.** Timing numerals stay at 300/400 weight in the condensed face; emphasis comes from colour and the live fill, never from bolding the figures.

## Layout

A full-height three-row grid: the header (min 72 px), the workspace, and a resizable log dock (260 px default, dragged by a grip on its top edge). The header is a three-column grid: identity and connection states left, the clock and splits centred, sim time and Not-Aus right. The workspace puts the 3D scene and the dog camera side by side at equal width, then a 280 px control rail; gaps and padding are 12 px. Everything aligns to an 8 px unit, with 4, 6 and 12 px used for tight internal spacing.

At ≤1100 px the clock and splits drop to a second header row, the rail narrows to 210 px but stays beside the views, workspace gaps tighten to 8 px, the dock height becomes clamp(150px, 30vh, 260px), and long meta text and legend labels shorten. At ≤640 px the workspace stacks into one scrolling column with the dog camera first (views 260 px tall), the dock is 180 px, its toolbar wraps, and log rows put the message on its own line.

## Elevation & Depth

Flat. Depth comes from tonal layering (white panels on the warm ground) and 1 px hairlines, not shadows.

### Shadow Vocabulary
- **Floating hint** (`box-shadow: 0 4px 16px rgb(0 0 0 / 0.18)`): only the placing hint that floats over the 3D canvas.

### Named Rules
**The Hairline Rule.** Panels separate by a 1 px hairline and the ground showing between them; a shadow appears only on something floating over a canvas.

## Shapes

One gentle radius (6 px) for panels, buttons, inputs, the split strip and segmented controls; 4 px for small insets (code, kbd, webcam frame); 2 px for thin bars; circles only for 7 px state dots. Grouped controls (splits, segmented buttons) share one outer border and radius, divided internally by hairlines with square inner corners.

## Components

### Buttons
- **Shape:** gently rounded (6 px), 1 px hairline border.
- **Default:** white with ink text, 6 px 10 px padding; hover to warm ground with a darker border (#c4c4be), active to soft hairline. 120 ms ease-out on background and border.
- **Quiet:** transparent border, grey text, ink on hover (log Clear).
- **Not-Aus:** race red fill, white 600 text, 10 px 18px padding, always at the header's right edge. Engaged: white button with race-red-ink text on a race-red header.

### Segmented control
- **Style:** one bordered strip, equal segments divided by hairlines; the active segment is solid ink with white text, counts in a grey aside.
- **State:** no colour transition, so the active state never shows half-painted. Compact variant (4 px 10 px) for log source filters.

### Run clock and splits (signature)
- **Clock:** display numerals over a 3 px budget bar (ink fill, red when over) and a caption with the budget.
- **Splits:** a four-cell strip. Idle cells show a grey dash; the live cell is solid ink with white figures; done cells turn their figures green; a live cell over budget fills race red. A closing split flashes pale green (600 ms, cubic-bezier(0.16, 1, 0.3, 1)). The Search cell carries a delta: green time left, red 600 overrun.

### View panels
- **Corner Style:** 6 px. **Background:** white. **Border:** 1 px hairline. **Shadow:** none.
- **Head:** 36 px row with a 12 px 600 label, grey meta text, and a right-aligned toggle or legend, divided by a soft hairline.
- **Camera stage:** the dog camera sits centred on the near-black stage at its native 640 × 480.

### Detection overlay
- Core detections: 2 px solid timing-green box with a solid green chip, white 600 11 px label and confidence.
- Real positions: 1 px dashed white box with a dark ink chip (82% ink). Chips stack downward so labels never overlap. A legend in the panel head names both.

### Rail blocks
- Sections inside one white rail, 12 px padding, divided by soft hairlines; facts as a two-column list with right-aligned monospace values; motor load as 4 px bars (ink-2, amber when high, red at max).

### Inputs / Fields
- **Style:** white, 1 px hairline, 6 px radius, 4 px 8 px padding, inherited 13 px type.
- **Focus:** 2 px ink outline offset 2 px, the same ring as every focusable element.

### Log dock
- Monospace grid rows (time, run time, source, level, message) at a 20 px line. Warnings tint amber, errors tint red with red level text. Run phase marks are sans 600 rows on the warm ground between hairlines. Core source in ink 600, sim host grey, UART blue.

## Do's and Don'ts

### Do:
- **Do** keep panels white on the warm ground with 1 px hairlines and the single 6 px radius.
- **Do** use tabular figures for every changing number, and the condensed timing face only for the clock and splits.
- **Do** use race-red-ink and timing-green-ink whenever red or green is text on white.
- **Do** draw what the dog really perceived (core detections) in solid green and world truth in dashed ink, and label both.
- **Do** keep Not-Aus race red at the header's right edge, and turn the whole header red while it is engaged.
- **Do** show focus as a 2 px ink outline offset 2 px.

### Don't:
- **Don't** give ink, green or red a second meaning; a green that is not "done" or "detected" breaks the board.
- **Don't** bold timing numerals or set them in the system sans or a monospace; the clock face is light and condensed.
- **Don't** add drop shadows to panels; only a hint floating over a canvas gets one.
- **Don't** switch to a dark theme; dark is reserved for camera stages.
