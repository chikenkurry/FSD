---
name: "What to do?"
description: "A shared workspace for considered group decisions."
colors:
  ink: "#243440"
  muted: "#59676e"
  navy: "#182e3b"
  surface: "#fff"
  ground: "#f4f5f2"
  line: "#dce2de"
  control-line: "#809387"
  accent: "#24614e"
  accent-hover: "#194b3b"
  accent-soft: "#e8f1eb"
  danger: "#9b3030"
  danger-soft: "#fff0ed"
  badge-neutral: "#edf0ed"
  badge-neutral-ink: "#435349"
  reviewing-soft: "#fff1d9"
  reviewing-ink: "#805114"
  confirmed-soft: "#e5edf6"
  confirmed-ink: "#294e74"
  nav-current: "#304b59"
  focus: "#c17828"
typography:
  display:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-.03em"
  headline:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "2rem"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-.03em"
  section:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-.02em"
  title:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 650
    lineHeight: 1.4
  body:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Public Sans, sans-serif"
    fontSize: ".875rem"
    fontWeight: 600
    lineHeight: 1.6
  badge:
    fontFamily: "Public Sans, sans-serif"
    fontSize: ".75rem"
    fontWeight: 650
    lineHeight: 1.6
rounded:
  badge: "5px"
  input: "6px"
  button: "7px"
  panel: "12px"
  circle: "50%"
spacing:
  4: "4px"
  8: "8px"
  12: "12px"
  16: "16px"
  20: "20px"
  24: "24px"
  28: "28px"
  32: "32px"
  48: "48px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.button}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "10px 16px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "10px 16px"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.danger}"
    rounded: "{rounded.button}"
    padding: "10px 16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.input}"
    padding: "10px 12px"
  badge-collecting:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent}"
    rounded: "{rounded.badge}"
    padding: "4px 10px"
  badge-reviewing:
    backgroundColor: "{colors.reviewing-soft}"
    textColor: "{colors.reviewing-ink}"
    rounded: "{rounded.badge}"
    padding: "4px 10px"
  badge-confirmed:
    backgroundColor: "{colors.confirmed-soft}"
    textColor: "{colors.confirmed-ink}"
    rounded: "{rounded.badge}"
    padding: "4px 10px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "28px"
  navigation-current:
    backgroundColor: "{colors.nav-current}"
    textColor: "{colors.surface}"
    rounded: "{rounded.button}"
    padding: "10px 16px"
---

# Design System: What to do?

## Overview

**Creative North Star: "The Shared Workspace"**

A calm shared workspace for decisions: clear options, visible progress and considered actions. The navy application shell and green action states give professional organisations a credible working interface; warm near-white surfaces and plain language keep the same interface approachable for friends and informal groups. This is an Operate application, with the connected task taking priority over decorative storytelling.

The implemented system uses one visual language across audiences. Separate business and casual themes would introduce a distinction the shared decision workflow does not need. Shared CSS tokens and native form controls keep existing Vue flows consistent and responsive without another UI framework or a parallel component API. These are documented implementation choices, not a claim that the user approved individual token values.

The North Star is a descriptive label for the built system, not a separately approved brand metaphor. Source of truth: `frontend/src/responsive.css` and the Vue views and components. `PRODUCT.md` establishes the professional and informal audience.

**Key Characteristics:**
- One navy application header with a restrained geometric brand mark.
- White bordered working surfaces on a warm near-white ground.
- Green actions and current steps; text-labelled lifecycle states.
- Public Sans throughout, with compact supporting text and readable task headings.
- Responsive tables, form steps and action rows preserve the same workflows.

## Colors

A grounded navy and green palette, with warm neutral surfaces and restrained semantic status colours. The frontmatter records the implemented values; CSS custom properties retain their existing names. Sidecar tonal ramps are synthesized OKLCH preview strips for the design panel, not additional application tokens.

### Primary

- **Considered green** (`accent`): primary buttons, links, current steps and collecting states. Its deeper hover and pale companion support interaction and selected surfaces.

### Neutral

- **Working navy** (`navy`): session shell; `nav-current` distinguishes the current navigation destination.
- **Ink and muted slate** (`ink`, `muted`): primary content and supporting explanation.
- **Warm ground and white surface** (`ground`, `surface`): page canvas and working regions.
- **Quiet line and control line** (`line`, `control-line`): structural divisions and stronger input boundaries.
- **Neutral badge pair**: low-emphasis draft or other unaccented states.

Reviewing uses the amber semantic pair; confirmed uses the blue pair. These are state indicators, not competing action accents. The danger pair identifies errors and destructive text. Amber focus is a separate keyboard interaction cue. Status badges always carry words and a small dot.

**The The Shared Workspace Rule.** Use the same palette and component language for professional and informal groups; let the decision content establish the context.

## Typography

**Display Font:** Public Sans, sans-serif.
**Body Font:** Public Sans, sans-serif.

The variable font is self-hosted at `/fonts/public-sans.ttf`, with normal weights (100–900) and swap loading. There is no separate display or monospace family. Its plain, open forms support both administration and informal planning.

### Hierarchy

- **Display:** the login introduction uses the display role; it reduces to 2.25rem at 1000px and 2rem at 700px.
- **Headline:** page headings use the headline role, reducing to 1.625rem at 700px.
- **Section / title:** the section and title roles distinguish panels and subordinate option or review headings.
- **Body:** the body role is the global baseline; paragraphs cap at 72ch. Supporting panel text commonly uses .875rem.
- **Label / badge:** labels are sentence case and semibold; badges are compact and slightly heavier. Help text uses .8125rem, and metadata commonly uses .75rem.

**The The One Family Rule.** Use Public Sans for headings, controls and body copy; establish hierarchy through size, weight and spacing.

## Layout

Working pages use a centred container (maximum 1200px) with desktop side padding (32px), top spacing (48px; dashboard 56px) and bottom spacing (80px). At 700px the workspace, dashboard and creator use 20px side padding and 32px / 48px vertical padding. The minimum document width is 320px. Reused spacing steps are extracted in the frontmatter; they describe a practical rhythm rather than a strict mathematical scale.

The authenticated session header is the only application shell header; page headings sit inside content. At 900px shell spacing tightens and the session name hides. At 600px the brand takes a full row and session controls remain reachable below it. The session popover is anchored over content with a viewport-constrained width.

The creator places a 200px step column beside the form with a 48px gap. At 900px this becomes 165px / 24px; at 700px the main layout becomes one column. Above the form, step navigation uses five equal columns from 381–700px and three columns at 380px or narrower, allowing labels to wrap by words. All five setup steps remain visible without horizontal scrolling. Two-column input, fact and summary grids stack on phones. Wizard actions stack with the forward action visually first.

Dashboard tables retain real headers on desktop. At 700px each row becomes a bordered two-column card with visible data labels, a full-width plan name and its open action. Search and status filters stack. Candidate recommendations use an auto-fitting grid with a 320px minimum capped by available width. Lifecycle progress stays visible and compacts into three small labelled columns on phones.

Panels use 28px padding, reducing to 20px on phones. Creator and option-editor surfaces use 32px desktop padding. Action rows wrap and become full-width buttons at 700px. Inputs remain within their containers; long user text wraps.

## Elevation & Depth

The system is mostly flat: white surfaces, pale state fills, one-pixel borders and whitespace establish hierarchy. Shadows are reserved for surfaces that float above the page: the session popover, the entry and invitation cards, and the sticky "keep" bar. The popover uses positioning and stacking (z-index 10), while the focused skip link sits above it (z-index 20).

**The Flat Surface Rule.** Separate working regions with background tone, thin borders and spacing; only floating surfaces carry a soft shadow.

## Shapes

Gently curved rectangles distinguish scale: panel corners are broader than control corners, and small status badges are squarer. The frontmatter records the actual radius vocabulary. Numbered step markers and state dots are circular. Controls have thin visible borders; selected or recommended surfaces pair pale green with an appropriate outline or filled step marker. The brand mark combines three blocks and a check; utility icons are inline stroke SVGs, normally 19px, with smaller 15–16px supporting variants.

## Components

### Buttons

Clear, compact, labelled actions. Primary actions are green with white text; hover and active use the deeper green. Secondary buttons are white with a stronger control border; quiet buttons have transparent backgrounds and borders. Danger is a text-colour treatment that may combine with quiet buttons. Controls have a minimum height (44px), semibold text and an 8px icon gap. Secondary hover uses a pale neutral fill; disabled states use grey-green fill, border and text. Colour and border transitions use the `--fast` token (140ms); buttons press down 1px and trailing arrows nudge on hover. Reduced-motion preferences remove all transitions and animations.

### Inputs / Fields

Native inputs, selects, dates, checkboxes, radio buttons and textareas carry the shared visual treatment. Text controls have a minimum height (46px), visible control border, white background and green caret. Textareas start at 112px and resize vertically. Checkboxes and radios use the green native accent. Labels stay attached to fields; help text remains visually subordinate. Error and alert messages use the danger pair with inline padding; native required and date constraints remain in use. Every keyboard-focusable element receives a visible amber outline (3px with a 3px offset).

### Chips

Status badges are text labels with a small same-colour dot, compact padding and restrained corner rounding. Collecting is green, reviewing amber and confirmed blue. These are status displays, not decorative tags or substitute navigation.

### Cards / Containers

White, thin-bordered panels hold coherent work regions. The dashboard empty and failure states use the same language as forms. Nested facts and private review use pale tonal fills rather than additional elevation. Recommended candidates receive pale green with a stronger green border; numerical comparison values use tabular figures.

### Navigation

One navy session bar contains the brand, My forms, session details and sign out. Current navigation uses a lighter navy surface and white text; hover uses the same treatment. The creator step navigation (Basics, Options, Overview, Questions, Review) is distinct from lifecycle progress: it allows movement through five setup steps, while the round progress communicates collection, review and confirmation. Both identify the current step in text and with `aria-current`.

### Option overview cards

Each option is presented as a card: up to three photos (with author credits), the name and detected type, a meta line (rating, price level, place type, price note or dates), the address or area, a summary of at most two sentences, up to four short highlight labels, and a collapsed "What reviewers say" disclosure when Places provides one. Live Places details and the stored web/AI brief are combined into one card. Provenance is always visible: "View on Google Maps", "From the web" with source links, or "General description by AI". The same card serves the organiser's Overview step, the member overview and the organiser workspace (compact). AI fit values in the creator carry an amber "AI estimate" label.

### Guided member response

Invited members move through one page at a time: name, overview (main question plus option cards), one question per page with a progress meter, extras, review and a drawn-check confirmation. Pages slide in the direction of travel. Choice questions use large selectable rows rather than dropdowns.

### Private review and lifecycle progress

The round header shows the named state and organiser/member context before the three-stage lifecycle. Private response copy explains the privacy boundary. On the member review page, the interpretation is checked automatically and requirement confirmation appears above Submit response, which stays disabled until requirements are confirmed. Editing answers clears the previous review. The private preview translates `EXECUTION_ADAPTER_REQUIRED` into a plain-language explanation: it interprets answers, while the organiser calculates option rankings after collection closes. The original issue code and any original message remain available in a collapsed Technical details disclosure. The visual order supports the actual review and submission flow; it must not imply private answers are shared group results. Date and location fields collect context in the creator and do not imply generated scheduled choices.

## Do's and Don'ts

### Do:

- Do use green for primary actions and the current step, with visible text describing the action or state.
- Do retain the single session header, labelled native controls and visible keyboard focus.
- Do reflow tables into labelled mobile rows and keep all five creator steps visible on phones.
- Do keep private interpretation above submission actions and distinguish personal review from group results.
- Do explain date and location context truthfully and show validation close to the working form.
- Do label every AI or third-party result with its origin, and let the organiser change it before publishing.
- Do use the shared motion tokens (`--fast`, `--base`, `--slow`, `--ease-out`) for state changes, and only for state changes.

### Don't:

- Don't introduce separate business and casual themes for the same workflow.
- Don't make colour or an icon the sole explanation of a decision state.
- Don't replace real options or native date inputs with an illustrative calendar that implies scheduling capabilities.
- Don't substitute text glyphs for the existing inline SVG icon vocabulary.
- Don't present AI estimates as verified facts, or show members the internal comparison facts used for ranking.
- Don't add decorative or looping motion beyond loading indicators.

Verification scope: this record is extracted from the final source and direction contract. It does not assert physical-device or screen-reader validation; browser emulation is not evidence of either. No unresolved visual defect is promoted into a reusable rule.
