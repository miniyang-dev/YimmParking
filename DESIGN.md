---
name: YimmParking
description: A parking finder drawn as an orienteering control-description sheet.
colors:
  paper: "#ffffff"
  map-paper: "#f7f8f3"
  ink: "#161412"
  muted-ink: "#4b473f"
  rule-soft: "#cfccc2"
  open-land: "#f7dc55"
  thicket-hatch: "rgba(96, 140, 66, 0.55)"
  contour-brown: "rgba(176, 101, 45, 0.3)"
  water-blue: "#1c5fae"
  course-purple: "#b21a8f"
  night-paper: "#14171a"
  night-map-paper: "#181c1f"
  night-ink: "#efebe0"
  night-open-land: "#3e3611"
  night-open-ink: "#f6df6a"
  night-course-purple: "#f07ad4"
typography:
  display:
    fontFamily: "Noto Sans TC Variable, Noto Sans TC, PingFang TC, Microsoft JhengHei, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 800
    lineHeight: 1.25
  title:
    fontFamily: "Noto Sans TC Variable, Noto Sans TC, PingFang TC, Microsoft JhengHei, system-ui, sans-serif"
    fontSize: "16.5px"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "Noto Sans TC Variable, Noto Sans TC, PingFang TC, Microsoft JhengHei, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Noto Sans TC Variable, Noto Sans TC, PingFang TC, Microsoft JhengHei, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 800
    letterSpacing: "0.02em"
  numeral:
    fontFamily: "Barlow Condensed, Noto Sans TC Variable, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 800
    lineHeight: 1
rounded:
  none: "0px"
  chip: "3px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  tap: "48px"
components:
  button-primary:
    backgroundColor: "{colors.course-purple}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    height: "48px"
  button-submit:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "0 16px"
  band-preferred:
    backgroundColor: "{colors.open-land}"
    textColor: "{colors.ink}"
    padding: "7px 16px"
  band-other:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    padding: "7px 16px"
  field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    height: "52px"
---

# Design System: YimmParking

## Overview

**Creative North Star: "The Control Description Sheet"**

Every result is a numbered control on an orienteering map's description sheet. The destination is the start triangle, each parking lot is a control with a symbol, and the lot you open is the one the purple course runs to. The interface reads like something printed and ruled: white ground, black rules, tabular numerals, and inks that each have one job. It is built for a driver who has seconds, in glare or at night, and who must trust what a number means before acting on it.

It deliberately refuses the category's white card with a blue button. Nothing floats: no shadows, no rounded cards, no gradients. Structure is carried by 1px rules and 1.5px outer frames; state is carried by texture and text, never by colour alone.

**Key Characteristics:**
- Ruled grid table as the main surface; the list is the product.
- Colour is an ink with a single job, and each job has a non-colour backup (symbol, texture, or text).
- One condensed numeral face for every figure the driver must read at a glance.
- Flat by default: no shadows, no radius beyond 3px.
- Light and dark are the same sheet printed on white and on night paper.

## Colors

A white sheet with a black rule, a map-paper tint for the title block, and a small set of map inks. Purple is rare on purpose.

### Primary
- **Course Purple** (#b21a8f, dark #f07ad4): The route. Used only for the start triangle, the opened lot's number, the course line, the primary navigate action and the focus ring.

### Secondary
- **Open-Land Yellow** (#f7dc55, dark band #3e3611 with #f6df6a text): Marks the preferred-brand group bands. Nothing else is yellow.
- **Water Blue** (#1c5fae, dark #82b8f2): Links that leave the app for an outside map (food places).
- **Thicket Hatch** (rgba(96,140,66,.55)): Diagonal hatch behind a reading that is old.

### Neutral
- **Paper** (#ffffff, dark #14171a): The sheet.
- **Map Paper** (#f7f8f3, dark #181c1f): Title block and fact labels.
- **Ink** (#161412, dark #efebe0): All text, all rules, the full-lot hatch, the no-data dot screen.
- **Muted Ink** (#4b473f, dark #b9b4a7): Secondary text; at least 9:1 on paper.
- **Contour Brown** (rgba(176,101,45,.3)): Concentric contour texture, only in the title block and the course panel.

### Named Rules
**The One Course Rule.** Purple marks the route and nothing else. If two things on a screen are purple, one of them is wrong.
**The Ink-With-A-Job Rule.** Every colour answers one question (preferred, old, outside link, route). A colour that answers none is removed, not recoloured.
**The No-Colour-Alone Rule.** State must survive greyscale: symbol shape, hatch direction, dot screen, or words carry it.

## Typography

**Display Font:** Noto Sans TC Variable (with PingFang TC, Microsoft JhengHei, system-ui)
**Body Font:** the same family
**Numeral Font:** Barlow Condensed 800, Latin digits only

**Character:** A plain, confident CJK sans for words and a tall condensed numeral for figures, as on an orienteering control number or a road sign. Words are never condensed; numbers always are.

### Hierarchy
- **Display** (800, 22px, 1.25): The opened lot's name.
- **Title** (700, 16.5px, 1.3): A lot name in the list.
- **Body** (400–700, 14px, 1.5): Facts, fee text, notices.
- **Label** (800, 13px, 0.02em): Group bands, table labels, chips.
- **Numeral** (800, 30px; 44–46px for the opened lot): Spaces left, row numbers, bearing distance. Tabular figures.

### Named Rules
**The Numerals-Are-Condensed Rule.** Any figure the driver reads at a glance (spaces, row number, distance on the detail view) uses the condensed numeral face; running prose never does.

## Layout

A single column, 480px at most, centred, framed by a 1.5px rule on wide screens. The page is mobile-first: the title block (name, address field, tools, scale) sits on top, then bands and a ruled table. Rows are at least 62px tall; every control is at least 44px. The sheet is a table, so columns keep fixed widths (number 40, symbol 42, spaces 94) and the lot name takes the rest. Spacing steps are 4, 8, 12, 16, 24px.

The detail view keeps the title block but drops its tools, then stacks: back, number and name, course panel (bearing diagram and facts), spaces, navigate, food, fee, facts.

**Desktop (1024px and up): the sheet beside the control.** The frame widens to 1440px at most and locks to the window height. The title block runs across the top: two rows (name and settings, then field, tools and scale) up to 1279px, one row from 1280px. Below it, the sheet keeps a 380–440px left column and the opened lot fills the right. Each column scrolls on its own, so the sheet never leaves the screen. Until a lot is opened, the first one is shown. The shown lot's row carries the course: an 11% purple wash and a purple number, `aria-current`. There is no back button. When the detail column is at least 720px wide (a container query), it splits in two: what to do at the lot on the left (spaces, the way there, the usual day, fee, facts), what is around it on the right (YouBike, food). The second row takes the slack, so a long food list never opens gaps on the left. Preferences and this month's usage sit side by side. Below 1024px the phone layout is unchanged.

## Elevation & Depth

Flat. There are no shadows. Depth is conveyed by rules: a 1px rule between rows, a 1.5px rule around panels and under bands, and a hatch or dot texture for state. Nothing overlaps; there are no overlays or modals.

### Named Rules
**The Flat-Sheet Rule.** If something needs to stand out, give it a rule or a texture. A shadow is never the answer.

## Shapes

Square. Panels, fields, buttons and cells have no radius; the language chip and segmented control use 3px at most. Symbols are drawn at a single 2.2px stroke on a 26px box: triangle for the destination, double circle for iParking 嘟嘟房, circle for 嘟嘟房 or 台灣聯通, cross for others.

## Components

### Buttons
- **Primary (navigate):** Course Purple fill, white text, 48px tall, square, full width.
- **Submit (search):** Ink fill, paper text, attached to the field with a 1.6px rule.
- **Text button:** Ink, underlined, 44px tap height; the colour never changes to blue.
- **Focus:** 3px Course Purple outline, 2px offset, on everything.

### Chips and Segments
- **Language chip:** 1.5px ink border, 3px radius, paper fill.
- **Segmented sort control:** two cells in one 1.5px frame; the pressed cell is ink on paper-colour text.

### Inputs / Fields
- **Style:** paper fill, 1.6px ink border, leading purple start triangle, 52px tall.
- **Focus:** the whole field takes the 3px purple outline.

### Group bands
- **Preferred:** open-land yellow, 13px bold label, count on the right, 1.5px rules above and below.
- **Other:** paper, same rules.

### Spaces cell (signature)
Four states, each readable without colour: plain numeral (known), green diagonal hatch with age text (old), black diagonal hatch with "滿" (full), dot screen with "無資料" (no data). A reading above the lot's listed capacity prints with "~" and "約".

### Roulette ("what shall we eat today")
A full-width outlined button in Course Purple above the food table. While it runs, a row is tinted
as the roulette passes over it (11% purple wash, purple row letter), the row it is on right now is
tinted stronger (30%), and the chosen row ends filled solid purple with paper-coloured text. The
route colour is used because choosing a place is drawing the course to it. Reduced motion skips the
animation and fills the chosen row at once.

After a pick, "not this one, pick again" crosses the chosen row out (strikethrough, 55% opacity,
the way an orienteer strikes a control already dealt with) and spins again over the rows that are
left. Crossed-out rows are never visited; "restore all" clears them.

### Course panel
A square compass diagram: dotted rings, an N tick, the start triangle at centre and the lot as a double circle at its bearing. It shows direction only; it is not to scale and is never presented as a map.

## Do's and Don'ts

### Do:
- **Do** keep purple to the route: start triangle, opened lot, course line, primary action, focus ring.
- **Do** state age next to any count that is older than a few minutes.
- **Do** use hatches and dot screens for state, with words as the backup.
- **Do** keep every control at least 44px tall.
- **Do** verify both light and dark: the dark sheet inverts ink and paper and lightens each map ink.
- **Do** keep light as the default; dark is opt-in (header chip cycles Light → Dark → Auto, saved in the browser).

### Don't:
- **Don't** put a shadow, gradient, glass or rounded card anywhere.
- **Don't** show "no data" as zero, or a stale reading as fresh.
- **Don't** use blue for anything but links that leave for an outside map.
- **Don't** add a second accent colour for decoration.
- **Don't** put an eyebrow or kicker above a heading; the band label is the heading.
- **Don't** embed a map: Google content must not be combined with a non-Google map.
