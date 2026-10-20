"""Result cache in front of the (billed) places provider.

A lookup already answered is served from the store instead of being sent again. This is a
deliberate, configurable trade: Google's terms expressly allow caching only coordinates (up to 30
days) and place ids, so holding names and ratings for hours goes beyond them. The TTL is a setting
and `0` turns the cache off.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from yimmparking.application.keyed_locks import KeyedLocks
from yimmparking.application.ports import Clock, PlaceCache, PlaceSource
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import Place

log = logging.getLogger(__name__)


def cache_key(
    center: GeoPoint,
    radius_m: int,
    limit: int,
    min_rating: float,
    origin: GeoPoint | None = None,
) -> str:
    # 5 decimal places is about 1 m: the same lot always maps to the same key. The origin is part
    # of the key because the walking times stored with each place depend on it (about 11 m).
    where = "-" if origin is None else f"{origin.lat:.4f},{origin.lng:.4f}"
    return f"food|{center.lat:.5f}|{center.lng:.5f}|{radius_m}|{limit}|{min_rating:.1f}|{where}"


class CachedPlaces:
    def __init__(self, inner: PlaceSource, store: PlaceCache, clock: Clock, ttl: timedelta) -> None:
        self._inner = inner
        self._store = store
        self._clock = clock
        self._ttl = ttl
        self._locks = KeyedLocks()

    def nearby_food(
        self,
        center: GeoPoint,
        radius_m: int,
        limit: int,
        min_rating: float = 0.0,
        origin: GeoPoint | None = None,
    ) -> list[Place]:
        key = cache_key(center, radius_m, limit, min_rating, origin)
        cached = self._store.get_places(key, self._clock.now())
        if cached is not None:
            log.info("food cache HIT (no request): %s", key)
            return cached

        # Concurrent identical requests wait for the first instead of each being billed.
        with self._locks.hold(key):
            cached = self._store.get_places(key, self._clock.now())
            if cached is not None:
                return cached
            log.info("food cache MISS, calling provider: %s", key)
            places = self._inner.nearby_food(center, radius_m, limit, min_rating, origin)
            # An empty answer is cached too: it was billed, and asking again would not change it.
            # Errors raise before this line and are never cached.
            self._store.put_places(key, places, self._clock.now(), self._ttl)
            return places
