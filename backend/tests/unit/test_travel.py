"""Travel time: routing adapter, cache, quota, the parking search with a shortlist, and food."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from yimmparking.adapters.places.google_places import GooglePlaces
from yimmparking.adapters.routes.google_routes import GoogleRoutes
from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.application.limits import ROUTES_ELEMENTS, LimitedRouter, UsageGate
from yimmparking.application.ports import QuotaExceeded, RoutesError
from yimmparking.application.route_cache import CachedRouter, route_key
from yimmparking.application.search import (
    SearchNearbyFood,
    SearchNearbyParking,
    WalkingStatus,
)
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import Brand, City, ParkingLot, Place, RouteTime, TravelMode
from yimmparking.domain.ranking import Block, RankingPolicy, SortMode
from yimmparking.domain.vendor import Preference, Vendor, VendorPick

ORIGIN = GeoPoint(25.0507, 121.5501)
T0 = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
ClientFactory = Callable[[Callable[[httpx.Request], httpx.Response]], httpx.Client]
WALK, BIKE = TravelMode.WALK, TravelMode.BICYCLE


class Clock:
    def __init__(self) -> None:
        self.at = T0

    def now(self) -> datetime:
        return self.at


class FakeRouter:
    """Fixed walking seconds per destination id; other modes are a third of that."""

    def __init__(self, times: dict[str, int | None], *, fail: Exception | None = None) -> None:
        self.times = times
        self.fail = fail
        self.asked: list[tuple[TravelMode, list[str]]] = []

    def travel_times(
        self, origin: GeoPoint, destinations: list[tuple[str, GeoPoint]], mode: TravelMode
    ) -> dict[str, RouteTime | None]:
        if self.fail:
            raise self.fail
        ids = [d for d, _ in destinations]
        self.asked.append((mode, ids))
        divisor = 1 if mode is WALK else 3
        return {
            d: (RouteTime(self.times[d] // divisor, 100) if self.times.get(d) else None)
            for d in ids
        }


class BlockingRouter(FakeRouter):
    """Holds every call inside the router until `release` is set."""

    def __init__(self, times: dict[str, int | None]) -> None:
        super().__init__(times)
        self.entered = threading.Event()
        self.release = threading.Event()
        self._calls = 0
        self._counted = threading.Condition()

    def travel_times(
        self, origin: GeoPoint, destinations: list[tuple[str, GeoPoint]], mode: TravelMode
    ) -> dict[str, RouteTime | None]:
        with self._counted:
            self._calls += 1
            self._counted.notify_all()
        self.entered.set()
        self.release.wait(5)
        return super().travel_times(origin, destinations, mode)

    def wait_for_calls(self, n: int) -> bool:
        with self._counted:
            return self._counted.wait_for(lambda: self._calls >= n, timeout=5)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store() -> SqliteStore:
    s = SqliteStore(":memory:")
    yield s  # type: ignore[misc]
    s.close()


# --------------------------------------------------------------------------- the adapter
class TestGoogleRoutes:
    DESTS = [
        ("lot:a", GeoPoint(25.051, 121.551)),
        ("lot:b", GeoPoint(25.049, 121.548)),
        ("lot:c", GeoPoint(25.060, 121.560)),
    ]

    def test_missing_key_raises(self, make_client: ClientFactory) -> None:
        router = GoogleRoutes(make_client(lambda r: httpx.Response(500)), api_key=None)
        with pytest.raises(RoutesError):
            router.travel_times(ORIGIN, self.DESTS, WALK)

    @pytest.mark.parametrize("mode", [WALK, BIKE])
    def test_one_request_with_the_requested_mode_and_a_small_field_mask(
        self, make_client: ClientFactory, mode: TravelMode
    ) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=[])

        GoogleRoutes(make_client(handler), "k").travel_times(ORIGIN, self.DESTS, mode)

        assert len(seen) == 1  # batch: one request for all destinations
        body = json.loads(seen[0].content)
        assert body["travelMode"] == mode.value
        assert len(body["origins"]) == 1
        assert len(body["destinations"]) == 3
        mask = seen[0].headers["X-Goog-FieldMask"]
        assert "duration" in mask and "distanceMeters" in mask
        assert "polyline" not in mask  # nothing that would move it to a pricier tier

    def test_parses_each_element_by_destination_index(self, make_client: ClientFactory) -> None:
        payload = [
            {
                "originIndex": 0,
                "destinationIndex": 1,
                "duration": "420s",
                "distanceMeters": 510,
                "status": {},
                "condition": "ROUTE_EXISTS",
            },
            {
                "originIndex": 0,
                "destinationIndex": 0,
                "duration": "1039s",
                "distanceMeters": 1219,
                "status": {},
                "condition": "ROUTE_EXISTS",
            },
        ]
        router = GoogleRoutes(make_client(lambda r: httpx.Response(200, json=payload)), "k")
        out = router.travel_times(ORIGIN, self.DESTS, WALK)

        assert out["lot:a"] == RouteTime(seconds=1039, meters=1219)
        assert out["lot:b"] == RouteTime(seconds=420, meters=510)
        assert out["lot:c"] is None  # absent from the answer: no time is invented

    def test_a_pair_that_cannot_be_routed_is_none_not_zero(
        self, make_client: ClientFactory
    ) -> None:
        payload = [
            {"originIndex": 0, "destinationIndex": 0, "condition": "ROUTE_NOT_FOUND"},
            {
                "originIndex": 0,
                "destinationIndex": 1,
                "status": {"code": 5},
                "condition": "ROUTE_NOT_FOUND",
            },
        ]
        router = GoogleRoutes(make_client(lambda r: httpx.Response(200, json=payload)), "k")
        out = router.travel_times(ORIGIN, self.DESTS, BIKE)
        assert out["lot:a"] is None and out["lot:b"] is None

    def test_http_error_is_a_routes_error(self, make_client: ClientFactory) -> None:
        router = GoogleRoutes(make_client(lambda r: httpx.Response(403)), "k")
        with pytest.raises(RoutesError, match="403"):
            router.travel_times(ORIGIN, self.DESTS, WALK)

    def test_no_destinations_makes_no_request(self, make_client: ClientFactory) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise AssertionError("must not be called")

        assert GoogleRoutes(make_client(boom), "k").travel_times(ORIGIN, [], WALK) == {}


# --------------------------------------------------------------------------- quota by element
class TestElementQuota:
    def test_quota_counts_destinations_not_requests(self, store: SqliteStore, clock: Clock) -> None:
        gate = UsageGate(store, clock, {ROUTES_ELEMENTS: 10})
        router = LimitedRouter(FakeRouter({"a": 60, "b": 60, "c": 60}), gate)
        dests = [(i, ORIGIN) for i in ("a", "b", "c")]

        router.travel_times(ORIGIN, dests, WALK)  # 3 elements
        router.travel_times(ORIGIN, dests, BIKE)  # 6: a second mode is billed again
        router.travel_times(ORIGIN, dests, WALK)  # 9
        assert gate.used(ROUTES_ELEMENTS) == 9

        with pytest.raises(QuotaExceeded):
            router.travel_times(ORIGIN, dests, WALK)  # would be 12 > 10: refused whole
        assert gate.used(ROUTES_ELEMENTS) == 9  # nothing was consumed by the refused request

    def test_a_request_that_does_not_fit_is_not_sent(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        inner = FakeRouter({"a": 60})
        router = LimitedRouter(inner, UsageGate(store, clock, {ROUTES_ELEMENTS: 2}))
        with pytest.raises(QuotaExceeded):
            router.travel_times(ORIGIN, [(i, ORIGIN) for i in ("a", "b", "c")], WALK)
        assert inner.asked == []


# --------------------------------------------------------------------------- the cache
class TestRouteCache:
    TTL = timedelta(days=30)

    def build(
        self, store: SqliteStore, clock: Clock, inner: FakeRouter, limit: int = 100
    ) -> tuple[CachedRouter, UsageGate]:
        gate = UsageGate(store, clock, {ROUTES_ELEMENTS: limit})
        return CachedRouter(LimitedRouter(inner, gate), store, clock, self.TTL), gate

    def test_only_missing_pairs_are_sent_and_billed(self, store: SqliteStore, clock: Clock) -> None:
        inner = FakeRouter({"a": 100, "b": 200, "c": 300})
        router, gate = self.build(store, clock, inner)

        router.travel_times(ORIGIN, [("a", ORIGIN), ("b", ORIGIN)], WALK)
        out = router.travel_times(ORIGIN, [("a", ORIGIN), ("b", ORIGIN), ("c", ORIGIN)], WALK)

        assert inner.asked == [(WALK, ["a", "b"]), (WALK, ["c"])]
        assert gate.used(ROUTES_ELEMENTS) == 3
        assert out["a"] == RouteTime(100, 100)
        assert out["c"] == RouteTime(300, 100)

    def test_each_travel_mode_has_its_own_entry(self, store: SqliteStore, clock: Clock) -> None:
        inner = FakeRouter({"a": 600})
        router, _ = self.build(store, clock, inner)
        walk = router.travel_times(ORIGIN, [("a", ORIGIN)], WALK)["a"]
        ride = router.travel_times(ORIGIN, [("a", ORIGIN)], BIKE)["a"]
        assert walk == RouteTime(600, 100) and ride == RouteTime(200, 100)
        assert router.travel_times(ORIGIN, [("a", ORIGIN)], BIKE)["a"] == ride  # served from cache
        assert [m for m, _ in inner.asked] == [WALK, BIKE]
        assert route_key(ORIGIN, "a", WALK) != route_key(ORIGIN, "a", BIKE)

    def test_fully_cached_search_makes_no_request_and_spends_nothing(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        inner = FakeRouter({"a": 100})
        router, gate = self.build(store, clock, inner)
        for _ in range(4):
            router.travel_times(ORIGIN, [("a", ORIGIN)], WALK)
        assert len(inner.asked) == 1
        assert gate.used(ROUTES_ELEMENTS) == 1

    def test_a_slightly_different_origin_inside_11_m_reuses_the_entry(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        inner = FakeRouter({"a": 100})
        router, _ = self.build(store, clock, inner)
        router.travel_times(GeoPoint(25.05070, 121.55010), [("a", ORIGIN)], WALK)
        router.travel_times(GeoPoint(25.05072, 121.55012), [("a", ORIGIN)], WALK)
        assert len(inner.asked) == 1

    def test_a_different_origin_is_a_different_entry(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        inner = FakeRouter({"a": 100})
        router, _ = self.build(store, clock, inner)
        router.travel_times(ORIGIN, [("a", ORIGIN)], WALK)
        router.travel_times(GeoPoint(25.0600, 121.5600), [("a", ORIGIN)], WALK)
        assert len(inner.asked) == 2

    def test_entries_expire(self, store: SqliteStore, clock: Clock) -> None:
        inner = FakeRouter({"a": 100})
        router, _ = self.build(store, clock, inner)
        router.travel_times(ORIGIN, [("a", ORIGIN)], WALK)

        clock.at += self.TTL - timedelta(hours=1)
        router.travel_times(ORIGIN, [("a", ORIGIN)], WALK)
        assert len(inner.asked) == 1

        clock.at += timedelta(hours=2)
        router.travel_times(ORIGIN, [("a", ORIGIN)], WALK)
        assert len(inner.asked) == 2

    def test_no_route_is_cached_because_it_was_billed(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        inner = FakeRouter({"a": None})
        router, gate = self.build(store, clock, inner)
        assert router.travel_times(ORIGIN, [("a", ORIGIN)], WALK) == {"a": None}
        assert router.travel_times(ORIGIN, [("a", ORIGIN)], WALK) == {"a": None}
        assert len(inner.asked) == 1
        assert gate.used(ROUTES_ELEMENTS) == 1

    def test_errors_are_not_cached(self, store: SqliteStore, clock: Clock) -> None:
        inner = FakeRouter({"a": 100}, fail=RoutesError("down"))
        router, _ = self.build(store, clock, inner)
        with pytest.raises(RoutesError):
            router.travel_times(ORIGIN, [("a", ORIGIN)], WALK)
        inner.fail = None
        assert router.travel_times(ORIGIN, [("a", ORIGIN)], WALK)["a"] == RouteTime(100, 100)

    def test_a_search_elsewhere_does_not_wait_for_a_slow_router_call(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        inner = BlockingRouter({"a": 100})
        router, _ = self.build(store, clock, inner)
        first = threading.Thread(
            target=router.travel_times, args=(ORIGIN, [("a", ORIGIN)], WALK)
        )
        first.start()
        assert inner.entered.wait(5)  # the first call is now inside the router, blocked

        elsewhere = threading.Thread(
            target=router.travel_times, args=(GeoPoint(25.0600, 121.5600), [("a", ORIGIN)], WALK)
        )
        elsewhere.start()
        # The second origin reaches the router while the first call is still in flight.
        assert inner.wait_for_calls(2)
        inner.release.set()
        first.join(5)
        elsewhere.join(5)

    def test_identical_searches_at_once_are_billed_once(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        inner = BlockingRouter({"a": 100})
        router, gate = self.build(store, clock, inner)
        results: list[dict[str, RouteTime | None]] = []

        def search() -> None:
            results.append(router.travel_times(ORIGIN, [("a", ORIGIN)], WALK))

        threads = [threading.Thread(target=search) for _ in range(4)]
        for t in threads:
            t.start()
        assert inner.entered.wait(5)
        inner.release.set()
        for t in threads:
            t.join(5)

        assert len(inner.asked) == 1
        assert gate.used(ROUTES_ELEMENTS) == 1
        assert results == [{"a": RouteTime(100, 100)}] * 4

    def test_purge_removes_expired_entries(self, store: SqliteStore, clock: Clock) -> None:
        inner = FakeRouter({"a": 100})
        router, _ = self.build(store, clock, inner)
        router.travel_times(ORIGIN, [("a", ORIGIN)], WALK)
        key = route_key(ORIGIN, "a", WALK)
        assert store.get_routes([key], clock.now())
        later = clock.now() + self.TTL + timedelta(seconds=1)
        assert store.purge_expired_routes(later) == 1
        assert store.get_routes([key], later) == {}


# --------------------------------------------------------------------------- the parking search
def lot(
    source_id: str, lat: float, *, brand: Brand = Brand.OTHER, iparking: str | None = None
) -> ParkingLot:
    return ParkingLot(
        id=f"taipei:{source_id}",
        city=City.TAIPEI,
        source_id=source_id,
        name=source_id,
        address="",
        district="",
        location=GeoPoint(lat, ORIGIN.lng),
        total_car=100,
        brand=brand,
        iparking_code=iparking,
    )


def seed(store: SqliteStore, lots: list[ParkingLot]) -> None:
    store.replace_lots(City.TAIPEI, lots)


def pref(*shows: tuple[Vendor, int]) -> Preference:
    return Preference.from_picks(VendorPick(vendor, show) for vendor, show in shows)


class TestParkingSearchWithTravelTimes:
    def lots(self) -> list[ParkingLot]:
        # ~11 m per 0.0001 degree of latitude: 4 嘟嘟房 lots and 14 ordinary lots, all in range
        return [
            lot("b1", 25.0560, brand=Brand.DODOHOME),
            lot("b2", 25.0555, brand=Brand.DODOHOME),
            lot("b3", 25.0550, brand=Brand.DODOHOME),
            lot("b4", 25.0545, brand=Brand.DODOHOME),
            *[lot(f"o{i:02d}", 25.0508 + i * 0.0003) for i in range(14)],
        ]

    @staticmethod
    def times(*ids: str) -> dict[str, int]:
        return {f"taipei:{i}": 300 + 10 * n for n, i in enumerate(ids)}

    def test_pool_is_every_lot_in_range_and_the_list_is_capped(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        seed(store, self.lots())
        result = SearchNearbyParking(store, clock, router=FakeRouter({})).execute(
            ORIGIN, RankingPolicy()
        )
        assert result.pool_size == 18
        # Defaults show 2 嘟嘟房 in the first section; the other 2 plus 14 ordinary lots share the
        # 8-lot section below it.
        assert len(result.hits) == 2 + 8
        assert [h.ranked.block for h in result.hits] == [Block.PRIORITY] * 2 + [Block.OTHER] * 8

    def test_only_the_shortlist_is_routed_and_billed_in_one_walking_request(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        seed(store, self.lots())
        router = FakeRouter({})
        SearchNearbyParking(store, clock, router=router).execute(ORIGIN, RankingPolicy())

        assert [m for m, _ in router.asked] == [WALK]  # no cycling request any more
        routed = router.asked[0][1]
        assert len(routed) == 8
        # Two 嘟嘟房 (the nearest), then the nearest of the rest.
        assert routed[:2] == ["taipei:b4", "taipei:b3"]

    def test_the_section_shows_the_configured_number_of_each_vendor(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        seed(store, self.lots())
        policy = RankingPolicy(preference=pref((Vendor.DODOHOME, 3)))
        result = SearchNearbyParking(store, clock, router=FakeRouter({})).execute(ORIGIN, policy)
        priority = [h for h in result.hits if h.ranked.block is Block.PRIORITY]
        assert [h.ranked.lot.source_id for h in priority] == ["b4", "b3", "b2"]
        assert all(h.ranked.vendor is Vendor.DODOHOME for h in priority)

    def test_the_priority_section_lists_routed_lots_first_by_walking_time(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        seed(store, self.lots())
        times = {"taipei:b3": 300, "taipei:b4": 900}
        result = SearchNearbyParking(store, clock, router=FakeRouter(times)).execute(
            ORIGIN, RankingPolicy()
        )
        priority = [h.ranked for h in result.hits if h.ranked.block is Block.PRIORITY]
        assert [r.lot.source_id for r in priority] == ["b3", "b4"]  # by time, not distance
        assert priority[0].walking == RouteTime(300, 100)

    def test_lots_without_a_time_carry_none_and_sort_after_those_with_one(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        seed(store, self.lots())
        result = SearchNearbyParking(store, clock, router=FakeRouter({"taipei:o00": 100})).execute(
            ORIGIN, RankingPolicy()
        )
        other = [h.ranked for h in result.hits if h.ranked.block is Block.OTHER]
        assert other[0].lot.source_id == "o00"  # the only routed lot leads its section
        assert all(r.walking is None for r in other[1:])  # never invented

    def test_walking_only_mode_is_one_list_capped_at_twenty(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        seed(store, self.lots())
        # Only the nearest 8 lots are routed in this mode, so the routed ones are o00..o07.
        times = self.times("o03", "o00")
        result = SearchNearbyParking(store, clock, router=FakeRouter(times)).execute(
            ORIGIN, RankingPolicy(mode=SortMode.DISTANCE)
        )
        assert [h.ranked.lot.source_id for h in result.hits][:2] == ["o03", "o00"]
        assert {h.ranked.block for h in result.hits} == {Block.DISTANCE}
        assert len(result.hits) == 18  # everything in range fits under the cap of 20

    def test_exhausted_quota_degrades_to_straight_line_and_says_so(
        self, store: SqliteStore, clock: Clock
    ) -> None:
        seed(store, self.lots())
        router = FakeRouter({}, fail=QuotaExceeded(ROUTES_ELEMENTS, 9000, "2026-10"))
        result = SearchNearbyParking(store, clock, router=router).execute(ORIGIN, RankingPolicy())

        assert result.walking is WalkingStatus.QUOTA_EXHAUSTED
        assert result.hits  # still a full list
        assert all(h.ranked.walking is None for h in result.hits)  # nothing invented

    def test_router_failure_degrades_the_same_way(self, store: SqliteStore, clock: Clock) -> None:
        seed(store, self.lots())
        router = FakeRouter({}, fail=RoutesError("timeout"))
        result = SearchNearbyParking(store, clock, router=router).execute(ORIGIN, RankingPolicy())
        assert result.walking is WalkingStatus.UNAVAILABLE
        assert result.hits

    def test_no_router_configured_is_unavailable(self, store: SqliteStore, clock: Clock) -> None:
        seed(store, self.lots())
        result = SearchNearbyParking(store, clock).execute(ORIGIN, RankingPolicy())
        assert result.walking is WalkingStatus.UNAVAILABLE
        assert result.hits


class TestFoodTravelTimes:
    @staticmethod
    def payload() -> dict[str, object]:
        def place(pid: str, lat: float, name: str | None = "店") -> dict[str, object]:
            raw: dict[str, object] = {
                "id": pid,
                "location": {"latitude": lat, "longitude": 121.55},
                "rating": 4.5,
                "userRatingCount": 500,
            }
            if name:
                raw["displayName"] = {"text": name}
            return raw

        return {
            "places": [
                place("p0", 25.051),
                place("skipped", 25.052, name=None),  # unusable: no name
                place("p2", 25.053),
            ],
            # one summary per place, in order, including the one that gets skipped
            "routingSummaries": [
                {"legs": [{"duration": "597s", "distanceMeters": 700}]},
                {"legs": [{"duration": "100s", "distanceMeters": 120}]},
                {"legs": [{"duration": "1039s", "distanceMeters": 1219}]},
            ],
        }

    def test_request_asks_for_walking_summaries_from_the_search_origin(
        self, make_client: ClientFactory
    ) -> None:
        sent: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            sent["body"] = json.loads(request.content)
            sent["mask"] = request.headers["X-Goog-FieldMask"]
            return httpx.Response(200, json=self.payload())

        GooglePlaces(make_client(handler), "k").nearby_food(
            GeoPoint(25.05, 121.5493), 1000, 20, 4.0, ORIGIN
        )
        body = sent["body"]
        assert isinstance(body, dict)
        assert body["routingParameters"] == {
            "origin": {"latitude": ORIGIN.lat, "longitude": ORIGIN.lng},
            "travelMode": "WALK",
        }
        assert "routingSummaries" in str(sent["mask"])

    def test_without_an_origin_no_routing_is_requested(self, make_client: ClientFactory) -> None:
        sent: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            sent["body"] = json.loads(request.content)
            sent["mask"] = request.headers["X-Goog-FieldMask"]
            return httpx.Response(200, json={"places": []})

        GooglePlaces(make_client(handler), "k").nearby_food(GeoPoint(25.05, 121.5493), 1000, 20)
        assert "routingParameters" not in sent["body"]  # type: ignore[operator]
        assert "routingSummaries" not in str(sent["mask"])

    def test_summaries_stay_aligned_when_a_place_is_skipped(
        self, make_client: ClientFactory
    ) -> None:
        places = GooglePlaces(
            make_client(lambda r: httpx.Response(200, json=self.payload())), "k"
        ).nearby_food(GeoPoint(25.05, 121.5493), 1000, 20, 4.0, ORIGIN)

        by_id = {p.id: p for p in places}
        assert set(by_id) == {"p0", "p2"}
        assert by_id["p0"].walking == RouteTime(597, 700)
        # p2 is the third place; its summary is the third entry, not the second.
        assert by_id["p2"].walking == RouteTime(1039, 1219)

    def test_an_empty_summary_means_no_walking_time(self, make_client: ClientFactory) -> None:
        payload = self.payload()
        payload["routingSummaries"] = [{}, {}, {}]
        places = GooglePlaces(
            make_client(lambda r: httpx.Response(200, json=payload)), "k"
        ).nearby_food(GeoPoint(25.05, 121.5493), 1000, 20, 4.0, ORIGIN)
        assert all(p.walking is None for p in places)

    class Source:
        def nearby_food(
            self,
            center: GeoPoint,
            radius_m: int,
            limit: int,
            min_rating: float = 0.0,
            origin: GeoPoint | None = None,
        ) -> list[Place]:
            def p(pid: str, dlat: float, secs: int | None) -> Place:
                return Place(
                    id=pid,
                    name=pid,
                    location=GeoPoint(center.lat + dlat, center.lng),
                    rating=4.5,
                    user_rating_count=500,
                    walking=RouteTime(secs, secs) if secs else None,
                )

            return [
                p("near_slow", 0.0010, 900),
                p("far_fast", 0.0040, 300),
                p("unrouted", 0.0005, None),
            ]

    def test_use_case_orders_food_by_walking_time(self) -> None:
        result = SearchNearbyFood(self.Source(), min_rating=4.0, min_reviews=100).execute(
            GeoPoint(25.05, 121.5493), 1000, 20, ORIGIN
        )
        assert [h.place.id for h in result.hits] == ["far_fast", "near_slow", "unrouted"]
