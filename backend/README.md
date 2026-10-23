# YimmParking backend

Nearby parking lots for Taipei / New Taipei, ranked by distance with brand priority
(iParking-supported 嘟嘟房 → 嘟嘟房 → 台灣聯通 → others), plus nearby food.

## Layout (dependencies point inward)

```
interface/    FastAPI, CLI, composition root      → application, adapters (wiring only)
adapters/     feeds, stores, geocoder, places      → application ports
application/  use cases + ports (Protocols)        → domain
domain/       entities, ranking, brand rules       → nothing
```

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env        # add GOOGLE_MAPS_API_KEY
```

## Run

```bash
# ingestion — dry-run by default, prints the target database first
yimmparking refresh-lots [--yes]
yimmparking refresh-availability [--yes]

yimmparking worker              # loop: availability every 2 min, lots daily
yimmparking serve --port 8000   # HTTP API, OpenAPI at /docs

# one-off, services stopped: old per-poll history → change-only history (dry-run by default)
yimmparking convert-history [--yes]
```

## Test

```bash
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m mypy
```

Tests never touch the network: an autouse fixture fails on any real HTTP transport, and adapters
take an injected `httpx.Client` backed by recorded fixtures in `tests/fixtures/`.

## Paid-API ceilings

Google calls are counted per calendar month in SQLite (`api_usage`) *before* they are made, and
refused with HTTP 429 `quota_exhausted` once the limit is reached, so the free tier cannot be
exceeded. Defaults sit 10% under it: Geocoding 9,000 (free 10,000) and Places Nearby Search 900
(free 1,000 at the Enterprise tier, which the requested rating fields fall in). Change them with
`YIMM_GEOCODE_MONTHLY_LIMIT` / `YIMM_PLACES_MONTHLY_LIMIT`. `/api/v1/health` reports usage.

The counters only see this app: another project sharing the same key is not counted, and Google's
billing month may start a few hours off the UTC month used here (the margin absorbs that).

## Result cache

| What | Where | TTL | Terms |
|---|---|---|---|
| Geocode (address → coordinates) | SQLite `geocode_cache` | 28 days | Google allows lat/lng ≤ 30 days |
| Food results per lot | SQLite `place_cache` | 24 h (`YIMM_FOOD_CACHE_TTL_HOURS`, `0` = off) | **Not expressly allowed**: Google's terms permit caching only coordinates (≤ 30 days) and place ids |

The food cache is a deliberate, owner-chosen trade of terms risk for fewer billed calls. A hit makes
no request and spends no quota; the cache sits outside the quota gate. Identical simultaneous
lookups are collapsed into one. Empty answers are cached (they were billed); errors never are.
Set `YIMM_FOOD_CACHE_TTL_HOURS=0` to disable it.

One lookup is one request returning at most 20 places: the response is never paginated.

## Vendors and walking time

Every lot in range is listed. Large vendors (嘟嘟房 with and without iParking, 台灣聯通, Times,
USPACE) can be put first by the user, with a count each (default 2, max 8), in the order chosen on
the settings page; the setting is sent with each search as `vendors=iparking_dodohome:2,dodohome:2,…`.
Small operators are not configurable: their lots follow the vendor sections, by distance. Only the
vendors in the `Vendor` enum are accepted; any other name is refused with HTTP 422.

Walking time comes from the Google Routes API (Compute Route Matrix) from the search origin, billed
per origin-destination pair, so only 8 lots are routed in one batched request: the nearest lots of
each vendor in the user's order, then the nearest of the rest. Within a vendor section, lots with a
walking time come first, ordered by it; the rest follow by straight-line distance and carry no time.
A time is never invented.

- Routes elements are counted before the call and capped at `YIMM_ROUTES_MONTHLY_LIMIT` (9,000);
  past it the list falls back to straight-line distance and `meta.walking` says so. A fresh search
  spends up to 8 elements; a repeat of the same place spends none.
- Pairs are cached for 30 days (`YIMM_ROUTE_CACHE_TTL_DAYS`); a cache hit spends no quota. Google's
  terms do not expressly allow caching durations, so this is an owner-chosen trade, like the food
  cache.
- Food walking times come back in the same Text Search request (`routingSummaries`), so they cost no
  Routes elements; that request is billed in the Enterprise + Atmosphere tier (still 1,000 free).
- There is no cycling time on purpose: a Routes request takes a single travel mode, so a second mode
  is a second billed request and doubles the element spend.

## Food quality floor

Food comes from Google Places **Text Search** (not Nearby Search) because only it accepts
`minRating`: places below the floor (default 4.0) are excluded by Google before they can fill the
20 result slots. A review-count floor (default 100) cannot be sent to Google, so it is applied after
the response. Billing is per request, not per result, so this improves the quality of the slots,
not the cost. Results are restricted to a rectangle and trimmed to the radius afterwards.

## Availability history

Kept for a later "will there be a space when I get there" estimate; nothing reads it yet.

- `availability_change`: a lot's count is stored only when it differs from its previous reading,
  so the value at any moment is the last change at or before it. Lots are integer keys
  (`lot_key`), times are whole UTC seconds.
- `availability_poll`: every feed read with a new timestamp, per city. A feed that stops (or keeps
  repeating one timestamp) leaves a gap here, so a frozen number is not mistaken for a steady one.
- Kept 365 days (`YIMM_HISTORY_DAYS`), about 1.4 MB a day. The worker drops older rows daily, keeping
  each lot's last change before the window so the window's first hours still have a value.

Releases before this stored every reading of every poll in `availability_observation` (about
130 MB a day with its indexes). `yimmparking convert-history --yes` moves it into the tables
above, checks every old reading against the rebuilt history, then drops the old table and compacts
the file; on any mismatch nothing is changed. Without `--yes` it opens the database read-only and
only reports. Stop the API and the worker first, and back the file up.

## Street parking (TDX)

Metered road segments near the search origin, from MOTC TDX's OnStreet API
(`/v1/Parking/OnStreet/ParkingSegment/City/{City}` and `.../ParkingSegmentAvailability/City/{City}`,
Taipei and NewTaipei). Set `TDX_CLIENT_ID` / `TDX_CLIENT_SECRET` (free TDX member key); without them
the endpoint answers 503 and the client hides the section.

- Token: OAuth client credentials, cached until shortly before `expires_in`; a failed token request
  fails fast for a minute instead of each city waiting out a timeout.
- Segments are read once a day, live counts at most every 2 minutes per city; a failed read is
  retried after 2 minutes, and served from the last copy meanwhile (up to 30 minutes for counts).
- Counts: the car-space reading (`SpaceType` 1) when given, else the all-types total, labelled as such.
  `-1` is "unknown", never zero. Distance is straight-line to the segment's marker point.
- Checked against the live service (2026-10-23): the list is named per endpoint
  (`ParkingSegments`, `CurbParkingSegmentAvailabilities`), not `Items` as the OpenAPI document says;
  `FullStatus` can be `-1` (unknown). Taipei has ~2,400 segments refreshed every 5 minutes, New Taipei
  ~600 running 15–20 minutes behind (the age is shown past 15 minutes). Segments with only scooter
  spaces (no car type in the breakdown) are not listed. `tests/fixtures/tdx_curb_*.json` are recorded.
- Rate limit: 5 calls a minute per key (`x-ratelimit-limit-minute`). A search reads at most four
  (segments and counts for two cities) and then serves from memory; a 429 is retried after 2 minutes.

## Taipei counts from TDX when the city's feed stops

臺北市's own feed has stalled for days while still answering (the same UPDATETIME every time). With
TDX credentials set, Taipei's counts come from the city feed while its newest reading is under
30 minutes old, and from TDX's off-street data (`/v1/Parking/OffStreet/ParkingAvailability/City/Taipei`,
same `TPE…` car park ids) otherwise; the city feed is used again as soon as it moves. Each latest
reading keeps its source (`availability_latest.source`, migration v6); the API returns it per lot
and `/api/v1/health` per city (`availability_source`), and the web client says when TDX is in use.
TDX publishes no New Taipei equivalent. A TDX row more than 30 minutes behind the newest row is
treated as no data.

## Data caveats

- No operator field exists in either feed; brand is inferred from name, then phone number.
- Availability `-9` means "no data" and is never shown as zero. New Taipei has no real-time data
  for 嘟嘟房 / 台灣聯通 lots.
- Reported capacity is unreliable; a reading above it is flagged `suspect`, not corrected.
- Google content (geocode, places) is passed through; geocode results are cached as coordinates only, for 28 days (Google allows ≤30).
  See "Result cache" for the places cache.
