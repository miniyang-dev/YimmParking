"""Google Places API (New) — Text Search for food.

Text Search is used instead of Nearby Search because only it accepts `minRating`, so low-rated
places are excluded by Google before they can occupy one of the (at most 20) result slots. It
bills like Nearby Search (the rating fields put it in the Enterprise tier, 1,000 free/month) and
`minRating` does not change the tier.

Policy constraints (Places API policies): results must not be pre-fetched or stored beyond the
Place ID, must carry Google Maps attribution, and must not be combined with a non-Google map.
This adapter therefore only ever passes results through.

Billing note: requesting rating, price level or opening hours moves a call to the Enterprise
SKU; the field mask below is the single place that decides which SKU a call lands in.

Walking time to every result comes in the same request (`routingParameters` +
`routingSummaries`), so no separate routing call is needed for food. Asking for it moves the call
to the Enterprise + Atmosphere SKU: $40 instead of $35 per 1,000, same 1,000 free per month.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

from yimmparking.application.ports import PlacesError
from yimmparking.domain.geo import GeoPoint, bounding_box
from yimmparking.domain.model import Place, RouteTime
from yimmparking.domain.opening import MINUTES_PER_WEEK, OpeningPeriod, minutes_of

log = logging.getLogger(__name__)

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.primaryType",
        "places.primaryTypeDisplayName",
        "places.regularOpeningHours.periods",
        "places.googleMapsUri",
    ]
)
MAX_RESULTS = 20
# "餐廳" skews towards places with the word in their name or category (mostly Western and chain
# restaurants); "美食" returned a more varied, locally typical set in a real-data comparison.
QUERY = "美食"
DEFAULT_TYPE = "restaurant"


def server_rating_floor(min_rating: float) -> float:
    """`minRating` accepts 0.5 steps only. Round *down* so no qualifying place is lost; the exact
    threshold is applied again by the caller."""
    return max(0.0, min(5.0, math.floor(min_rating * 2) / 2))


def _parse_walking(summary: Any) -> RouteTime | None:
    """`{"legs": [{"duration": "597s", "distanceMeters": 812}]}` → RouteTime, else None."""
    try:
        leg = summary["legs"][0]
        seconds = int(str(leg["duration"]).rstrip("s"))
        return RouteTime(seconds=seconds, meters=int(leg["distanceMeters"]))
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _point_in_week(point: dict[str, Any]) -> int:
    """`{"day": 1, "hour": 11, "minute": 0}` → minutes from Sunday 00:00. Raises on bad input."""
    day = int(point["day"])
    if not 0 <= day <= 6:
        raise ValueError(f"day out of range: {day}")
    return minutes_of(day, int(point.get("hour", 0)), int(point.get("minute", 0)))


def _parse_opening(raw: dict[str, Any]) -> tuple[OpeningPeriod, ...] | None:
    """Weekly schedule from `regularOpeningHours`; None when Google did not say.

    A schedule that cannot be read is also None ("unknown"), never a partial one: dropping a
    malformed period would make the place look closed when it is open. It must not fail the whole
    request either, which has already been billed.
    """
    periods = (raw.get("regularOpeningHours") or {}).get("periods")
    if not periods:
        return None
    parsed: list[OpeningPeriod] = []
    try:
        for period in periods:
            start = _point_in_week(period["open"])
            closed = period.get("close")
            if closed is None:  # open with no close: open all week
                return (OpeningPeriod(start=0, end=MINUTES_PER_WEEK),)
            end = _point_in_week(closed)
            if end <= start:  # closes after midnight, into the next day (or the next week)
                end += MINUTES_PER_WEEK
            parsed.append(OpeningPeriod(start=start, end=end))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        log.warning("place %s: unreadable opening hours, so unknown: %s", raw.get("id"), exc)
        return None
    return tuple(parsed)


def _parse_place(raw: dict[str, Any], walking: RouteTime | None = None) -> Place | None:
    loc = raw.get("location") or {}
    try:
        point = GeoPoint(float(loc["latitude"]), float(loc["longitude"]))
    except (KeyError, TypeError, ValueError):
        return None
    place_id = raw.get("id")
    name = (raw.get("displayName") or {}).get("text")
    if not place_id or not name:
        return None
    price = raw.get("priceLevel")
    return Place(
        id=str(place_id),
        name=str(name),
        location=point,
        address=str(raw.get("formattedAddress", "")),
        rating=raw.get("rating"),
        user_rating_count=raw.get("userRatingCount"),
        price_level=str(price).removeprefix("PRICE_LEVEL_") if price else None,
        primary_type=(raw.get("primaryTypeDisplayName") or {}).get("text"),
        primary_type_code=raw.get("primaryType"),
        opening=_parse_opening(raw),
        maps_uri=raw.get("googleMapsUri"),
        walking=walking,
    )


class GooglePlaces:
    def __init__(
        self,
        http: httpx.Client,
        api_key: str | None,
        included_type: str = DEFAULT_TYPE,
        endpoint: str = ENDPOINT,
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._type = included_type
        self._endpoint = endpoint

    def nearby_food(
        self,
        center: GeoPoint,
        radius_m: int,
        limit: int,
        min_rating: float = 0.0,
        origin: GeoPoint | None = None,
    ) -> list[Place]:
        if not self._api_key:
            raise PlacesError("GOOGLE_MAPS_API_KEY is not configured")
        # Text Search only restricts to a rectangle; the caller trims the corners by distance.
        box = bounding_box(center, radius_m)
        body: dict[str, Any] = {
            "textQuery": QUERY,
            "includedType": self._type,
            "strictTypeFiltering": True,
            "pageSize": max(1, min(limit, MAX_RESULTS)),
            "rankPreference": "RELEVANCE",
            "languageCode": "zh-TW",
            "regionCode": "TW",
            "locationRestriction": {
                "rectangle": {
                    "low": {"latitude": box.min_lat, "longitude": box.min_lng},
                    "high": {"latitude": box.max_lat, "longitude": box.max_lng},
                }
            },
        }
        server_floor = server_rating_floor(min_rating)
        if server_floor > 0:
            body["minRating"] = server_floor
        field_mask = FIELD_MASK
        if origin is not None:
            # Walking time from `origin` to every result, in this same request.
            body["routingParameters"] = {
                "origin": {"latitude": origin.lat, "longitude": origin.lng},
                "travelMode": "WALK",
            }
            field_mask = FIELD_MASK + ",routingSummaries"
        # The key is never logged; this line is how a billed request can be seen after the fact.
        log.info(
            "GOOGLE places textSearch (billed): query=%s type=%s minRating=%s pageSize=%s "
            "center=%.5f,%.5f radius=%sm walkingFrom=%s",
            QUERY,
            self._type,
            body.get("minRating", "none"),
            body["pageSize"],
            center.lat,
            center.lng,
            radius_m,
            "-" if origin is None else f"{origin.lat:.5f},{origin.lng:.5f}",
        )
        try:
            response = self._http.post(
                self._endpoint,
                json=body,
                headers={"X-Goog-Api-Key": self._api_key, "X-Goog-FieldMask": field_mask},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise PlacesError(f"places returned {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise PlacesError(f"places unreachable: {exc}") from exc

        raws = payload.get("places", [])
        # routingSummaries has one entry per place, in the same order.
        summaries = payload.get("routingSummaries") or []
        out: list[Place] = []
        for index, raw in enumerate(raws):
            summary = summaries[index] if index < len(summaries) else None
            place = _parse_place(raw, _parse_walking(summary) if summary else None)
            if place is not None:
                out.append(place)
        return out
