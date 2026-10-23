"""A city's feed whose real-time counts fall back to a second source when its own stop moving.

臺北市's feed once kept answering with the same UPDATETIME for days: every fetch "succeeded" and
every lot of the city read as no data. A count that is current is worth more than whose it is, so
while the city's own reading is too old (or cannot be read) the backup's is taken, marked with
its source; as soon as the city's own feed moves again it is used again.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from yimmparking.application.ports import AvailabilityFeed, Clock, ParkingFeed, SourceError
from yimmparking.domain.model import AvailabilityBatch, ParkingLot

log = logging.getLogger(__name__)

# The Taipei feed runs 4–7 minutes behind when healthy; past this it has stopped.
PRIMARY_MAX_AGE = timedelta(minutes=30)
# The backup is metered (TDX: 3 free points a month, about 0.001 per call): read it at most this
# often, and serve its last answer in between. 30 minutes is about 1.5 points a month. TDX's own
# Taipei data changes only about every 35 minutes (seen 2026-10-23), so a reading is up to ~65
# minutes old just before the next read; much longer and it would often count as expired.
BACKUP_INTERVAL = timedelta(minutes=30)
# How often TDX's Taipei off-street data itself changes (observed: every 34–36 minutes).
TDX_TAIPEI_CADENCE = timedelta(minutes=35)


class FallbackFeed:
    """Static lots always from `primary`; counts from `primary` while current, else `backup`."""

    def __init__(
        self,
        primary: ParkingFeed,
        backup: AvailabilityFeed,
        clock: Clock,
        max_age: timedelta = PRIMARY_MAX_AGE,
        backup_interval: timedelta = BACKUP_INTERVAL,
    ) -> None:
        if primary.city is not backup.city:
            raise ValueError("a fallback must be for the same city")
        self.city = primary.city
        self._primary, self._backup = primary, backup
        self._clock, self._max_age = clock, max_age
        self._backup_interval = backup_interval
        self._last_backup: tuple[datetime, AvailabilityBatch] | None = None
        self._on_backup = False

    def fetch_lots(self) -> list[ParkingLot]:
        return self._primary.fetch_lots()

    def fetch_availability(self) -> AvailabilityBatch:
        primary: AvailabilityBatch | None = None
        problem: str
        try:
            primary = self._primary.fetch_availability()
            age = self._clock.now() - primary.observed_at
            if age <= self._max_age:
                if self._on_backup:
                    log.warning("%s: own feed is current again, leaving the backup", self.city)
                    self._on_backup = False
                return primary
            problem = f"own feed stuck at {primary.observed_at.isoformat()} ({age} old)"
        except SourceError as exc:
            problem = f"own feed failed: {exc}"

        now = self._clock.now()
        if self._last_backup and now - self._last_backup[0] < self._backup_interval:
            return self._last_backup[1]  # recorded already: adds nothing, costs nothing
        try:
            backup = self._backup.fetch_availability()
            self._last_backup = (now, backup)
        except SourceError as exc:
            if primary is not None:
                return primary  # old, but the newest there is; freshness rules will hide it
            raise SourceError(f"{problem}; backup failed too: {exc}") from exc
        if not self._on_backup:
            log.warning("%s: %s, using %s", self.city, problem, backup.source)
            self._on_backup = True
        return backup
