"""Trend, doubts and the typical day, worked out from change-only history and feed polls."""

from __future__ import annotations

from datetime import UTC, date, datetime

from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.application.insights import LotInsights
from yimmparking.domain.model import AvailabilityBatch, AvailabilityReading, City
from yimmparking.domain.occupancy import (
    MIN_SAMPLES,
    TAIPEI,
    Direction,
    Doubt,
    past_days,
    read_near,
    trend,
    typical_day,
    value_at,
)

NOW = int(datetime(2026, 10, 22, 10, 0, tzinfo=UTC).timestamp())
MIN = 60


def polls_every(minutes: int, start: int, end: int) -> list[int]:
    return list(range(start, end + 1, minutes * MIN))


class TestReading:
    def test_the_value_in_force_is_the_last_change_at_or_before(self) -> None:
        changes = [(100, 5), (200, None), (300, 7)]
        assert [value_at(changes, t) for t in (50, 100, 250, 999)] == [None, 5, None, 7]

    def test_a_moment_counts_only_if_the_feed_was_read_shortly_before(self) -> None:
        polls = [1000, 1120]
        assert read_near(polls, 1120 + 14 * MIN)
        assert not read_near(polls, 1120 + 16 * MIN)  # the feed stopped
        assert not read_near(polls, 999)


class TestTrend:
    polls = polls_every(2, NOW - 60 * MIN, NOW)

    def test_filling_up_with_a_time_until_full(self) -> None:
        changes = [(NOW - 40 * MIN, 30), (NOW - 10 * MIN, 18)]
        t = trend(changes, self.polls, NOW, current=18)
        assert t is not None
        assert (t.delta, t.direction) == (-12, Direction.FILLING)
        assert t.full_in_min == 45  # 12 spaces in 30 min → 18 left in 45 min

    def test_small_moves_are_steady_and_say_nothing_about_full(self) -> None:
        t = trend([(NOW - 40 * MIN, 20)], self.polls, NOW, current=18)
        assert t is not None and t.direction is Direction.STEADY and t.full_in_min is None

    def test_emptying(self) -> None:
        t = trend([(NOW - 40 * MIN, 5)], self.polls, NOW, current=15)
        assert t is not None and t.direction is Direction.EMPTYING

    def test_a_far_off_full_is_not_forecast(self) -> None:
        t = trend([(NOW - 40 * MIN, 200)], self.polls, NOW, current=196)
        assert t is not None and t.direction is Direction.FILLING and t.full_in_min is None

    def test_no_trend_without_a_reading_at_both_ends(self) -> None:
        changes = [(NOW - 40 * MIN, 30)]
        assert trend(changes, self.polls, NOW, current=None) is None  # not live now
        late_polls = polls_every(2, NOW - 10 * MIN, NOW)  # feed came back 10 min ago
        assert trend(changes, late_polls, NOW, current=20) is None
        assert trend([(NOW - 5 * MIN, 9)], self.polls, NOW, current=9) is None  # no past value


class TestDoubts:
    week = polls_every(2, NOW - 7 * 86400, NOW)

    def doubts(self, changes: list[tuple[int, int | None]], total: int | None = 50) -> list[Doubt]:
        from yimmparking.domain.occupancy import doubts

        return doubts(changes, self.week, NOW, total)

    def test_a_number_that_moves_normally_raises_no_doubt(self) -> None:
        changes = [(t, 10 + (i % 5)) for i, t in enumerate(self.week[::30])]
        assert self.doubts(changes) == []

    def test_a_number_stuck_for_days_while_the_feed_runs_is_frozen(self) -> None:
        assert self.doubts([(NOW - 5 * 86400, 12)]) == [Doubt.FROZEN]

    def test_often_above_capacity(self) -> None:
        changes = [(NOW - 7 * 86400, 80), (NOW - 3600, 40), (NOW - 1800, 41)]
        assert Doubt.OVER_CAPACITY in self.doubts(changes, total=50)

    def test_often_without_data(self) -> None:
        changes = [(NOW - 7 * 86400, None), (NOW - 3600, 5), (NOW - 1800, 6)]
        assert self.doubts(changes) == [Doubt.OFTEN_MISSING]

    def test_too_little_history_judges_nothing(self) -> None:
        from yimmparking.domain.occupancy import doubts

        few = polls_every(2, NOW - (MIN_SAMPLES - 10) * 2 * MIN, NOW)
        assert doubts([(NOW - 5 * 86400, 12)], few, NOW, 50) == []


class TestTypicalDay:
    today = date(2026, 10, 22)  # a Thursday

    def test_past_days_are_the_same_weekday_before_today(self) -> None:
        assert past_days(self.today, 3, 2) == [date(2026, 10, 15), date(2026, 10, 8)]
        assert past_days(self.today, 4, 1) == [date(2026, 10, 16)]

    def history(self, weeks: int) -> tuple[list[tuple[int, int | None]], list[int]]:
        """`weeks` past Thursdays: 40 spaces at 08:00, 10 at 12:00, polled all day."""
        changes: list[tuple[int, int | None]] = []
        polls: list[int] = []
        for day in past_days(self.today, 3, weeks):
            midnight = int(datetime(day.year, day.month, day.day, tzinfo=TAIPEI).timestamp())
            changes += [(midnight + 8 * 3600, 40), (midnight + 12 * 3600, 10 + len(changes))]
            polls += polls_every(2, midnight, midnight + 86400 - 1)
        return sorted(changes), sorted(polls)

    def test_each_half_hour_is_the_median_of_the_past_days(self) -> None:
        changes, polls = self.history(weeks=3)
        day = typical_day(changes, polls, self.today, weekday=3)
        by_minute = {s.minute: s for s in day.slots}
        assert day.days_used == 3 and len(day.slots) == 48
        assert by_minute[9 * 60].median == 40
        assert by_minute[13 * 60].median == 12  # 10, 12, 14 on the three days
        assert by_minute[13 * 60].samples == 3

    def test_too_few_days_show_no_typical_value(self) -> None:
        changes, polls = self.history(weeks=2)
        day = typical_day(changes, polls, self.today, weekday=3)
        assert day.days_used == 2
        assert all(s.median is None for s in day.slots)

    def test_a_day_the_feed_was_down_does_not_count(self) -> None:
        changes, _ = self.history(weeks=3)
        day = typical_day(changes, [], self.today, weekday=3)
        assert day.days_used == 0


def test_insights_read_the_stored_history() -> None:
    store = SqliteStore(":memory:")
    for minutes_ago, count in ((60, 30), (40, 30), (20, 20), (0, 18)):
        at = datetime.fromtimestamp(NOW - minutes_ago * MIN, UTC)
        store.record_availability(
            AvailabilityBatch(City.TAIPEI, at, (AvailabilityReading("taipei:a", count),))
        )
    since = datetime.fromtimestamp(NOW - 30 * MIN, UTC)
    # The change in force at `since` (30 at 40 min ago) leads the series.
    assert store.availability_changes("taipei:a", since) == [
        (NOW - 60 * MIN, 30),
        (NOW - 20 * MIN, 20),
        (NOW, 18),
    ]
    assert store.feed_polls(City.TAIPEI, since) == [NOW - 20 * MIN, NOW]

    class Clock:
        def now(self) -> datetime:
            return datetime.fromtimestamp(NOW, UTC)

    day = LotInsights(store, Clock()).typical("taipei:a", City.TAIPEI)
    assert day.weekday == 3 and day.days_used == 0  # no past Thursday yet
    store.close()
