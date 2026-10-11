"""Google Routes API: travel time from one origin to several destinations in one request.

`computeRouteMatrix` is the batch endpoint. It is billed per element (one origin-destination pair),
so batching saves requests, not money; the caller keeps the destination list short.

Terms (Maps Platform service terms, Routes API): results must not be combined with a non-Google
map, and attribution is required when they are shown without a Google map.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from yimmparking.application.ports import RoutesError
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import RouteTime, TravelMode

log = logging.getLogger(__name__)

ENDPOINT = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
# Only what is needed: a smaller mask keeps the request in the cheapest tier.
FIELD_MASK = "originIndex,destinationIndex,duration,distanceMeters,status,condition"
MAX_ELEMENTS = 100  # well under the 625-element request limit


def _waypoint(point: GeoPoint) -> dict[str, Any]:
    return {"waypoint": {"location": {"latLng": {"latitude": point.lat, "longitude": point.lng}}}}


class GoogleRoutes:
    def __init__(self, http: httpx.Client, api_key: str | None, endpoint: str = ENDPOINT) -> None:
        self._http = http
        self._api_key = api_key
        self._endpoint = endpoint

    def travel_times(
        self, origin: GeoPoint, destinations: list[tuple[str, GeoPoint]], mode: TravelMode
    ) -> dict[str, RouteTime | None]:
        if not self._api_key:
            raise RoutesError("GOOGLE_MAPS_API_KEY is not configured")
        if not destinations:
            return {}
        if len(destinations) > MAX_ELEMENTS:
            raise RoutesError(f"too many destinations in one request: {len(destinations)}")

        log.info(
            "GOOGLE routes computeRouteMatrix (billed per element): %d %s elements from %.5f,%.5f",
            len(destinations),
            mode.value,
            origin.lat,
            origin.lng,
        )
        body = {
            "origins": [_waypoint(origin)],
            "destinations": [_waypoint(point) for _, point in destinations],
            "travelMode": mode.value,
        }
        try:
            response = self._http.post(
                self._endpoint,
                json=body,
                headers={"X-Goog-Api-Key": self._api_key, "X-Goog-FieldMask": FIELD_MASK},
            )
            response.raise_for_status()
            elements = response.json()
        except httpx.HTTPStatusError as exc:
            raise RoutesError(f"routes returned {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise RoutesError(f"routes unreachable: {exc}") from exc

        if not isinstance(elements, list):
            raise RoutesError("routes returned an unexpected body")

        out: dict[str, RouteTime | None] = {dest_id: None for dest_id, _ in destinations}
        for element in elements:
            try:
                index = int(element["destinationIndex"])
                dest_id = destinations[index][0]
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            # A pair that could not be routed carries a non-empty status or a different condition.
            if element.get("status") or element.get("condition") != "ROUTE_EXISTS":
                continue
            try:
                seconds = int(str(element["duration"]).rstrip("s"))
                meters = int(element["distanceMeters"])
            except (KeyError, TypeError, ValueError):
                continue
            out[dest_id] = RouteTime(seconds=seconds, meters=meters)
        return out
