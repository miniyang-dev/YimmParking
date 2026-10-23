"""Query use cases: nearby parking, address resolution, nearby food."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import timedelta
from enum import StrEnum

from yimmparking.application.ports import (
    Clock,
    GeocodeCache,
    Geocoder,
    LotRepository,
    PlaceSource,
    QuotaExceeded,
    RoutesError,
    TravelRouter,
)
from yimmparking.domain.geo import GeoPoint, bounding_box, haversine_m
from yimmparking.domain.model import (
    Availability,
    Freshness,
    FreshnessPolicy,
    GeocodeCandidate,
    Place,
    RouteTime,
    TravelMode,
)
from yimmparking.domain.opening import open_at
from yimmparking.domain.ranking import (
    Candidate,
    RankedLot,
    RankingPolicy,
    arrange,
    pool_within_radius,
    shortlist,
)

log = logging.getLogger(__name__)

# Google's terms allow lat/lng to be cached for at most 30 consecutive days; stay inside it.
GEOCODE_CACHE_TTL = timedelta(days=28)


@dataclass(frozen=True, slots=True)
class ParkingHit:
    ranked: RankedLot
    availability: Availability
    freshness: Freshness


class WalkingStatus(StrEnum):
    """Where the walking times on a result came from."""

    GOOGLE = "google"
    QUOTA_EXHAUSTED = "quota_exhausted"  # monthly self-imposed limit reached
    UNAVAILABLE = "unavailable"  # no router configured, or it failed


@dataclass(frozen=True, slots=True)
class ParkingSearchResult:
    center: GeoPoint
    radius_m: int
    pool_size: int  # lots inside the radius, of which only a shortlist is shown
    walking: WalkingStatus
    hits: tuple[ParkingHit, ...]


class SearchNearbyParking:
    def __init__(
        self,
        repo: LotRepository,
        clock: Clock,
        freshness: FreshnessPolicy | None = None,
        router: TravelRouter | None = None,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._freshness = freshness or FreshnessPolicy()
        self._router = router

    def execute(self, center: GeoPoint, policy: RankingPolicy | None = None) -> ParkingSearchResult:
        policy = policy or RankingPolicy()
        box = bounding_box(center, policy.max_radius_m)
        candidates = [
            Candidate(lot=lot, distance_m=haversine_m(center, lot.location))
            for lot in self._repo.lots_in_box(box)
        ]
        pool = pool_within_radius(candidates, policy)

        # Walking time is billed per lot, so only a shortlist is routed. Every other lot stays in
        # the list, ordered by straight-line distance after those that have a time. If routing is
        # not available the whole list is still returned and labelled.
        routed = shortlist(pool, policy)
        walks: dict[str, RouteTime | None] = {}
        status = WalkingStatus.UNAVAILABLE
        if self._router is not None and routed:
            destinations = [(c.lot.id, c.lot.location) for c in routed]
            try:
                walks = self._router.travel_times(center, destinations, TravelMode.WALK)
                status = WalkingStatus.GOOGLE
            except QuotaExceeded:
                status = WalkingStatus.QUOTA_EXHAUSTED
            except RoutesError as exc:
                log.warning("travel times unavailable: %s", exc)
        ranked = arrange([(c, walks.get(c.lot.id)) for c in pool.candidates], policy)

        ids = [item.lot.id for item in ranked]
        readings = self._repo.latest_availability(ids)
        sources = self._repo.availability_sources(ids)
        now = self._clock.now()
        hits: list[ParkingHit] = []
        for item in ranked:
            reading = readings.get(item.lot.id)
            if reading is None:
                availability = Availability.unknown()
                freshness = Freshness.UNKNOWN
            else:
                count, observed_at = reading
                freshness = self._freshness.classify(observed_at, now)
                source = sources.get(item.lot.id)
                availability = Availability.from_reading(
                    count, item.lot.total_car, observed_at, source
                )
                if freshness is Freshness.EXPIRED:
                    # A reading this old is worse than none: showing it would imply a live count.
                    availability = Availability(count=None, observed_at=observed_at, source=source)
            hits.append(ParkingHit(ranked=item, availability=availability, freshness=freshness))
        return ParkingSearchResult(
            center=center,
            radius_m=pool.radius_m,
            pool_size=len(pool.candidates),
            walking=status,
            hits=tuple(hits),
        )


_WS = re.compile(r"\s+")


def normalize_address(text: str) -> str:
    """Canonical form used for cache keys: NFKC, 臺→台, no inner whitespace."""
    text = unicodedata.normalize("NFKC", text).replace("臺", "台")
    return _WS.sub("", text).strip()


class ResolveAddress:
    def __init__(self, geocoder: Geocoder, cache: GeocodeCache, clock: Clock) -> None:
        self._geocoder = geocoder
        self._cache = cache
        self._clock = clock

    def execute(self, query: str) -> list[GeocodeCandidate]:
        key = normalize_address(query)
        if not key:
            return []
        now = self._clock.now()
        cached = self._cache.get_geocode(key, now)
        if cached is not None:
            return cached
        candidates = self._geocoder.geocode(query.strip())
        if candidates:
            self._cache.put_geocode(key, candidates, now, GEOCODE_CACHE_TTL)
        return candidates


@dataclass(frozen=True, slots=True)
class FoodHit:
    place: Place
    distance_m: float


@dataclass(frozen=True, slots=True)
class FoodSearchResult:
    hits: tuple[FoodHit, ...]
    min_rating: float
    min_reviews: int


class SearchNearbyFood:
    """Nearby places worth eating at.

    The rating floor is pushed to the provider (so the few result slots a request returns are not
    spent on low-rated places). The review-count floor cannot be: no provider filter exists for
    it, so it is applied here. Billing is per request, not per result.
    """

    def __init__(
        self,
        source: PlaceSource,
        min_rating: float = 4.0,
        min_reviews: int = 100,
        clock: Clock | None = None,
    ) -> None:
        self._source = source
        self._min_rating = min_rating
        self._min_reviews = min_reviews
        self._clock = clock

    def execute(
        self,
        center: GeoPoint,
        radius_m: int = 1000,
        limit: int = 20,
        origin: GeoPoint | None = None,
    ) -> FoodSearchResult:
        places = self._source.nearby_food(center, radius_m, limit, self._min_rating, origin)
        hits: list[FoodHit] = []
        for place in places:
            distance = haversine_m(center, place.location)
            # The provider restricts to a rectangle, whose corners lie beyond the radius.
            if distance > radius_m:
                continue
            rating, reviews = place.rating, place.user_rating_count
            if rating is None or rating < self._min_rating:
                continue
            if reviews is None or reviews < self._min_reviews:
                continue
            # Open status is worked out now from the weekly schedule, not read from a cache.
            if self._clock is not None and place.opening is not None:
                place = replace(place, open_now=open_at(place.opening, self._clock.now()))
            hits.append(FoodHit(place=place, distance_m=distance))
        # Real walking time when the provider returned it, else straight-line distance.
        hits.sort(
            key=lambda h: (
                h.place.walking.seconds if h.place.walking else float("inf"),
                h.distance_m,
            )
        )
        return FoodSearchResult(
            hits=tuple(hits), min_rating=self._min_rating, min_reviews=self._min_reviews
        )
