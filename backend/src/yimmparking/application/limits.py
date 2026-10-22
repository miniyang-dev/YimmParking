"""Self-imposed ceilings on paid external APIs.

A call is counted *before* it is made and refused once the period's limit is reached, so the
account can never exceed the free tier these limits are set under. Counting an attempt that later
fails is deliberate: Google bills the request, not the outcome.
"""

from __future__ import annotations

from yimmparking.application.ports import (
    Clock,
    Geocoder,
    PlaceSource,
    QuotaExceeded,
    QuotaStore,
    TravelRouter,
)
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import GeocodeCandidate, Place, RouteTime, TravelMode

GEOCODING = "geocoding"
PLACES_NEARBY = "places_nearby"
ROUTES_ELEMENTS = "routes_elements"


def period_of(clock: Clock) -> str:
    """Calendar month, e.g. "2026-10". Google's cap resets monthly; callers keep a margin below
    the free tier to absorb the few hours by which its billing month boundary can differ."""
    return clock.now().strftime("%Y-%m")


class UsageGate:
    """Owns every meter's limit, so enforcement and reporting can never disagree."""

    def __init__(self, store: QuotaStore, clock: Clock, limits: dict[str, int]) -> None:
        self._store = store
        self._clock = clock
        self._limits = dict(limits)

    @property
    def meters(self) -> tuple[str, ...]:
        return tuple(self._limits)

    def limit(self, meter: str) -> int:
        return self._limits[meter]

    def acquire(self, meter: str, amount: int = 1) -> None:
        period = period_of(self._clock)
        limit = self._limits[meter]
        if not self._store.try_consume(meter, period, limit, amount):
            raise QuotaExceeded(meter, limit, period)

    def used(self, meter: str) -> int:
        return self._store.used(meter, period_of(self._clock))

    @property
    def period(self) -> str:
        return period_of(self._clock)


class LimitedGeocoder:
    def __init__(self, inner: Geocoder, gate: UsageGate) -> None:
        self._inner = inner
        self._gate = gate

    def geocode(self, query: str) -> list[GeocodeCandidate]:
        self._gate.acquire(GEOCODING)
        return self._inner.geocode(query)


class LimitedPlaces:
    def __init__(self, inner: PlaceSource, gate: UsageGate) -> None:
        self._inner = inner
        self._gate = gate

    def nearby_food(
        self,
        center: GeoPoint,
        radius_m: int,
        limit: int,
        min_rating: float = 0.0,
        origin: GeoPoint | None = None,
    ) -> list[Place]:
        self._gate.acquire(PLACES_NEARBY)
        return self._inner.nearby_food(center, radius_m, limit, min_rating, origin)


class LimitedRouter:
    """Counts one unit per destination: the routing service bills per origin-destination pair."""

    def __init__(self, inner: TravelRouter, gate: UsageGate) -> None:
        self._inner = inner
        self._gate = gate

    def travel_times(
        self, origin: GeoPoint, destinations: list[tuple[str, GeoPoint]], mode: TravelMode
    ) -> dict[str, RouteTime | None]:
        if not destinations:
            return {}
        self._gate.acquire(ROUTES_ELEMENTS, len(destinations))
        return self._inner.travel_times(origin, destinations, mode)
