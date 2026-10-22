"""What the availability history adds to a search: trend, doubts, and a lot's typical day."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from yimmparking.application.ports import AvailabilityHistory, Clock
from yimmparking.application.search import ParkingHit
from yimmparking.domain.model import City, Freshness
from yimmparking.domain.occupancy import (
    RELIABILITY_DAYS,
    TAIPEI,
    TYPICAL_WEEKS,
    Doubt,
    Trend,
    TypicalDay,
    doubts,
    trend,
    typical_day,
)


@dataclass(frozen=True, slots=True)
class LotInsight:
    trend: Trend | None = None
    doubts: list[Doubt] = field(default_factory=list)


class LotInsights:
    def __init__(self, history: AvailabilityHistory, clock: Clock) -> None:
        self._history = history
        self._clock = clock

    def for_hits(self, hits: Sequence[ParkingHit]) -> dict[str, LotInsight]:
        """Trend and doubts for each listed lot. Each city's polls are read once per search."""
        now = self._clock.now()
        now_s = int(now.timestamp())
        since = now - timedelta(days=RELIABILITY_DAYS)
        polls = {
            city: self._history.feed_polls(city, since)
            for city in {hit.ranked.lot.city for hit in hits}
        }
        out: dict[str, LotInsight] = {}
        for hit in hits:
            lot = hit.ranked.lot
            changes = self._history.availability_changes(lot.id, since)
            # A trend is only told from a live number: a stale one could be hours behind.
            current = hit.availability.count if hit.freshness is Freshness.FRESH else None
            out[lot.id] = LotInsight(
                trend=trend(changes, polls[lot.city], now_s, current),
                doubts=doubts(changes, polls[lot.city], now_s, lot.total_car),
            )
        return out

    def typical(self, lot_id: str, city: City, weekday: int | None = None) -> TypicalDay:
        """The lot's usual count through a day of `weekday` (default: today, Taipei time)."""
        today = self._clock.now().astimezone(TAIPEI).date()
        day = today.weekday() if weekday is None else weekday
        since = datetime(today.year, today.month, today.day, tzinfo=TAIPEI) - timedelta(
            weeks=TYPICAL_WEEKS + 1
        )
        return typical_day(
            self._history.availability_changes(lot_id, since),
            self._history.feed_polls(city, since),
            today,
            day,
        )
