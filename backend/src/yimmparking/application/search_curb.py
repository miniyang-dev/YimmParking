"""Nearby on-street parking segments, with their live free spaces.

The segment list (with positions) is read once a day per city; live counts are asked only for
the segments near the search, so a city with nothing nearby costs no call, and a search repeated
within `LIVE_TTL` costs none either. As with YouBike, one city that cannot be read leaves the other
listed and is named, so a short list is never mistaken for a full answer.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Generic, TypeVar

from yimmparking.application.ports import Clock, CurbFeed, CurbUnconfigured, SourceError
from yimmparking.domain.curb import CurbReading, CurbSegment, SpaceKind
from yimmparking.domain.geo import GeoPoint, haversine_m
from yimmparking.domain.model import City

log = logging.getLogger(__name__)

RADII_M = (300, 600)  # a driver will walk a few minutes from the curb, not more
MAX_SEGMENTS = 8
# Live counts are asked for this many of the nearest segments within the widest radius: more
# than MAX_SEGMENTS, since scooter-only segments are found out (and dropped) only by asking.
QUERY_LIMIT = 40
SEGMENTS_TTL = timedelta(hours=24)
# TDX's curb counts change every 5 minutes at the source (SrcUpdateInterval 300), and every call
# is metered, so asking more often would only spend points.
LIVE_TTL = timedelta(minutes=5)
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


class _LiveCounts:
    """One city's readings by segment, each kept `LIVE_TTL` and served for up to `MAX_STALE`
    when a refresh fails. A search whose segments are all fresh makes no call; otherwise all of
    them are asked for in one call (same price as asking for the stale ones alone)."""

    def __init__(self) -> None:
        self._readings: dict[str, tuple[datetime, CurbReading | None]] = {}
        self._failed_at: datetime | None = None

    def get(
        self,
        now: datetime,
        ids: Sequence[str],
        fetch: Callable[[Sequence[str]], dict[str, CurbReading]],
        label: str,
    ) -> tuple[dict[str, CurbReading], bool]:
        """The readings known for `ids`, and whether every one of them could be asked about."""
        self._readings = {i: e for i, e in self._readings.items() if now - e[0] < MAX_STALE}
        due = any(i not in self._readings or now - self._readings[i][0] >= LIVE_TTL for i in ids)
        backing_off = self._failed_at is not None and now - self._failed_at < RETRY_AFTER
        if due and not backing_off:
            try:
                got = fetch(ids)
                self._readings.update({i: (now, got.get(i)) for i in ids})
                self._failed_at = None
            except SourceError as exc:
                self._failed_at = now
                log.warning("curb %s: refresh failed: %s", label, exc)
        complete = all(i in self._readings for i in ids)
        found = {
            i: r for i in ids if i in self._readings and (r := self._readings[i][1]) is not None
        }
        return found, complete


def _no_car(reading: CurbReading | None) -> bool:
    """A segment with only scooter (or other) spaces is not listed for a driver."""
    return reading is not None and reading.kind is SpaceKind.NO_CAR


class SearchNearbyCurb:
    def __init__(self, feeds: list[CurbFeed], clock: Clock, *, configured: bool = True) -> None:
        self._feeds, self._clock, self._configured = feeds, clock, configured
        self._segments = {
            f.city: _Cached[list[CurbSegment]](SEGMENTS_TTL, SEGMENTS_MAX_STALE) for f in feeds
        }
        self._live = {f.city: _LiveCounts() for f in feeds}
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
                near = sorted(
                    (
                        (d, s)
                        for s in segments
                        if (d := haversine_m(center, s.location)) <= RADII_M[-1]
                    ),
                    key=lambda pair: pair[0],
                )[:QUERY_LIMIT]
                if not near:
                    continue  # nothing of this city's nearby: no call
                live, complete = self._live[feed.city].get(
                    now, [s.id for _, s in near], feed.fetch_availability, f"{feed.city} live"
                )
                if not complete:
                    missing.append(feed.city)
                scored.extend(
                    CurbHit(s, live.get(s.id), d) for d, s in near if not _no_car(live.get(s.id))
                )
        if self._feeds and len(missing) == len(self._feeds) and not scored:
            raise SourceError(f"no on-street parking feed is readable: {', '.join(missing)}")
        scored.sort(key=lambda h: h.distance_m)
        for i, radius in enumerate(RADII_M):
            hits = tuple(h for h in scored if h.distance_m <= radius)[:MAX_SEGMENTS]
            if hits:
                return CurbSearchResult(radius, i > 0, hits, tuple(dict.fromkeys(missing)))
        return CurbSearchResult(RADII_M[-1], True, (), tuple(dict.fromkeys(missing)))
