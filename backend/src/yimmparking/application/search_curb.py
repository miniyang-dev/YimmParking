"""Nearby on-street parking segments, with their live free spaces.

TDX is read at most once per city per `ttl` for the live counts and once a day for the segment
list; every search in between is served from memory. As with YouBike, one city that cannot be
read leaves the other listed and is named, so a short list is never mistaken for a full answer.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Generic, TypeVar

from yimmparking.application.ports import Clock, CurbFeed, CurbUnconfigured, SourceError
from yimmparking.domain.curb import CurbReading, CurbSegment
from yimmparking.domain.geo import GeoPoint, haversine_m
from yimmparking.domain.model import City

log = logging.getLogger(__name__)

RADII_M = (300, 600)  # a driver will walk a few minutes from the curb, not more
MAX_SEGMENTS = 8
SEGMENTS_TTL = timedelta(hours=24)
LIVE_TTL = timedelta(seconds=120)  # TDX refreshes every minute; this caps our calls per city
MAX_STALE = timedelta(minutes=30)
SEGMENTS_MAX_STALE = timedelta(days=7)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CurbHit:
    segment: CurbSegment
    reading: CurbReading | None  # None: TDX has no live count for this segment
    distance_m: float


@dataclass(frozen=True, slots=True)
class CurbSearchResult:
    radius_m: int
    expanded: bool
    hits: tuple[CurbHit, ...]
    missing: tuple[City, ...] = ()


RETRY_AFTER = timedelta(minutes=2)


class _Cached(Generic[T]):
    """One feed call's result, kept for `ttl` and served for up to `max_stale` when a refresh
    fails. A failed call is not retried for `RETRY_AFTER`, so an outage does not stall every
    search, but a source that comes back is picked up within minutes (not after a whole `ttl`)."""

    def __init__(self, ttl: timedelta, max_stale: timedelta) -> None:
        self._ttl, self._max_stale = ttl, max_stale
        self._value: tuple[datetime, T] | None = None
        self._failed_at: datetime | None = None

    def get(self, now: datetime, fetch: Callable[[], T], label: str) -> T | None:
        due = self._value is None or now - self._value[0] >= self._ttl
        backing_off = self._failed_at is not None and now - self._failed_at < RETRY_AFTER
        if due and not backing_off:
            try:
                self._value = (now, fetch())
                self._failed_at = None
            except SourceError as exc:
                self._failed_at = now
                log.warning("curb %s: refresh failed: %s", label, exc)
        if self._value is None or now - self._value[0] >= self._max_stale:
            return None
        return self._value[1]


class SearchNearbyCurb:
    def __init__(self, feeds: list[CurbFeed], clock: Clock, *, configured: bool = True) -> None:
        self._feeds, self._clock, self._configured = feeds, clock, configured
        self._segments = {
            f.city: _Cached[list[CurbSegment]](SEGMENTS_TTL, SEGMENTS_MAX_STALE) for f in feeds
        }
        self._live = {f.city: _Cached[dict[str, CurbReading]](LIVE_TTL, MAX_STALE) for f in feeds}
        self._lock = threading.Lock()

    def execute(self, center: GeoPoint) -> CurbSearchResult:
        if not self._configured:
            raise CurbUnconfigured("on-street parking needs TDX credentials")
        now = self._clock.now()
        scored: list[CurbHit] = []
        missing: list[City] = []
        with self._lock:
            for feed in self._feeds:
                segments = self._segments[feed.city].get(
                    now, feed.fetch_segments, f"{feed.city} segments"
                )
                if segments is None:
                    missing.append(feed.city)
                    continue
                live = self._live[feed.city].get(
                    now, feed.fetch_availability, f"{feed.city} live"
                )
                if live is None:
                    missing.append(feed.city)
                    live = {}
                scored.extend(
                    CurbHit(s, live.get(s.id), haversine_m(center, s.location)) for s in segments
                )
        if self._feeds and len(missing) == len(self._feeds) and not scored:
            raise SourceError(f"no on-street parking feed is readable: {', '.join(missing)}")
        scored.sort(key=lambda h: h.distance_m)
        for i, radius in enumerate(RADII_M):
            hits = tuple(h for h in scored if h.distance_m <= radius)[:MAX_SEGMENTS]
            if hits:
                return CurbSearchResult(radius, i > 0, hits, tuple(dict.fromkeys(missing)))
        return CurbSearchResult(RADII_M[-1], True, (), tuple(dict.fromkeys(missing)))
