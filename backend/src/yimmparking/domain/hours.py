"""Opening hours from a lot's free-text service time, when it is a plain daily range.

Most lots write one of a few shapes ("00:00:00-24:00:00", "7~23時"). Anything with weekdays,
charging-hour notes or several sections is left unread rather than guessed at: a wrong "closed"
would send a driver elsewhere for nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

TAIPEI = timezone(timedelta(hours=8))
DAY = 24 * 60
CLOSING_SOON_MIN = 120

_NUM = r"(\d{1,2})"
_PATTERNS = [
    # 00:00:00-24:00:00, 7:00~23:30, 07:00 - 22:00
    re.compile(rf"^{_NUM}\s*:\s*(\d{{2}})(?::\d{{2}})?\s*[-~～至]\s*{_NUM}:(\d{{2}})(?::\d{{2}})?$"),
    # 7時30分~22時, 7時至23時30分
    re.compile(rf"^{_NUM}時(?:(\d{{1,2}})分)?\s*[-~～至]\s*{_NUM}時(?:(\d{{1,2}})分)?$"),
    # 7~23時, 0-24時
    re.compile(rf"^{_NUM}()\s*[-~～]\s*{_NUM}()時$"),
    # 22時至隔日6時, 22時至隔日凌晨6時, 22時至翌日6時
    re.compile(rf"^{_NUM}時()\s*至\s*(?:隔日|翌日)(?:凌晨)?{_NUM}時()$"),
]


@dataclass(frozen=True, slots=True)
class DailyHours:
    open_min: int  # minutes after local midnight
    close_min: int  # may be ≤ open_min: closes after midnight


def parse_daily(text: str) -> DailyHours | None:
    clean = text.strip().replace("：", ":").replace(" ", "")
    for pattern in _PATTERNS:
        match = pattern.match(clean)
        if not match:
            continue
        h1, m1, h2, m2 = match.groups()
        start = int(h1) * 60 + int(m1 or 0)
        end = int(h2) * 60 + int(m2 or 0)
        if not (0 <= start <= DAY and 0 <= end <= DAY):
            return None
        # "24:00", "23:59" and "0" as a closing time all mean the end of the day.
        if end == 0 or end >= DAY - 1:
            end = DAY
        return DailyHours(open_min=start % DAY, close_min=end)
    return None


class HoursStatus(StrEnum):
    ALWAYS = "always"  # open around the clock
    OPEN = "open"
    CLOSING_SOON = "closing_soon"  # closes within CLOSING_SOON_MIN
    CLOSED = "closed"
    UNKNOWN = "unknown"  # the text could not be read with confidence


@dataclass(frozen=True, slots=True)
class HoursNow:
    status: HoursStatus
    opens_at: str | None = None  # "07:00", when closed
    closes_at: str | None = None  # "23:00", when closing soon


def _clock(minute: int) -> str:
    minute %= DAY
    return f"{minute // 60:02d}:{minute % 60:02d}"


def hours_now(text: str, moment: datetime) -> HoursNow:
    hours = parse_daily(text)
    if hours is None:
        return HoursNow(HoursStatus.UNKNOWN)
    if hours.open_min == 0 and hours.close_min == DAY:
        return HoursNow(HoursStatus.ALWAYS)
    local = moment.astimezone(TAIPEI)
    now = local.hour * 60 + local.minute
    start, end = hours.open_min, hours.close_min
    if start < end:
        is_open = start <= now < end
        left = end - now
    else:  # overnight, e.g. 22:00 → 06:00
        is_open = now >= start or now < end
        left = (end - now) % DAY
    if not is_open:
        return HoursNow(HoursStatus.CLOSED, opens_at=_clock(start))
    if left <= CLOSING_SOON_MIN:
        return HoursNow(HoursStatus.CLOSING_SOON, closes_at=_clock(end))
    return HoursNow(HoursStatus.OPEN)
