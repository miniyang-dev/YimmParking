---
version: 1
slug: "web-src-app-tsx"
primary_target: "web/src/App.tsx"
related_targets: []
---

# Surface: YimmParking main screen (search → ranked lots → lot detail with food)

Mode: Operate. Mobile-first web. One continuous task: type an address, read the ranked lots, open one, see food within 1 km of that lot.

Audience and job: the owner (later maybe the public) driving in Taipei / New Taipei, one-handed, glare or night, seconds to decide. Needs name, distance, bearing, spaces left, and whether to trust that number.

Proof and content: real data from the backend (`/api/v1/search`, `/api/v1/parking/nearby`, `/api/v1/food/nearby`). Food is Google content: attribution required, no non-Google map, no storage beyond place id. No fabricated numbers; a missing reading is "no data", never zero.

Unresolved: embedded map (not in v1), PWA install, hosting.

## Direction contract

THESIS: The lot list is an orienteering control-description sheet. A destination is the start triangle, every lot is a numbered control, the one lot you choose gets the purple course. Refuses the white-card-with-blue-button parking list.

OWN-WORLD: White "runnable forest" ground with fine brown contour texture only in the sheet header. ISO map inks do jobs: open-land yellow marks the preferred group, thicket green hatch marks stale, black diagonal hatch marks full, a dot screen marks no data, water blue is reserved for links that leave for an outside map. Course purple appears only on the selected lot, its number, its connector line and the primary action. Ruled grid table, 1px black rules, condensed numerals, symbols drawn as SVG: double circle = iParking 嘟嘟房, circle = 嘟嘟房 / 台灣聯通, cross = other.

STORY: Visitor types an address and sees the start triangle with ranked controls. They understand brand priority from the symbols and group bands, read spaces and freshness without colour, open one lot, see bearing and distance as a course line, then food within 1 km of that lot, and navigate out to Google Maps.

FIRST VIEWPORT: 390x844. Contour-textured title block at top: product name, address field led by a purple start triangle, scale bar and brand/distance toggle. Below, the description sheet fills the screen: yellow group band, ruled rows (number, symbol, name with distance and bearing, spaces cell at the right). No row is selected in the list view; purple appears only on the start triangle until a lot is opened.

FORM: Orienteering map and legend (challenger, competitive verdict, chosen by the user over the assigned atlas), seed key 9fd90d67.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
