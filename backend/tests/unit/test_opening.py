"""Open-now is worked out per request from the weekly schedule, and food is grouped for filters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from yimmparking.domain.food_category import FoodCategory, category_of
from yimmparking.domain.opening import MINUTES_PER_WEEK, OpeningPeriod, minutes_of, open_at

TAIPEI = timezone(timedelta(hours=8))
# 2026-10-11 is a Sunday; 2026-10-12 a Monday.
SUNDAY_NOON = datetime(2026, 10, 11, 12, 0, tzinfo=TAIPEI)
MONDAY_1030 = datetime(2026, 10, 12, 10, 30, tzinfo=TAIPEI)
MONDAY_1130 = datetime(2026, 10, 12, 11, 30, tzinfo=TAIPEI)
MONDAY_2200 = datetime(2026, 10, 12, 22, 0, tzinfo=TAIPEI)


class TestOpenAt:
    LUNCH_MONDAY = (OpeningPeriod(start=minutes_of(1, 11, 0), end=minutes_of(1, 21, 30)),)

    def test_open_inside_the_period(self) -> None:
        assert open_at(self.LUNCH_MONDAY, MONDAY_1130) is True

    def test_closed_outside_the_period(self) -> None:
        assert open_at(self.LUNCH_MONDAY, MONDAY_1030) is False
        assert open_at(self.LUNCH_MONDAY, MONDAY_2200) is False

    def test_closed_on_a_day_with_no_period(self) -> None:
        assert open_at(self.LUNCH_MONDAY, SUNDAY_NOON) is False

    def test_the_answer_is_the_same_in_utc(self) -> None:
        # 11:30 Taipei is 03:30 UTC on the same date.
        assert open_at(self.LUNCH_MONDAY, MONDAY_1130.astimezone(UTC)) is True

    def test_a_period_that_wraps_past_saturday_is_open_on_sunday_morning(self) -> None:
        late = (OpeningPeriod(start=minutes_of(6, 22, 0), end=MINUTES_PER_WEEK + 120),)
        sunday_0130 = datetime(2026, 10, 11, 1, 30, tzinfo=TAIPEI)
        assert open_at(late, sunday_0130) is True
        assert open_at(late, datetime(2026, 10, 11, 3, 0, tzinfo=TAIPEI)) is False

    def test_all_week_is_always_open(self) -> None:
        assert open_at((OpeningPeriod(start=0, end=MINUTES_PER_WEEK),), SUNDAY_NOON) is True

    def test_an_empty_schedule_is_never_open(self) -> None:
        assert open_at((), MONDAY_1130) is False


class TestCategory:
    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ("chinese_restaurant", FoodCategory.CHINESE),
            ("japanese_restaurant", FoodCategory.JAPANESE),
            ("sushi_restaurant", FoodCategory.JAPANESE),
            ("vietnamese_restaurant", FoodCategory.SOUTHEAST_ASIAN),
            ("thai_restaurant", FoodCategory.THAI),
            ("italian_restaurant", FoodCategory.WESTERN),
            ("seafood_restaurant", FoodCategory.SEAFOOD),
            ("cafe", FoodCategory.CAFE),
            ("restaurant", FoodCategory.OTHER),  # generic: not guessed
            ("a_type_we_have_not_seen", FoodCategory.OTHER),
            (None, FoodCategory.OTHER),
        ],
    )
    def test_primary_type_maps_to_a_filter_group(
        self, code: str | None, expected: FoodCategory
    ) -> None:
        assert category_of(code) is expected


class TestOpenNowIsAskedFresh:
    class FixedClock:
        def __init__(self, at: datetime) -> None:
            self.at = at

        def now(self) -> datetime:
            return self.at

    class Source:
        def __init__(self, periods: tuple[OpeningPeriod, ...] | None) -> None:
            self.periods = periods

        def nearby_food(self, center, radius_m, limit, min_rating=0.0, origin=None):  # type: ignore[no-untyped-def]
            from yimmparking.domain.geo import GeoPoint
            from yimmparking.domain.model import Place

            return [
                Place(
                    id="p1",
                    name="店",
                    location=GeoPoint(center.lat, center.lng),
                    rating=4.5,
                    user_rating_count=500,
                    opening=self.periods,
                )
            ]

    def test_the_same_cached_schedule_gives_different_answers_at_different_times(self) -> None:
        from yimmparking.application.search import SearchNearbyFood
        from yimmparking.domain.geo import GeoPoint

        lunch = (OpeningPeriod(start=minutes_of(1, 11, 0), end=minutes_of(1, 21, 30)),)
        center = GeoPoint(25.05, 121.55)

        at_night = SearchNearbyFood(self.Source(lunch), clock=self.FixedClock(MONDAY_2200)).execute(
            center
        )
        at_lunch = SearchNearbyFood(self.Source(lunch), clock=self.FixedClock(MONDAY_1130)).execute(
            center
        )

        assert at_night.hits[0].place.open_now is False
        assert at_lunch.hits[0].place.open_now is True

    def test_no_schedule_means_unknown_not_closed(self) -> None:
        from yimmparking.application.search import SearchNearbyFood
        from yimmparking.domain.geo import GeoPoint

        result = SearchNearbyFood(self.Source(None), clock=self.FixedClock(MONDAY_1130)).execute(
            GeoPoint(25.05, 121.55)
        )
        assert result.hits[0].place.open_now is None
