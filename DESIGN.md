---
name: "What to do?"
description: "A shared workspace for considered group decisions."
colors:
  ink: "#0f1d3a"
  ink-2: "#2b3a57"
  muted: "#536179"
  faint: "#7887a0"
  ground: "#f3f7fc"
  surface: "#fff"
  surface-2: "#f8fbff"
  line: "#dde5f0"
  line-strong: "#c3d0e2"
  control-line: "#7f90ab"
  blue: "#1557c0"
  blue-hover: "#0f469e"
  blue-press: "#0b377d"
  blue-ink: "#0c3a85"
  sky-50: "#eef4fd"
  sky-100: "#e2ecfb"
  sky-200: "#c8dbf6"
  sky-300: "#94b8ec"
  night: "#0a2150"
  danger: "#b3172a"
  danger-soft: "#fdecee"
  warn: "#8a5300"
  warn-soft: "#fff4de"
  ok: "#146140"
  ok-soft: "#e4f3eb"
typography:
  display:
    fontFamily: "Source Sans 3, Helvetica Neue, Arial, sans-serif"
    fontSize: "clamp(2.75rem, 1.6rem + 3.6vw, 5.25rem)"
    fontWeight: 300
    lineHeight: 1.02
    letterSpacing: "-.035em"
  headline:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "clamp(2rem, 1.4rem + 1.6vw, 2.75rem)"
    fontWeight: 300
    lineHeight: 1.1
    letterSpacing: "-.02em"
  section:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.25
  title:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Source Sans 3, sans-serif"
    fontSize: ".9375rem"
    fontWeight: 600
rounded:
  control: "10px"
  button: "999px"
  card: "16px"
  panel: "20px"
  band: "28px"
spacing:
  gutter: "clamp(20px, 3.2vw, 56px)"
  steps: "4 8 12 16 20 24 28 32 40 48 56"
motion:
  ease-out: "cubic-bezier(.16, 1, .3, 1)"
  ease-io: "cubic-bezier(.65, 0, .35, 1)"
  fast: "120ms"
  base: "240ms"
  slow: "480ms"
components:
  button-primary: { backgroundColor: "{colors.blue}", textColor: "#fff", rounded: "{rounded.button}", padding: "10px 20px" }
  button-secondary: { backgroundColor: "{colors.surface}", textColor: "{colors.ink}", border: "{colors.line-strong}", rounded: "{rounded.button}" }
  button-quiet: { backgroundColor: "transparent", textColor: "{colors.blue-ink}", rounded: "{rounded.button}" }
  input: { backgroundColor: "{colors.surface}", border: "{colors.control-line}", rounded: "{rounded.control}", minHeight: "48px" }
  panel: { backgroundColor: "{colors.surface}", border: "{colors.line}", rounded: "{rounded.panel}" }
  board-head: { backgroundColor: "{colors.night}", textColor: "#fff" }
  board-lead-row: { backgroundColor: "{colors.blue}", textColor: "#fff" }
  nav-current: { backgroundColor: "{colors.sky-100}", textColor: "{colors.blue-ink}" }
---

# Design System: What to do?

## Overview

**North star: the station board.** The visual language borrows from Swiss rail information design (SBB's digital system): white working surfaces on a light-blue ground, a deep night-blue for information "boards", one confident blue for action, humanist sans type with large light-weight headlines, rounded controls and short, decelerating motion. A decision is treated like a journey with stops: options are listed, the group answers, the ranking arrives row by row, and the chosen option is confirmed.

The palette is deliberately restrained to blues and white. Colour does jobs: blue for action and the current position, night-blue for board headers and the closing landing band, amber/green/red only for state (reviewing, confirmed, ruled out). There are no gradients, glass, decorative borders on one side, highlighter fills or tag pills.

Source of truth: `frontend/src/responsive.css` (tokens, controls, transitions) and the Vue components. `PRODUCT.md` holds product truth.

## Signature move: the board

`LandingBoard.vue` (landing hero) and the result board in `RoundWorkspace.vue` share one grammar: a night-blue header with the plan and question, a light column-header row (Rank · Option · fit · Status/Lowest member), and rows with a light-weight rank numeral, option name plus muted meta, a thin fit bar with a tabular percentage, and a status column using a square signal mark. The leading row fills blue with white text. Rows enter with a clipped roll-in staggered 90–110ms; bars fill over ~1.1s; reordering uses FLIP (`*-move` transitions). On the landing the board loops through two example scenarios and pauses off-screen or in hidden tabs; reduced motion shows the final state.

## Colors

- **Ground** `#f3f7fc`: every app page and the landing. **Surface** white for panels, cards and tables; **surface-2** for table heads and secondary panes.
- **Blue** `#1557c0` (6.3:1 on white): primary buttons, current nav/step, focus rings, meters, the leading board row. Hover `#0f469e`, press `#0b377d`. **Blue-ink** for blue text on light fills.
- **Sky 50–300**: selected choice fills, nav current background, empty bar tracks, quiet callouts, and the landing hero field.
- **Night** `#0a2150`: board headers, the landing closing band, the invitation side panel, avatar.
- **State**: warn `#8a5300` (reviewing), ok `#146140` (confirmed/ranked), danger `#b3172a` (errors, ruled out). Soft fills only for callouts and alerts.
- Text is never neutral grey: muted `#536179` and faint `#7887a0` are blue-tinted.

## Typography

Source Sans 3 (variable, 200–900, self-hosted at `public/fonts/source-sans-3.woff2`, OFL), chosen as the closest open match to SBB's humanist type. Large headings use weight 300 with negative tracking; section and card titles use 600. Numbers in tables, meters and dates use tabular figures. Labels are sentence case and semibold. No eyebrows or kickers above headings; context lines go below the heading.

## Layout

- **App shell** (`AppManager.vue`): a 268px white sidebar (brand, My forms / New form / Join with a link, session menu and sign out at the foot) that collapses to a 76px icon rail with tooltips; the state is remembered per browser. At ≤860px it becomes a top bar (brand, Session details, sign out) plus a fixed bottom tab bar.
- **Full width**: content spans the main column with `--gutter` side padding (20–56px); reading measures are capped per element rather than by a page container.
- **Creator**: horizontal five-stop stepper across the width; form card plus a sticky "Plan so far" summary column (stacks under 1180px); a sticky action bar keeps Back/Next in reach.
- **Round workspace**: header, three-stop progress line, then main column plus a sticky organiser column (controls, invitation, waiting list, revise). The aside moves above the content under 1180px.
- **Dashboard**: underline status tabs with counts, search, full-width table (cards on phones).
- **Landing** (`Login.vue`): hero split 5/6 with the quick-start card (Start a plan / Join with a link tabs, resume disclosure) beside the board on a sky field; a route section with four stops drawn on scroll; three principles under a night rule; a night-blue closing band.

## Shapes & depth

Buttons are fully rounded (SBB control shape). Inputs 10px, cards 16px, panels and boards 20px, the closing band 28px. Depth comes from soft offset shadows (`--shadow-sm/md/lg`), never coloured halos.

## Motion

Exponential ease-out (`cubic-bezier(.16,1,.3,1)`), 120ms feedback, 240ms state, 300–480ms layout, up to ~1.1s for authored moments (headline line reveal, board fill, route draw). Exits are faster than entrances. Step and page changes slide in the direction of travel. Scroll reveals run once via IntersectionObserver and content stays visible without script. `prefers-reduced-motion` collapses durations to ~1ms.

## Do

- Show the current state and next action first (confirmed selection sits above options and results).
- Use the square signal mark plus text for status, not filled badges.
- Keep a single blue primary per view region.

## Don't

- Gradients, confetti, medals, glass, side-stripe borders, pill tags for metadata, eyebrows above headings.
- Grey neutrals; tint from the blue family instead.
