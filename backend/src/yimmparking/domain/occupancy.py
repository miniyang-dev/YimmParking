"""What a lot's availability history says: where it is heading, how far to trust it, and what a
day usually looks like.

Pure functions over the stored history (see adapters/store/history.py):

- `changes`: `(at_s, count)` sorted by time, a row only when the count changed. The value at a
  moment is the last change at or before it; `None` is "no data".
- `polls`: sorted times at which the city's feed was actually read. A value only counts at a
  moment if the feed was read shortly before it, so a feed that stopped is never mistaken for a
  number that held steady.

Nothing here invents a number: when the history cannot answer, the answer is `None`.
"""

from __future__ import annotations

import bisect
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum

TAIPEI = timezone(timedelta(hours=8))

# A reading stands for the moments up to this long after the feed was read. Taipei publishes every
# few minutes and runs 4–7 minutes behind; New Taipei is read every 2 minutes.
COVER_S = 15 * 60

Change = tuple[int, int | None]


def value_at(changes: Sequence[Change], at_s: int) -> int | None:
    """The count in force at `at_s`; None when there was none (or it was "no data")."""
    index = bisect.bisect_right(changes, at_s, key=lambda c: c[0]) - 1
    return changes[index][1] if index >= 0 else None


def read_near(polls: Sequence[int], at_s: int) -> bool:
    """Whether the feed was read in the COVER_S before `at_s` (so a value there is a reading)."""
    index = bisect.bisect_right(polls, at_s) - 1
    return index >= 0 and at_s - polls[index] < COVER_S


# ---- trend -----------------------------------------------------------------------------------


class Direction(StrEnum):
    FILLING = "filling"
    EMPTYING = "emptying"
    STEADY = "steady"


@dataclass(frozen=True, slots=True)
class Trend:
    minutes: int  # the window compared
    delta: int  # spaces now minus spaces `minutes` ago; negative = filling up
    direction: Direction
    full_in_min: int | None  # at this pace, minutes until no space left (filling only, ≤ 2 h)


TREND_WINDOW_MIN = 30
TREND_MIN_DELTA = 3  # smaller moves are noise in a feed that reports whole spaces
FULL_FORECAST_MAX_MIN = 120  # further out than this, a straight-line guess means little


def trend(
    changes: Sequence[Change],
    polls: Sequence[int],
    now_s: int,
    current: int | None,
    window_min: int = TREND_WINDOW_MIN,
) -> Trend | None:
    """How the count moved over the last `window_min`, if the feed was read at both ends."""
    past_s = now_s - window_min * 60
    if current is None or not read_near(polls, now_s) or not read_near(polls, past_s):
        return None
    past = value_at(changes, past_s)
    if past is None:
        return None
    delta = current - past
    if delta <= -TREND_MIN_DELTA:
        direction = Direction.FILLING
    elif delta >= TREND_MIN_DELTA:
        direction = Direction.EMPTYING
    else:
        direction = Direction.STEADY
    full_in = None
    if direction is Direction.FILLING and current > 0:
        minutes = round(current / (-delta / window_min))
        full_in = minutes if minutes <= FULL_FORECAST_MAX_MIN else None
    return Trend(minutes=window_min, delta=delta, direction=direction, full_in_min=full_in)


# ---- reliability -----------------------------------------------------------------------------


class Doubt(StrEnum):
    FROZEN = "frozen"  # the number has not moved for days while the feed kept being read
    OVER_CAPACITY = "over_capacity"  # often above the lot's listed capacity
    OFTEN_MISSING = "often_missing"  # "no data" much of the time


RELIABILITY_DAYS = 7
FROZEN_AFTER_S = 48 * 3600
MIN_SAMPLES = 200  # about 7 hours of New Taipei polls: less than this is too little to judge


def doubts(
    changes: Sequence[Change],
    polls: Sequence[int],
    now_s: int,
    total_car: int | None,
    days: int = RELIABILITY_DAYS,
) -> list[Doubt]:
    """Reasons to treat this lot's number with care, judged from the readings of the last days."""
    start = bisect.bisect_left(polls, now_s - days * 86400)
    samples = [value_at(changes, p) for p in polls[start:] if p <= now_s]
    if len(samples) < MIN_SAMPLES:
        return []
    known = [s for s in samples if s is not None]
    found: list[Doubt] = []

    if known and len(known) < len(samples) / 2:
        found.append(Doubt.OFTEN_MISSING)
    if total_car and known and sum(1 for s in known if s > total_car) >= 0.2 * len(known):
        found.append(Doubt.OVER_CAPACITY)

    last_change = changes[-1][0] if changes else None
    feed_alive = read_near(polls, now_s)
    if (
        feed_alive
        and last_change is not None
        and changes[-1][1] is not None
        and now_s - last_change >= FROZEN_AFTER_S
        and polls
        and polls[0] <= now_s - FROZEN_AFTER_S
    ):
        found.append(Doubt.FROZEN)
    return found


# ---- typical day -----------------------------------------------------------------------------


SLOT_MIN = 30
TYPICAL_WEEKS = 8
MIN_WEEKS = 3  # a slot shows a typical value only when this many past days had a reading there


@dataclass(frozen=True, slots=True)
class Slot:
    minute: int  # minutes after local midnight
    median: float | None  # None: fewer than MIN_WEEKS readings at this time
    samples: int


@dataclass(frozen=True, slots=True)
class TypicalDay:
    weekday: int  # 0 = Monday … 6 = Sunday (Python's numbering)
    days_used: int  # past days of this weekday that had any reading
    slots: tuple[Slot, ...]


def past_days(today: date, weekday: int, weeks: int) -> list[date]:
    """The last `weeks` dates with this weekday, before `today` (today itself is still running)."""
    back = (today.weekday() - weekday) % 7 or 7
    first = today - timedelta(days=back)
    return [first - timedelta(weeks=i) for i in range(weeks)]


def typical_day(
    changes: Sequence[Change],
    polls: Sequence[int],
    today: date,
    weekday: int,
    weeks: int = TYPICAL_WEEKS,
) -> TypicalDay:
    """The median count at each half hour over the past `weeks` days of this weekday."""
    per_slot: list[list[int]] = [[] for _ in range(24 * 60 // SLOT_MIN)]
    days_used = 0
    for day in past_days(today, weekday, weeks):
        midnight = int(datetime(day.year, day.month, day.day, tzinfo=TAIPEI).timestamp())
        any_reading = False
        for index, bucket in enumerate(per_slot):
            at_s = midnight + index * SLOT_MIN * 60
            if not read_near(polls, at_s):
                continue
            value = value_at(changes, at_s)
            if value is not None:
                bucket.append(value)
                any_reading = True
        days_used += any_reading
    slots = tuple(
        Slot(
            minute=index * SLOT_MIN,
            median=float(statistics.median(bucket)) if len(bucket) >= MIN_WEEKS else None,
            samples=len(bucket),
        )
        for index, bucket in enumerate(per_slot)
    )
    return TypicalDay(weekday=weekday, days_used=days_used, slots=slots)
