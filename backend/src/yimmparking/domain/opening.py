"""Opening hours as a weekly schedule, so "open now" is worked out when it is asked for.

A cached snapshot of "open now" goes stale within hours (a place cached at night still reads as
closed at lunch), so only the weekly schedule is kept and the answer is computed per request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

MINUTES_PER_DAY = 24 * 60
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY
# Places in Taiwan are on Taipei time all year; the schedule is local, not UTC.
LOCAL_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True, slots=True)
class OpeningPeriod:
    """One open stretch in a week, in minutes from Sunday 00:00 local time.

    `end` may exceed a week: a period that runs past Saturday midnight wraps to the next Sunday.
    """

    start: int
    end: int


def minutes_of(day: int, hour: int, minute: int) -> int:
    """Google numbers days from Sunday (0) to Saturday (6)."""
    return day * MINUTES_PER_DAY + hour * 60 + minute


def open_at(periods: tuple[OpeningPeriod, ...], moment: datetime) -> bool:
    """Whether the place is open at `moment` (timezone-aware)."""
    local = moment.astimezone(LOCAL_TZ)
    sunday_based_weekday = (local.weekday() + 1) % 7
    now = minutes_of(sunday_based_weekday, local.hour, local.minute)
    return any(p.start <= now < p.end or p.start <= now + MINUTES_PER_WEEK < p.end for p in periods)
