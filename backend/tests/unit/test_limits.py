from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.application.limits import (
    GEOCODING,
    PLACES_NEARBY,
    LimitedGeocoder,
    LimitedPlaces,
    UsageGate,
)
from yimmparking.application.ports import GeocodingError, QuotaExceeded
from yimmparking.application.search import ResolveAddress
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import GeocodeCandidate, Place

CENTER = GeoPoint(25.0375, 121.5637)


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now


class CountingGeocoder:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def geocode(self, query: str) -> list[GeocodeCandidate]:
        self.calls += 1
        if self.fail:
            raise GeocodingError("denied")
        return [GeocodeCandidate("addr", CENTER, "pid")]


class CountingPlaces:
    def __init__(self) -> None:
        self.calls = 0

    def nearby_food(
        self,
        center: GeoPoint,
        radius_m: int,
        limit: int,
        min_rating: float = 0.0,
        origin: GeoPoint | None = None,
    ) -> list[Place]:
        self.calls += 1
        return []


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime(2026, 10, 10, 12, 0, tzinfo=UTC))


@pytest.fixture
def store() -> SqliteStore:
    s = SqliteStore(":memory:")
    yield s  # type: ignore[misc]
    s.close()


class TestHardCeiling:
    def test_calls_up_to_the_limit_pass_and_the_next_is_refused_without_calling_out(
        self, store: SqliteStore, clock: MutableClock
    ) -> None:
        inner = CountingPlaces()
        places = LimitedPlaces(inner, UsageGate(store, clock, {PLACES_NEARBY: 3}))
        for _ in range(3):
            places.nearby_food(CENTER, 1000, 20)

        with pytest.raises(QuotaExceeded) as caught:
            places.nearby_food(CENTER, 1000, 20)

        assert inner.calls == 3  # the fourth never reached the provider
        assert caught.value.meter == PLACES_NEARBY
        assert caught.value.limit == 3

    def test_a_failed_provider_call_still_counts(
        self, store: SqliteStore, clock: MutableClock
    ) -> None:
        # The provider bills the request, not the outcome, so errors must not refund quota.
        inner = CountingGeocoder(fail=True)
        geocoder = LimitedGeocoder(inner, UsageGate(store, clock, {GEOCODING: 2}))
        for _ in range(2):
            with pytest.raises(GeocodingError):
                geocoder.geocode("x")
        with pytest.raises(QuotaExceeded):
            geocoder.geocode("x")
        assert inner.calls == 2

    def test_zero_limit_blocks_everything(self, store: SqliteStore, clock: MutableClock) -> None:
        inner = CountingPlaces()
        places = LimitedPlaces(inner, UsageGate(store, clock, {PLACES_NEARBY: 0}))
        with pytest.raises(QuotaExceeded):
            places.nearby_food(CENTER, 1000, 20)
        assert inner.calls == 0

    def test_meters_are_independent(self, store: SqliteStore, clock: MutableClock) -> None:
        gate = UsageGate(store, clock, {GEOCODING: 1, PLACES_NEARBY: 1})
        geo, plc = CountingGeocoder(), CountingPlaces()
        geocoder = LimitedGeocoder(geo, gate)
        places = LimitedPlaces(plc, gate)
        geocoder.geocode("a")
        places.nearby_food(CENTER, 1000, 20)  # unaffected by geocoding being at its limit
        assert gate.used(GEOCODING) == 1
        assert gate.used(PLACES_NEARBY) == 1


class TestPeriod:
    def test_count_resets_in_a_new_month(self, store: SqliteStore, clock: MutableClock) -> None:
        inner = CountingPlaces()
        places = LimitedPlaces(inner, UsageGate(store, clock, {PLACES_NEARBY: 1}))
        places.nearby_food(CENTER, 1000, 20)
        with pytest.raises(QuotaExceeded):
            places.nearby_food(CENTER, 1000, 20)

        clock.set(datetime(2026, 11, 1, 0, 5, tzinfo=UTC))
        places.nearby_food(CENTER, 1000, 20)
        assert inner.calls == 2

    def test_usage_is_durable_across_restarts(self, tmp_path: Path, clock: MutableClock) -> None:
        db = tmp_path / "usage.db"
        first = SqliteStore(db)
        LimitedPlaces(CountingPlaces(), UsageGate(first, clock, {PLACES_NEARBY: 2})).nearby_food(
            CENTER, 1000, 20
        )
        first.close()

        # A "restart": a brand-new store and gate over the same file must remember the count.
        second = SqliteStore(db)
        inner = CountingPlaces()
        places = LimitedPlaces(inner, UsageGate(second, clock, {PLACES_NEARBY: 2}))
        places.nearby_food(CENTER, 1000, 20)
        with pytest.raises(QuotaExceeded):
            places.nearby_food(CENTER, 1000, 20)
        assert inner.calls == 1
        second.close()


class TestCacheDoesNotSpendQuota:
    def test_repeat_address_is_free(self, store: SqliteStore, clock: MutableClock) -> None:
        inner = CountingGeocoder()
        gate = UsageGate(store, clock, {GEOCODING: 1})
        resolver = ResolveAddress(LimitedGeocoder(inner, gate), store, clock)

        resolver.execute("台北市信義區市府路1號")
        resolver.execute("臺北市 信義區 市府路1號")  # same address, different spelling

        assert inner.calls == 1
        assert gate.used(GEOCODING) == 1
