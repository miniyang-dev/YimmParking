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
from yimmparking.domain.model import BikeStation

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


class SearchNearbyBikes:
    def __init__(self, feeds: list[BikeFeed], clock: Clock, ttl: timedelta = FEED_TTL) -> None:
        self._feeds, self._clock, self._ttl = feeds, clock, ttl
        self._cache: dict[int, tuple[datetime, list[BikeStation]]] = {}
        self._lock = threading.Lock()

    def _stations(self) -> list[BikeStation]:
        now = self._clock.now()
        out: list[BikeStation] = []
        with self._lock:
            for i, feed in enumerate(self._feeds):
                cached = self._cache.get(i)
                if cached is None or now - cached[0] >= self._ttl:
                    try:
                        cached = (now, feed.fetch_stations())
                        self._cache[i] = cached
                    except SourceError as exc:
                        if cached is None or now - cached[0] >= MAX_STALE:
                            raise
                        log.warning(
                            "bikes %s: refresh failed, serving the last copy: %s", feed.city, exc
                        )
                out.extend(cached[1])
        return out

    def execute(self, center: GeoPoint) -> BikeSearchResult:
        # Only stations in service can be used; a closed station is not the same as one with no bikes.
        scored = [BikeHit(s, haversine_m(center, s.location)) for s in self._stations() if s.active]
        scored.sort(key=lambda h: h.distance_m)
        for i, radius in enumerate(RADII_M):
            hits = tuple(h for h in scored if h.distance_m <= radius)[:MAX_STATIONS]
            if hits:
                return BikeSearchResult(radius_m=radius, expanded=i > 0, hits=hits)
        return BikeSearchResult(radius_m=RADII_M[-1], expanded=True, hits=())
