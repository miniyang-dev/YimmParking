"""Travel-time cache in front of the (billed) routing service.

The time between two fixed points changes rarely, so a lookup already answered is served from the
store and only the missing pairs are sent. As with the food cache this is an owner-chosen trade:
Google's terms expressly allow caching only coordinates and place ids, not durations. The TTL is a
setting and `0` turns the cache off.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

from yimmparking.application.ports import Clock, RouteCache, TravelRouter
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import RouteTime, TravelMode

log = logging.getLogger(__name__)


def route_key(origin: GeoPoint, destination_id: str, mode: TravelMode) -> str:
    # 4 decimal places is about 11 m: a search for the same place hits the same entries. The mode is
    # part of the key: the same pair has a different time on foot and by bicycle.
    return f"route|{mode.value}|{origin.lat:.4f},{origin.lng:.4f}|{destination_id}"


class CachedRouter:
    def __init__(
        self, inner: TravelRouter, store: RouteCache, clock: Clock, ttl: timedelta
    ) -> None:
        self._inner = inner
        self._store = store
        self._clock = clock
        self._ttl = ttl
        # Serialises misses so two identical searches at once are not both billed.
        self._lock = threading.Lock()

    def travel_times(
        self, origin: GeoPoint, destinations: list[tuple[str, GeoPoint]], mode: TravelMode
    ) -> dict[str, RouteTime | None]:
        keys = {dest_id: route_key(origin, dest_id, mode) for dest_id, _ in destinations}
        with self._lock:
            hits = self._store.get_routes(list(keys.values()), self._clock.now())
            missing = [(i, p) for i, p in destinations if keys[i] not in hits]
            fetched: dict[str, RouteTime | None] = {}
            if missing:
                log.info(
                    "route cache (%s): %d hit, %d miss (calling router)",
                    mode.value,
                    len(destinations) - len(missing),
                    len(missing),
                )
                fetched = self._inner.travel_times(origin, missing, mode)
                # A pair with no route is cached too: it was billed and would answer the same.
                self._store.put_routes(
                    {keys[i]: fetched.get(i) for i, _ in missing}, self._clock.now(), self._ttl
                )
            else:
                log.info("route cache (%s): all %d hit (no request)", mode.value, len(destinations))

        return {
            dest_id: hits[keys[dest_id]] if keys[dest_id] in hits else fetched.get(dest_id)
            for dest_id, _ in destinations
        }
