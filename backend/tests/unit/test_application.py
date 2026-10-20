"""Use-case tests. Real SQLite (in memory) and real domain; only the outside world is faked."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from yimmparking.adapters.geocode.google import GoogleGeocoder
from yimmparking.adapters.places.google_places import GooglePlaces
from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.application.ports import (
    GeocodingError,
    GeocodingUnavailable,
    PlacesError,
    SourceError,
)
from yimmparking.application.refresh import RefreshAvailability, RefreshLots
from yimmparking.application.search import (
    GEOCODE_CACHE_TTL,
    ResolveAddress,
    SearchNearbyFood,
    SearchNearbyParking,
    normalize_address,
)
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import (
    AvailabilityBatch,
    AvailabilityReading,
    Brand,
    BrandEvidence,
    City,
    Freshness,
    GeocodeCandidate,
    IParkingStation,
    ParkingLot,
    Place,
)
from yimmparking.domain.opening import OpeningPeriod
from yimmparking.domain.ranking import RankingPolicy, SortMode

CENTER = GeoPoint(25.0330, 121.5654)


def lot(
    source_id: str,
    name: str,
    at: GeoPoint,
    *,
    city: City = City.TAIPEI,
    phone: str = "",
    total: int | None = 100,
) -> ParkingLot:
    return ParkingLot(
        id=f"{city.value}:{source_id}",
        city=city,
        source_id=source_id,
        name=name,
        address="",
        district="",
        location=at,
        phone=phone,
        total_car=total,
    )


class FakeFeed:
    def __init__(self, city: City, lots: list[ParkingLot], batch: AvailabilityBatch | None = None):
        self.city = city
        self.lots = lots
        self.batch = batch
        self.fail = False

    def fetch_lots(self) -> list[ParkingLot]:
        if self.fail:
            raise SourceError("boom")
        return self.lots

    def fetch_availability(self) -> AvailabilityBatch:
        if self.fail:
            raise SourceError("boom")
        assert self.batch is not None
        return self.batch


class FakeDirectory:
    def __init__(self, stations: list[IParkingStation] | None = None, fail: bool = False):
        self.stations = stations or []
        self.fail = fail

    def fetch_stations(self) -> list[IParkingStation]:
        if self.fail:
            raise SourceError("directory down")
        return self.stations


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.fixture
def store() -> SqliteStore:
    s = SqliteStore(":memory:")
    yield s  # type: ignore[misc]
    s.close()


class TestRefreshLots:
    def test_dry_run_reports_but_writes_nothing(self, store: SqliteStore) -> None:
        feed = FakeFeed(City.TAIPEI, [lot("1", "嘟嘟房甲站", CENTER)])
        report = RefreshLots([feed], FakeDirectory(), store).run(dry_run=True)
        assert report.cities[0].fetched == 1
        assert report.cities[0].written is False
        assert store.lot_count(City.TAIPEI) == 0

    def test_write_classifies_brand_and_flags_iparking(self, store: SqliteStore) -> None:
        feed = FakeFeed(
            City.TAIPEI,
            [lot("1", "嘟嘟房甲站", CENTER), lot("2", "某停車場", CENTER, phone="0226550818")],
        )
        station = IParkingStation("DDHTPC001", "甲站", "", "TPC", CENTER)
        RefreshLots([feed], FakeDirectory([station]), store).run(dry_run=False)

        found = {x.source_id: x for x in store.lots_in_box(_box_around(CENTER))}
        assert found["1"].brand is Brand.DODOHOME
        assert found["1"].brand_evidence is BrandEvidence.NAME
        assert found["1"].iparking_code == "DDHTPC001"
        # Recognised by phone, so it is 嘟嘟房 too, and the same station is claimed by only one lot.
        assert found["2"].brand is Brand.DODOHOME
        assert found["2"].brand_evidence is BrandEvidence.PHONE

    def test_rerun_is_idempotent(self, store: SqliteStore) -> None:
        feed = FakeFeed(City.TAIPEI, [lot("1", "A", CENTER), lot("2", "B", CENTER)])
        job = RefreshLots([feed], FakeDirectory(), store)
        job.run(dry_run=False)
        job.run(dry_run=False)
        assert store.lot_count(City.TAIPEI) == 2

    def test_one_failing_city_does_not_touch_the_other(self, store: SqliteStore) -> None:
        tpe = FakeFeed(City.TAIPEI, [lot("1", "A", CENTER)])
        ntpc = FakeFeed(City.NEW_TAIPEI, [lot("9", "B", CENTER, city=City.NEW_TAIPEI)])
        RefreshLots([tpe, ntpc], FakeDirectory(), store).run(dry_run=False)

        ntpc.fail = True
        tpe.lots = [lot("1", "A", CENTER), lot("2", "A2", CENTER)]
        report = RefreshLots([tpe, ntpc], FakeDirectory(), store).run(dry_run=False)

        assert store.lot_count(City.TAIPEI) == 2
        assert store.lot_count(City.NEW_TAIPEI) == 1  # untouched
        assert report.cities[1].error == "boom"

    def test_truncated_feed_does_not_replace_good_data(self, store: SqliteStore) -> None:
        many = [lot(str(i), f"L{i}", CENTER) for i in range(10)]
        feed = FakeFeed(City.TAIPEI, many)
        RefreshLots([feed], FakeDirectory(), store).run(dry_run=False)

        feed.lots = many[:2]
        report = RefreshLots([feed], FakeDirectory(), store).run(dry_run=False)

        assert store.lot_count(City.TAIPEI) == 10
        assert report.cities[0].written is False
        assert report.cities[0].error and "truncated" in report.cities[0].error

    def test_iparking_outage_does_not_block_government_data(self, store: SqliteStore) -> None:
        feed = FakeFeed(City.TAIPEI, [lot("1", "嘟嘟房甲站", CENTER)])
        RefreshLots([feed], FakeDirectory(fail=True), store).run(dry_run=False)
        assert store.lot_count(City.TAIPEI) == 1

    def test_iparking_outage_keeps_the_flags_already_held(self, store: SqliteStore) -> None:
        feed = FakeFeed(
            City.TAIPEI, [lot("1", "嘟嘟房甲站", CENTER), lot("2", "某停車場", CENTER)]
        )
        station = IParkingStation("DDHTPC001", "甲站", "", "TPC", CENTER)
        RefreshLots([feed], FakeDirectory([station]), store).run(dry_run=False)

        report = RefreshLots([feed], FakeDirectory(fail=True), store).run(dry_run=False)

        found = {x.source_id: x for x in store.lots_in_box(_box_around(CENTER))}
        assert found["1"].iparking_code == "DDHTPC001"
        assert found["2"].iparking_code is None
        assert report.iparking_error == "directory down"
        assert report.cities[0].iparking_matched == 1

    def test_a_held_flag_is_dropped_once_the_lot_is_no_longer_dodohome(
        self, store: SqliteStore
    ) -> None:
        feed = FakeFeed(City.TAIPEI, [lot("1", "嘟嘟房甲站", CENTER)])
        station = IParkingStation("DDHTPC001", "甲站", "", "TPC", CENTER)
        RefreshLots([feed], FakeDirectory([station]), store).run(dry_run=False)

        feed.lots = [lot("1", "改名停車場", CENTER)]
        RefreshLots([feed], FakeDirectory(fail=True), store).run(dry_run=False)

        assert store.lots_in_box(_box_around(CENTER))[0].iparking_code is None


class TestRefreshAvailabilityAndSearch:
    t0 = datetime(2026, 10, 10, 14, 37, tzinfo=UTC)

    def seed(self, store: SqliteStore) -> None:
        lots = [
            lot("near", "近的", GeoPoint(25.0331, 121.5654), total=100),
            lot("dodo", "嘟嘟房遠站", GeoPoint(25.0390, 121.5654), total=50),
            lot("nodata", "無資料場", GeoPoint(25.0335, 121.5654), total=10),
            lot("over", "超量場", GeoPoint(25.0336, 121.5654), total=5),
            lot("zero", "滿位場", GeoPoint(25.0337, 121.5654), total=40),
        ]
        RefreshLots([FakeFeed(City.TAIPEI, lots)], FakeDirectory(), store).run(dry_run=False)
        batch = AvailabilityBatch(
            City.TAIPEI,
            self.t0,
            (
                AvailabilityReading("taipei:near", 30),
                AvailabilityReading("taipei:dodo", 12),
                AvailabilityReading("taipei:nodata", None),
                AvailabilityReading("taipei:over", 9),
                AvailabilityReading("taipei:zero", 0),
                AvailabilityReading("taipei:not_in_db", 3),
            ),
        )
        job = RefreshAvailability([FakeFeed(City.TAIPEI, [], batch)], store, FixedClock(self.t0))
        report = job.run(dry_run=False)
        assert report.cities[0].orphans == 1
        assert report.cities[0].known == 5
        assert report.cities[0].unknown == 1

    def search(self, store: SqliteStore, now: datetime, **policy: object):
        return SearchNearbyParking(store, FixedClock(now)).execute(
            CENTER,
            RankingPolicy(min_results=1, **policy),  # type: ignore[arg-type]
        )

    def test_availability_semantics_through_the_full_stack(self, store: SqliteStore) -> None:
        self.seed(store)
        result = self.search(store, self.t0 + timedelta(minutes=5), mode=SortMode.DISTANCE)
        by = {h.ranked.lot.source_id: h for h in result.hits}

        assert by["near"].availability.count == 30
        assert by["near"].freshness is Freshness.FRESH
        assert by["nodata"].availability.count is None  # unknown, not zero
        assert by["zero"].availability.count == 0  # a real "full"
        assert by["zero"].availability.is_known
        assert by["over"].availability.count == 9
        assert by["over"].availability.suspect

    def test_brand_priority_orders_results(self, store: SqliteStore) -> None:
        self.seed(store)
        result = self.search(store, self.t0)
        ids = [h.ranked.lot.source_id for h in result.hits]
        assert ids[0] == "dodo"  # farther, but preferred brand
        assert ids[1] == "near"

    def test_expired_reading_is_presented_as_unknown(self, store: SqliteStore) -> None:
        self.seed(store)
        result = self.search(store, self.t0 + timedelta(hours=3), mode=SortMode.DISTANCE)
        for hit in result.hits:
            assert hit.freshness is Freshness.EXPIRED
            assert hit.availability.count is None

    def test_older_feed_never_rewinds_latest(self, store: SqliteStore) -> None:
        self.seed(store)
        older = AvailabilityBatch(
            City.TAIPEI,
            self.t0 - timedelta(minutes=30),
            (AvailabilityReading("taipei:near", 99),),
        )
        store.record_availability(older)
        count, observed = store.latest_availability(["taipei:near"])["taipei:near"]
        assert (count, observed) == (30, self.t0)

    def test_same_batch_twice_is_idempotent(self, store: SqliteStore) -> None:
        self.seed(store)
        batch = AvailabilityBatch(City.TAIPEI, self.t0, (AvailabilityReading("taipei:near", 30),))
        store.record_availability(batch)
        store.record_availability(batch)
        assert store.latest_availability(["taipei:near"])["taipei:near"][0] == 30


class TestResolveAddress:
    now = datetime(2026, 10, 10, 14, 0, tzinfo=UTC)

    class CountingGeocoder:
        def __init__(self) -> None:
            self.calls = 0

        def geocode(self, query: str) -> list[GeocodeCandidate]:
            self.calls += 1
            return [GeocodeCandidate("台北市信義區市府路1號", GeoPoint(25.0375, 121.5637), "pid")]

    def test_normalization_unifies_equivalent_spellings(self) -> None:
        assert normalize_address("臺北市 信義區　市府路１號") == normalize_address(
            "台北市信義區市府路1號"
        )

    def test_second_lookup_is_served_from_cache(self, store: SqliteStore) -> None:
        geocoder = self.CountingGeocoder()
        resolver = ResolveAddress(geocoder, store, FixedClock(self.now))
        first = resolver.execute("臺北市信義區市府路1號")
        second = resolver.execute("台北市 信義區 市府路1號")
        assert geocoder.calls == 1
        assert first[0].location == second[0].location

    def test_cache_expires_and_is_actually_deleted(self, store: SqliteStore) -> None:
        geocoder = self.CountingGeocoder()
        ResolveAddress(geocoder, store, FixedClock(self.now)).execute("市府路1號")
        later = self.now + GEOCODE_CACHE_TTL + timedelta(seconds=1)
        assert store.get(normalize_address("市府路1號"), later) is None
        assert store.purge_expired(later) == 1
        ResolveAddress(geocoder, store, FixedClock(later)).execute("市府路1號")
        assert geocoder.calls == 2

    def test_cached_entry_holds_no_address_text(self, store: SqliteStore) -> None:
        ResolveAddress(self.CountingGeocoder(), store, FixedClock(self.now)).execute("市府路1號")
        row = store._conn.execute("SELECT payload FROM geocode_cache").fetchone()  # noqa: SLF001
        assert "formatted" not in row["payload"]
        assert "市府路" not in row["payload"]

    def test_blank_query_returns_nothing_without_calling_geocoder(self, store: SqliteStore) -> None:
        geocoder = self.CountingGeocoder()
        assert ResolveAddress(geocoder, store, FixedClock(self.now)).execute("   ") == []
        assert geocoder.calls == 0


ClientFactory = Callable[[Callable[[httpx.Request], httpx.Response]], httpx.Client]


class TestGoogleGeocoder:
    def test_missing_key_is_unavailable_not_empty(self, make_client: ClientFactory) -> None:
        geocoder = GoogleGeocoder(make_client(lambda r: httpx.Response(500)), api_key=None)
        with pytest.raises(GeocodingUnavailable):
            geocoder.geocode("市府路1號")

    def test_parses_candidates(self, make_client: ClientFactory) -> None:
        payload = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "110台北市信義區市府路1號",
                    "place_id": "ChIJ",
                    "geometry": {"location": {"lat": 25.0375, "lng": 121.5637}},
                }
            ],
        }
        geocoder = GoogleGeocoder(make_client(lambda r: httpx.Response(200, json=payload)), "k")
        [c] = geocoder.geocode("市府路1號")
        assert c.location == GeoPoint(25.0375, 121.5637)
        assert c.place_id == "ChIJ"

    def test_zero_results_is_an_empty_list(self, make_client: ClientFactory) -> None:
        geocoder = GoogleGeocoder(
            make_client(
                lambda r: httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []})
            ),
            "k",
        )
        assert geocoder.geocode("???") == []

    def test_denied_key_is_an_error_not_zero_results(self, make_client: ClientFactory) -> None:
        body = {"status": "REQUEST_DENIED", "error_message": "key invalid", "results": []}
        geocoder = GoogleGeocoder(make_client(lambda r: httpx.Response(200, json=body)), "bad")
        with pytest.raises(GeocodingError, match="REQUEST_DENIED"):
            geocoder.geocode("市府路1號")


class TestGooglePlaces:
    def test_missing_key_raises(self, make_client: ClientFactory) -> None:
        places = GooglePlaces(make_client(lambda r: httpx.Response(500)), api_key=None)
        with pytest.raises(PlacesError):
            places.nearby_food(CENTER, 500, 10)

    def test_request_asks_google_to_exclude_low_rated_places(
        self, make_client: ClientFactory
    ) -> None:
        sent: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            sent["url"] = str(request.url)
            sent["body"] = json.loads(request.content)
            sent["mask"] = request.headers["X-Goog-FieldMask"]
            sent["key"] = request.headers["X-Goog-Api-Key"]
            return httpx.Response(200, json={"places": []})

        GooglePlaces(make_client(handler), api_key="k").nearby_food(CENTER, 1000, 20, 4.0)

        body = sent["body"]
        assert isinstance(body, dict)
        assert str(sent["url"]).endswith(":searchText")
        assert body["minRating"] == 4.0  # filtered by Google, before it fills the 20 slots
        assert body["includedType"] == "restaurant"
        assert body["strictTypeFiltering"] is True
        assert body["pageSize"] == 20
        rect = body["locationRestriction"]["rectangle"]
        assert rect["low"]["latitude"] < CENTER.lat < rect["high"]["latitude"]
        assert rect["low"]["longitude"] < CENTER.lng < rect["high"]["longitude"]
        assert "places.rating" in str(sent["mask"])
        assert sent["key"] == "k"

    @pytest.mark.parametrize(
        ("wanted", "sent_floor"), [(4.0, 4.0), (4.3, 4.0), (4.5, 4.5), (4.9, 4.5), (0.0, None)]
    )
    def test_rating_floor_is_rounded_down_to_the_half_step_google_accepts(
        self, make_client: ClientFactory, wanted: float, sent_floor: float | None
    ) -> None:
        # Rounding up would silently drop a 4.3 place the caller asked for; the exact threshold
        # is applied again after the response.
        sent: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            sent["body"] = json.loads(request.content)
            return httpx.Response(200, json={"places": []})

        GooglePlaces(make_client(handler), api_key="k").nearby_food(CENTER, 1000, 20, wanted)
        body = sent["body"]
        assert isinstance(body, dict)
        assert body.get("minRating") == sent_floor

    def test_parses_places(self, make_client: ClientFactory) -> None:
        payload = {
            "places": [
                {
                    "id": "p1",
                    "displayName": {"text": "牛肉麵"},
                    "location": {"latitude": 25.0378, "longitude": 121.5637},
                    "rating": 4.5,
                    "userRatingCount": 120,
                    "priceLevel": "PRICE_LEVEL_MODERATE",
                    "primaryType": "chinese_restaurant",
                    "regularOpeningHours": {
                        "periods": [
                            {
                                "open": {"day": 1, "hour": 11, "minute": 0},
                                "close": {"day": 1, "hour": 21, "minute": 30},
                            }
                        ]
                    },
                    "googleMapsUri": "https://maps.google.com/?cid=1",
                },
                {"id": "broken", "displayName": {"text": "沒座標"}},
            ]
        }
        places = GooglePlaces(make_client(lambda r: httpx.Response(200, json=payload)), "k")
        [place] = places.nearby_food(CENTER, 500, 20)
        assert place.rating == 4.5
        assert place.user_rating_count == 120
        assert place.price_level == "MODERATE"
        assert place.primary_type_code == "chinese_restaurant"
        # Monday 11:00 to 21:30, in minutes from Sunday 00:00. Open now is not decided here.
        assert place.opening == (OpeningPeriod(start=1440 + 660, end=1440 + 1290),)
        assert place.open_now is None

    @pytest.mark.parametrize(
        ("periods", "expected"),
        [
            ([{"open": {"day": 0, "hour": 0, "minute": 0}}], ((0, 10080),)),  # open all week
            (
                [{"open": {"day": 6, "hour": 22}, "close": {"day": 0, "hour": 2}}],
                ((9960, 10200),),  # Saturday 22:00 into Sunday 02:00 wraps the week
            ),
            ([], None),  # Google said nothing: unknown, not closed
            # Unreadable schedules are unknown too, never a partial week or a crash.
            ([{"open": {"hour": 9}, "close": {"day": 1, "hour": 18}}], None),
            ([{"open": {"day": 9, "hour": 9}, "close": {"day": 9, "hour": 18}}], None),
            ([{"open": {"day": 1, "hour": "x"}, "close": {"day": 1, "hour": 18}}], None),
            (
                [
                    {"open": {"day": 1, "hour": 9}, "close": {"day": 1, "hour": 18}},
                    {"close": {"day": 2, "hour": 18}},
                ],
                None,
            ),
            (["junk"], None),
        ],
    )
    def test_opening_periods_are_parsed(self, periods: list, expected: object) -> None:
        from yimmparking.adapters.places.google_places import _parse_opening

        raw = {"regularOpeningHours": {"periods": periods}} if periods else {}
        parsed = _parse_opening(raw)
        if expected is None:
            assert parsed is None
        else:
            assert parsed == tuple(OpeningPeriod(start=s, end=e) for s, e in expected)

    def test_a_place_with_unreadable_hours_is_still_listed(self, make_client: ClientFactory) -> None:
        payload = {
            "places": [
                {
                    "id": "p1",
                    "displayName": {"text": "牛肉麵"},
                    "location": {"latitude": 25.0378, "longitude": 121.5637},
                    "regularOpeningHours": {"periods": [{"open": {"hour": 11}}]},
                }
            ]
        }
        places = GooglePlaces(make_client(lambda r: httpx.Response(200, json=payload)), "k")
        [place] = places.nearby_food(CENTER, 500, 20)
        assert place.name == "牛肉麵"
        assert place.opening is None

    def test_http_error_is_a_places_error(self, make_client: ClientFactory) -> None:
        places = GooglePlaces(make_client(lambda r: httpx.Response(403)), api_key="k")
        with pytest.raises(PlacesError, match="403"):
            places.nearby_food(CENTER, 500, 10)


class TestSearchNearbyFood:
    class Fixed:
        def __init__(self, places: list[Place]) -> None:
            self.places = places
            self.asked_min_rating: float | None = None

        def nearby_food(
            self,
            center: GeoPoint,
            radius_m: int,
            limit: int,
            min_rating: float = 0.0,
            origin: GeoPoint | None = None,
        ) -> list[Place]:
            self.asked_min_rating = min_rating
            return self.places

    @staticmethod
    def place(pid: str, d_lat: float, rating: float | None, reviews: int | None) -> Place:
        return Place(
            id=pid,
            name=pid,
            location=GeoPoint(CENTER.lat + d_lat, CENTER.lng),
            rating=rating,
            user_rating_count=reviews,
        )

    def test_passes_the_rating_floor_to_the_provider(self) -> None:
        source = self.Fixed([])
        SearchNearbyFood(source, min_rating=4.3).execute(CENTER)
        assert source.asked_min_rating == 4.3

    def test_drops_unrated_few_review_and_out_of_radius_places(self) -> None:
        source = self.Fixed(
            [
                self.place("good-far", 0.0070, 4.6, 500),  # ~780 m
                self.place("good-near", 0.0010, 4.4, 80),  # ~110 m
                self.place("five-stars-three-reviews", 0.0005, 5.0, 3),
                self.place("below-floor", 0.0008, 4.1, 900),
                self.place("unrated", 0.0004, None, None),
                self.place("outside-radius", 0.0150, 4.9, 4000),  # ~1.67 km (rectangle corner)
            ]
        )
        result = SearchNearbyFood(source, min_rating=4.3, min_reviews=20).execute(CENTER, 1000)
        assert [h.place.id for h in result.hits] == ["good-near", "good-far"]
        assert (result.min_rating, result.min_reviews) == (4.3, 20)


def _box_around(point: GeoPoint):
    from yimmparking.domain.geo import bounding_box

    return bounding_box(point, 5000)
