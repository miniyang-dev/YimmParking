from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.application.limits import PLACES_NEARBY, LimitedPlaces, UsageGate
from yimmparking.application.place_cache import CachedPlaces
from yimmparking.application.ports import PlacesError
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import Place
from yimmparking.domain.opening import MINUTES_PER_WEEK, OpeningPeriod

LOT_A = GeoPoint(25.0375, 121.5637)
LOT_B = GeoPoint(25.0390, 121.5650)
TTL = timedelta(hours=24)


class Clock:
    def __init__(self) -> None:
        self.at = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.at


class Provider:
    def __init__(self, places: list[Place] | None = None, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail
        self.places = (
            places
            if places is not None
            else [
                Place(
                    id="p1",
                    name="牛肉麵",
                    location=GeoPoint(25.0378, 121.5640),
                    address="台北市某路",
                    rating=4.6,
                    user_rating_count=1200,
                    price_level="MODERATE",
                    primary_type="麵食",
                    primary_type_code="chinese_restaurant",
                    opening=(OpeningPeriod(start=0, end=MINUTES_PER_WEEK),),
                    maps_uri="https://maps.google.com/?cid=1",
                )
            ]
        )

    def nearby_food(
        self,
        center: GeoPoint,
        radius_m: int,
        limit: int,
        min_rating: float = 0.0,
        origin: GeoPoint | None = None,
    ) -> list[Place]:
        self.calls += 1
        time.sleep(0.01)  # widen the window for the concurrency test
        if self.fail:
            raise PlacesError("boom")
        return self.places


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store() -> SqliteStore:
    s = SqliteStore(":memory:")
    yield s  # type: ignore[misc]
    s.close()


class TestCacheBehaviour:
    def test_a_repeated_lookup_is_served_without_calling_the_provider(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        provider = Provider()
        cached = CachedPlaces(provider, store, clock, TTL)

        first = cached.nearby_food(LOT_A, 1000, 20, 4.0)
        second = cached.nearby_food(LOT_A, 1000, 20, 4.0)

        assert provider.calls == 1
        assert second == first  # every field survives the round trip through storage

    def test_open_now_is_never_stored(self, store: SqliteStore, clock: Clock) -> None:
        # A snapshot of "open now" goes stale within hours, so only the schedule is cached.
        provider = Provider()
        cached = CachedPlaces(provider, store, clock, TTL)
        [place] = cached.nearby_food(LOT_A, 1000, 20, 4.0)
        assert place.open_now is None

    def test_a_different_lot_is_a_different_lookup(self, store: SqliteStore, clock: Clock) -> None:
        provider = Provider()
        cached = CachedPlaces(provider, store, clock, TTL)
        cached.nearby_food(LOT_A, 1000, 20, 4.0)
        cached.nearby_food(LOT_B, 1000, 20, 4.0)
        assert provider.calls == 2

    def test_a_different_rating_floor_is_a_different_lookup(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        provider = Provider()
        cached = CachedPlaces(provider, store, clock, TTL)
        cached.nearby_food(LOT_A, 1000, 20, 4.0)
        cached.nearby_food(LOT_A, 1000, 20, 4.5)
        assert provider.calls == 2

    def test_entry_expires_after_the_ttl(self, store: SqliteStore, clock: Clock) -> None:
        provider = Provider()
        cached = CachedPlaces(provider, store, clock, TTL)
        cached.nearby_food(LOT_A, 1000, 20, 4.0)

        clock.at += TTL - timedelta(minutes=1)
        cached.nearby_food(LOT_A, 1000, 20, 4.0)
        assert provider.calls == 1

        clock.at += timedelta(minutes=2)
        cached.nearby_food(LOT_A, 1000, 20, 4.0)
        assert provider.calls == 2

    def test_an_empty_answer_is_cached_because_it_was_billed(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        provider = Provider([])
        cached = CachedPlaces(provider, store, clock, TTL)
        assert cached.nearby_food(LOT_A, 1000, 20, 4.0) == []
        assert cached.nearby_food(LOT_A, 1000, 20, 4.0) == []
        assert provider.calls == 1

    def test_errors_are_never_cached(self, store: SqliteStore, clock: Clock) -> None:
        provider = Provider(fail=True)
        cached = CachedPlaces(provider, store, clock, TTL)
        for _ in range(2):
            with pytest.raises(PlacesError):
                cached.nearby_food(LOT_A, 1000, 20, 4.0)
        assert provider.calls == 2

        provider.fail = False
        assert cached.nearby_food(LOT_A, 1000, 20, 4.0)
        assert provider.calls == 3

    def test_survives_a_restart(self, tmp_path: Path, clock: Clock) -> None:
        db = tmp_path / "cache.db"
        first = SqliteStore(db)
        CachedPlaces(Provider(), first, clock, TTL).nearby_food(LOT_A, 1000, 20, 4.0)
        first.close()

        second = SqliteStore(db)
        provider = Provider()
        CachedPlaces(provider, second, clock, TTL).nearby_food(LOT_A, 1000, 20, 4.0)
        assert provider.calls == 0
        second.close()

    def test_purge_removes_only_expired_entries(self, store: SqliteStore, clock: Clock) -> None:
        cached = CachedPlaces(Provider(), store, clock, TTL)
        cached.nearby_food(LOT_A, 1000, 20, 4.0)
        clock.at += timedelta(hours=12)
        cached.nearby_food(LOT_B, 1000, 20, 4.0)

        clock.at += timedelta(hours=13)  # A is now 25h old, B is 13h old
        assert store.purge_expired_places(clock.now()) == 1
        assert store.get_places("food|25.03900|121.56500|1000|20|4.0|-", clock.now()) is not None


class TestConcurrencyAndQuota:
    def test_simultaneous_identical_lookups_are_billed_once(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        provider = Provider()
        cached = CachedPlaces(provider, store, clock, TTL)
        results: list[list[Place]] = []

        def work() -> None:
            results.append(cached.nearby_food(LOT_A, 1000, 20, 4.0))

        threads = [threading.Thread(target=work) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert provider.calls == 1
        assert len(results) == 6

    def test_cache_hits_spend_no_quota(self, store: SqliteStore, clock: Clock) -> None:
        provider = Provider()
        gate = UsageGate(store, clock, {PLACES_NEARBY: 5})
        # The cache sits outside the limiter, as in the real wiring.
        cached = CachedPlaces(LimitedPlaces(provider, gate), store, clock, TTL)

        for _ in range(4):
            cached.nearby_food(LOT_A, 1000, 20, 4.0)

        assert provider.calls == 1
        assert gate.used(PLACES_NEARBY) == 1
