"""Nearby YouBike stations for one point.

Real-time bike counts change every minute or so and are not history we keep, so the feeds are
held in memory for a short time rather than stored.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from yimmparking.application.ports import BikeFeed, Clock, SourceError
from yimmparking.domain.geo import GeoPoint, haversine_m
from yimmparking.domain.model import BikeStation, City

log = logging.getLogger(__name__)

# Tried in order: the first radius that has any station wins, so a lot with a station next door
# never lists far ones, and a lot without gets the wider answer instead of an empty section.
RADII_M = (400, 800)
MAX_STATIONS = 5
FEED_TTL = timedelta(seconds=60)
# A feed that cannot be refreshed is served from its last copy for this long, then it is an error:
# a number older than this is no longer a reading anyone should walk to.
MAX_STALE = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class BikeHit:
    station: BikeStation
    distance_m: float


@dataclass(frozen=True, slots=True)
class BikeSearchResult:
    radius_m: int
    expanded: bool  # True when the first radius was empty and a wider one was used
    hits: tuple[BikeHit, ...]
    # Cities whose feed could not be read: their stations are missing from `hits`, so an empty
    # or short list is not proof that there is no station nearby.
    missing: tuple[City, ...] = ()


class SearchNearbyBikes:
    def __init__(self, feeds: list[BikeFeed], clock: Clock, ttl: timedelta = FEED_TTL) -> None:
        self._feeds, self._clock, self._ttl = feeds, clock, ttl
        self._cache: dict[int, tuple[datetime, list[BikeStation]]] = {}
        # When a feed last failed: it is not asked again until `ttl` has passed, so an outage
        # does not make every request wait for the same timeout.
        self._failed_at: dict[int, datetime] = {}
        self._lock = threading.Lock()

    def _feed_stations(self, i: int, feed: BikeFeed, now: datetime) -> list[BikeStation] | None:
        """This feed's stations (fresh, or a recent copy), or None when it has nothing usable."""
        cached = self._cache.get(i)
        failed = self._failed_at.get(i)
        due = cached is None or now - cached[0] >= self._ttl
        backing_off = failed is not None and now - failed < self._ttl
        if due and not backing_off:
            try:
                cached = (now, feed.fetch_stations())
                self._cache[i] = cached
                self._failed_at.pop(i, None)
            except SourceError as exc:
                self._failed_at[i] = now
                log.warning("bikes %s: refresh failed: %s", feed.city, exc)
        if cached is None or now - cached[0] >= MAX_STALE:
            return None
        return cached[1]

    def _stations(self) -> tuple[list[BikeStation], tuple[City, ...]]:
        now = self._clock.now()
        out: list[BikeStation] = []
        missing: list[City] = []
        with self._lock:
            for i, feed in enumerate(self._feeds):
                stations = self._feed_stations(i, feed, now)
                if stations is None:
                    missing.append(feed.city)
                else:
                    out.extend(stations)
        if self._feeds and len(missing) == len(self._feeds):
            raise SourceError(f"no YouBike feed is readable: {', '.join(missing)}")
        return out, tuple(missing)

    def execute(self, center: GeoPoint) -> BikeSearchResult:
        stations, missing = self._stations()
        # Only stations in service can be used; a closed station is not one with no bikes.
        scored = [BikeHit(s, haversine_m(center, s.location)) for s in stations if s.active]
        scored.sort(key=lambda h: h.distance_m)
        for i, radius in enumerate(RADII_M):
            hits = tuple(h for h in scored if h.distance_m <= radius)[:MAX_STATIONS]
            if hits:
                return BikeSearchResult(radius_m=radius, expanded=i > 0, hits=hits, missing=missing)
        return BikeSearchResult(radius_m=RADII_M[-1], expanded=True, hits=(), missing=missing)
