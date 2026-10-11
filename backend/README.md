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

## Data caveats

- No operator field exists in either feed; brand is inferred from name, then phone number.
- Availability `-9` means "no data" and is never shown as zero. New Taipei has no real-time data
  for 嘟嘟房 / 台灣聯通 lots.
- Reported capacity is unreliable; a reading above it is flagged `suspect`, not corrected.
- Google content (geocode, places) is passed through; geocode results are cached as coordinates only, for 28 days (Google allows ≤30).
  See "Result cache" for the places cache.
