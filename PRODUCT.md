# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python backend (FastAPI, clean architecture; already built in `backend/`) and a TypeScript web client (Vite + React) in `web/`, typed from the backend's OpenAPI. Chosen by the user. Mobile web, not a native app; installable PWA is possible later but not decided.

## Users

Primary: the owner and people close to them, driving in Taipei / New Taipei, usually on a phone, one-handed, often outdoors in daylight or at night, deciding where to park before or during a trip. They may be standing at a destination or sitting in a car. They have seconds, not minutes.
Later, possibly: the general public of drivers who arrive cold and must understand the screen at first sight. Not committed.

## Product Purpose

Type a Taiwan address and immediately see the parking lots near it, ordered by distance, with the operators the owner prefers (嘟嘟房 and 台灣聯通) surfaced first, and 嘟嘟房 lots usable through iParking at the very top. Show how many spaces are left and how fresh that number is. Secondarily, show what is worth eating nearby, and from a restaurant jump to parking near it.
Success: from typing an address to a trustworthy "go here" in a few seconds, and never being misled by a number that looked more certain than it was.

## Positioning

A parking finder that is opinionated about operators (brand priority is the point, not a filter) and honest about data quality: it distinguishes "full", "no data" and "stale", which general map apps blur together. The brand tiers and iParking support come from joining government open data with the iParking directory; a general map product does not do that.

## Operating Context

- Data: 臺北市 and 新北市 government open-data feeds (static lots + real-time remaining spaces), the iParking public station list, Google Geocoding for addresses and Google Places for food.
- Taipei real-time data runs about 4–7 minutes behind wall-clock time; New Taipei updates about every 3 minutes with no timestamp.
- 新北 嘟嘟房 / 台灣聯通 lots carry no real-time space data at all (the feed reports -9); only location, fee and capacity exist.
- Operator is not a field in either feed; it is inferred from name and phone number, so a brand label can be wrong and should carry its evidence.
- Local development only for now; deployment is undecided.

## Capabilities and Constraints

- Search by Taiwan address (Google Geocoding) or by coordinates ("use my location").
- Ranking: the user orders the large vendors (嘟嘟房 with iParking, 嘟嘟房, 台灣聯通, Times, USPACE) and chooses how many of each to show first (default 2, max 8). Everything else follows by walking time where it exists, then straight-line distance. A distance-only mode drops the vendors. Search radius widens (1.5 → 3 → 5 km) only when too few lots are found.
- Availability states that must stay visually distinct: known count, zero (full), no data, stale, suspect (reading above listed capacity).
- Every lot in range is listed, but walking time is billed per lot, so only 8 are routed (the nearest of each vendor the user puts first, then the nearest of the rest). Straight-line distance is always labelled as such; a time is never estimated from it.
- Food comes from Google Places and is passed through live: no storage beyond place id, Google attribution is required, and Google content may not be shown on a non-Google map. Therefore v1 has no embedded map; it links out to Google Maps for directions.
- UI language: Traditional Chinese (Taiwan) and English. The product name is YimmParking.
- Undecided: embedded map (needs Google Maps JS), PWA install.

## Brand Commitments

Name: YimmParking. No logo, voice guide, or visual identity exists yet; none is committed.

## Evidence on Hand

- Real data in the local database: 1,758 Taipei lots and 1,365 New Taipei lots; 157 + 33 嘟嘟房 lots, 73 + 26 台灣聯通 lots; 175 iParking stations of which 77 + 12 matched to government lots.
- Measured data quality (2026-10-10, two sample times only): Taipei real-time covers ~69% of lots; New Taipei has real data for ~30% of lots and none for 嘟嘟房 / 台灣聯通.
- No user research, usage numbers, testimonials, or screenshots exist. Do not invent any.
- No Google API key has been provided yet, so address search and food have not been exercised against the live Google services.

## Product Principles

1. Honest numbers beat confident numbers: unknown, stale and suspect are shown as such, never as zero or as fresh.
2. The list is the product; secondary context (food, directions) never pushes it below the first screen.
3. Preference is explicit and explainable: a lot is ranked first because of a stated reason (brand, iParking), and the user can turn the preference off.
4. Distance is always visible; ranking by brand must never hide how far something is.
5. Fast to read in motion: one glance yields name, distance, spaces left, and whether to trust that number.

## Accessibility & Inclusion

Used while driving or in glare: large touch targets, high contrast in both light and dark themes, numbers readable at a glance, no information carried by color alone. Bilingual (繁中 / English). Reduced-motion respected.
