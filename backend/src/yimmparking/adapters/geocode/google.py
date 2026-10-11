"""Google Geocoding API adapter.

Terms that shape its use (Google Maps Platform service-specific terms): latitude/longitude may be
cached for at most 30 days, and the results must not be combined with a non-Google map.
"""

from __future__ import annotations

import httpx

from yimmparking.application.ports import GeocodingError, GeocodingUnavailable
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import GeocodeCandidate

ENDPOINT = "https://maps.googleapis.com/maps/api/geocode/json"
MAX_CANDIDATES = 5


class GoogleGeocoder:
    def __init__(self, http: httpx.Client, api_key: str | None, endpoint: str = ENDPOINT) -> None:
        self._http = http
        self._api_key = api_key
        self._endpoint = endpoint

    def geocode(self, query: str) -> list[GeocodeCandidate]:
        if not self._api_key:
            raise GeocodingUnavailable("GOOGLE_MAPS_API_KEY is not configured")
        try:
            response = self._http.get(
                self._endpoint,
                params={
                    "address": query,
                    "key": self._api_key,
                    "language": "zh-TW",
                    "region": "tw",
                    "components": "country:TW",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GeocodingUnavailable(f"geocoder unreachable: {exc}") from exc

        status = payload.get("status")
        if status == "ZERO_RESULTS":
            return []
        if status != "OK":
            # REQUEST_DENIED / OVER_QUERY_LIMIT / INVALID_REQUEST: surface it, never an empty list,
            # or "your key is broken" would look like "no such address".
            detail = payload.get("error_message") or status
            raise GeocodingError(f"geocoder returned {status}: {detail}")

        candidates: list[GeocodeCandidate] = []
        for result in payload.get("results", [])[:MAX_CANDIDATES]:
            loc = result.get("geometry", {}).get("location", {})
            try:
                point = GeoPoint(float(loc["lat"]), float(loc["lng"]))
            except (KeyError, TypeError, ValueError):
                continue
            candidates.append(
                GeocodeCandidate(
                    formatted_address=str(result.get("formatted_address", query)),
                    location=point,
                    place_id=result.get("place_id"),
                )
            )
        return candidates
