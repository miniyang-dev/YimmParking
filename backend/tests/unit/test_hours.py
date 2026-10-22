"""Opening hours read from the service-time text, only when it is a plain daily range."""

from __future__ import annotations

from datetime import datetime

import pytest

from yimmparking.domain.hours import TAIPEI, DailyHours, HoursStatus, hours_now, parse_daily


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("00:00:00-24:00:00", DailyHours(0, 1440)),
        ("0~24時", DailyHours(0, 1440)),
        ("00:00:00-23:59:59", DailyHours(0, 1440)),
        ("07:00:00-23:00:00", DailyHours(420, 1380)),
        ("7~23時", DailyHours(420, 1380)),
        ("7時30分~22時", DailyHours(450, 1320)),
        ("8時至22時", DailyHours(480, 1320)),
        ("07:00 :00-21:30:00", DailyHours(420, 1290)),
        ("22時至隔日凌晨6時", DailyHours(1320, 360)),
        ("22時至翌日6時", DailyHours(1320, 360)),
    ],
)
def test_plain_daily_ranges_are_read(text: str, expected: DailyHours) -> None:
    assert parse_daily(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "週一至週六 9時至17時",  # weekdays: not a daily range
        "收費日：星期一至星期日，收費時間：09-17",  # charging hours, not opening hours
        "每日不逾8小時，每月不逾240小時",
        "臨停：7時至23時；月租：24小時",
        "25~26時",
    ],
)
def test_anything_else_is_left_unread(text: str) -> None:
    assert parse_daily(text) is None


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 22, hour, minute, tzinfo=TAIPEI)


def test_status_through_the_day() -> None:
    assert hours_now("0~24時", at(3)).status is HoursStatus.ALWAYS
    assert hours_now("7~23時", at(12)).status is HoursStatus.OPEN
    soon = hours_now("7~23時", at(21, 30))
    assert (soon.status, soon.closes_at) == (HoursStatus.CLOSING_SOON, "23:00")
    closed = hours_now("7~23時", at(23, 10))
    assert (closed.status, closed.opens_at) == (HoursStatus.CLOSED, "07:00")
    assert hours_now("週一至週六 9時至17時", at(12)).status is HoursStatus.UNKNOWN


def test_overnight_hours() -> None:
    assert hours_now("22時至隔日6時", at(23)).status is HoursStatus.OPEN
    soon = hours_now("22時至隔日6時", at(5))
    assert (soon.status, soon.closes_at) == (HoursStatus.CLOSING_SOON, "06:00")
    closed = hours_now("22時至隔日6時", at(12))
    assert (closed.status, closed.opens_at) == (HoursStatus.CLOSED, "22:00")


def test_the_time_is_read_in_taipei_whatever_zone_the_server_uses() -> None:
    from datetime import UTC

    late = datetime(2026, 10, 22, 15, 10, tzinfo=UTC)  # 23:10 in Taipei
    assert hours_now("7~23時", late).status is HoursStatus.CLOSED
