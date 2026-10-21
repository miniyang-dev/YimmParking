from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from yimmparking.adapters.alert.webhook import LogOnlyAlerter
from yimmparking.adapters.geocode.google import GoogleGeocoder
from yimmparking.adapters.places.google_places import GooglePlaces
from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.application.feed_watch import FeedWatch
from yimmparking.application.limits import (
    GEOCODING,
    PLACES_NEARBY,
    ROUTES_ELEMENTS,
    LimitedGeocoder,
    LimitedPlaces,
    UsageGate,
)
from yimmparking.application.ports import SourceError
from yimmparking.application.refresh import RefreshAvailability, RefreshLots
from yimmparking.application.search import ResolveAddress, SearchNearbyFood, SearchNearbyParking
from yimmparking.application.search_bikes import SearchNearbyBikes
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import (
    AvailabilityBatch,
    AvailabilityReading,
    BikeStation,
    City,
    IParkingStation,
    ParkingLot,
)
from yimmparking.interface.api import create_app
from yimmparking.interface.container import Container
from yimmparking.interface.settings import Settings

NOW = datetime(2026, 10, 10, 14, 40, tzinfo=UTC)
CENTER = GeoPoint(25.0375, 121.5637)  # 市府路1號


class Clock:
    def now(self) -> datetime:
        return NOW


class Feed:
    def __init__(self, city: City, lots: list[ParkingLot], batch: AvailabilityBatch) -> None:
        self.city, self._lots, self._batch = city, lots, batch

    def fetch_lots(self) -> list[ParkingLot]:
        return self._lots

    def fetch_availability(self) -> AvailabilityBatch:
        return self._batch


class Directory:
    def fetch_stations(self) -> list[IParkingStation]:
        return [IParkingStation("DDHTPC001", "市府站", "", "TPC", GeoPoint(25.0378, 121.5637))]


def _lot(source_id: str, name: str, lat: float, phone: str = "") -> ParkingLot:
    return ParkingLot(
        id=f"taipei:{source_id}",
        city=City.TAIPEI,
        source_id=source_id,
        name=name,
        address="台北市某路",
        district="信義區",
        location=GeoPoint(lat, 121.5637),
        phone=phone,
        total_car=100,
        fee_text="計時50元",
        service_time="00:00-24:00",
    )


def build(
    api_key: str | None,
    transport: httpx.MockTransport | None = None,
    *,
    places_limit: int = 900,
    router: object | None = None,
    bike_feeds: list[Any] | None = None,
) -> Container:
    http = httpx.Client(transport=transport or httpx.MockTransport(lambda r: httpx.Response(500)))
    store = SqliteStore(":memory:")
    lots = [
        _lot("a", "嘟嘟房市府站停車場", 25.0378),
        _lot("b", "一般停車場", 25.0376),
        _lot("c", "台灣聯通松高站", 25.0390),
    ]
    batch = AvailabilityBatch(
        City.TAIPEI,
        NOW,
        (
            AvailabilityReading("taipei:a", 41),
            AvailabilityReading("taipei:b", None),
            AvailabilityReading("taipei:c", 0),
        ),
    )
    feed = Feed(City.TAIPEI, lots, batch)
    feeds = [feed]
    RefreshLots(feeds, Directory(), store).run(dry_run=False)  # type: ignore[arg-type]
    RefreshAvailability(feeds, store, Clock()).run(dry_run=False)  # type: ignore[arg-type]

    settings = Settings.from_env()
    object.__setattr__(settings, "google_maps_api_key", api_key)
    usage = UsageGate(
        store,
        Clock(),
        {GEOCODING: 9000, PLACES_NEARBY: places_limit, ROUTES_ELEMENTS: 9000},
    )
    geocoder = LimitedGeocoder(GoogleGeocoder(http, api_key), usage)
    places = LimitedPlaces(GooglePlaces(http, api_key), usage)
    return Container(
        settings=settings,
        http=http,
        clock=Clock(),
        store=store,
        feeds=feeds,  # type: ignore[arg-type]
        geocoder=geocoder,
        places=places,
        refresh_lots=RefreshLots(feeds, Directory(), store),  # type: ignore[arg-type]
        refresh_availability=RefreshAvailability(feeds, store, Clock()),  # type: ignore[arg-type]
        search_parking=SearchNearbyParking(store, Clock(), router=router),  # type: ignore[arg-type]
        resolve_address=ResolveAddress(geocoder, store, Clock()),
        search_food=SearchNearbyFood(places),
        search_bikes=SearchNearbyBikes(bike_feeds or [], Clock()),
        usage=usage,
        router=router,  # type: ignore[arg-type]
        feed_watch=FeedWatch(store, Clock(), LogOnlyAlerter()),
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        if "geocode" in str(request.url):
            if "不存在" in request.url.params["address"]:
                return httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []})
            return httpx.Response(
                200,
                json={
                    "status": "OK",
                    "results": [
                        {
                            "formatted_address": "110台北市信義區市府路1號",
                            "place_id": "p",
                            "geometry": {"location": {"lat": CENTER.lat, "lng": CENTER.lng}},
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "id": "x",
                        "displayName": {"text": "牛肉麵"},
                        "rating": 4.4,
                        "userRatingCount": 300,
                        "location": {"latitude": 25.0378, "longitude": 121.5640},
                    }
                ]
            },
        )

    container = build("test-key", httpx.MockTransport(handler))
    with TestClient(create_app(container=container)) as c:
        yield c
    container.close()


def test_health_reports_sources(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()
    assert body["geocoder_configured"] is True
    taipei = next(s for s in body["sources"] if s["city"] == "taipei")
    assert taipei["lots"] == 3
    # New Taipei has no data in this fixture, so the service must say it is degraded.
    assert body["status"] == "degraded"
    stale = {s["city"]: s["stale"] for s in body["sources"]}
    assert stale == {"taipei": False, "new_taipei": True}


def test_search_names_the_cities_whose_feed_has_stopped(client: TestClient) -> None:
    body = client.get(
        "/api/v1/parking/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng}
    ).json()
    assert body["meta"]["stale_sources"] == [{"city": "new_taipei", "as_of": None}]


def test_health_identifies_the_running_build(client: TestClient) -> None:
    body = client.get("/api/v1/health").json()
    # The tests run inside the git checkout, so the commit is normally known; without git it is null.
    assert body["version"] is None or re.fullmatch(r"[0-9a-f]{40}", body["version"])
    started = datetime.fromisoformat(body["started_at"])
    assert started.tzinfo is not None  # a deploy check compares it with its own UTC timestamps
    assert body["frontend_version"] is None  # this fixture serves no web build
    # Stable for the life of the process: it is read once, when the app is created.
    again = client.get("/api/v1/health").json()
    assert (again["version"], again["started_at"]) == (body["version"], body["started_at"])


def test_health_reports_the_web_build_commit_and_follows_a_rebuild(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    container = build("k")
    object.__setattr__(container.settings, "web_dist", tmp_path)
    with TestClient(create_app(container=container)) as c:
        assert c.get("/api/v1/health").json()["frontend_version"] is None  # not stamped yet
        (tmp_path / "version.txt").write_text("a" * 40 + "\n", encoding="utf-8")
        assert c.get("/api/v1/health").json()["frontend_version"] == "a" * 40
        (tmp_path / "version.txt").write_text("b" * 40, encoding="utf-8")  # rebuilt, no restart
        assert c.get("/api/v1/health").json()["frontend_version"] == "b" * 40
    container.close()


def test_nearby_orders_by_brand_then_distance(client: TestClient) -> None:
    body = client.get(
        "/api/v1/parking/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng}
    ).json()
    names = [r["name"] for r in body["results"]]
    assert names == ["嘟嘟房市府站停車場", "台灣聯通松高站", "一般停車場"]
    first, second, third = body["results"]
    assert first["iparking"] is True  # the directory station is right next to it
    assert (first["vendor"], first["block"]) == ("iparking_dodohome", "priority")
    assert (second["vendor"], second["block"]) == ("liantong", "priority")
    assert (third["vendor"], third["block"]) == (None, "other")


def test_availability_states_are_distinct(client: TestClient) -> None:
    body = client.get(
        "/api/v1/parking/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng}
    ).json()
    by = {r["name"]: r["availability"] for r in body["results"]}
    dodo = by["嘟嘟房市府站停車場"]
    assert dodo["count"] == 41 and dodo["state"] == "known"
    assert by["一般停車場"]["state"] == "unknown" and by["一般停車場"]["count"] is None
    assert by["台灣聯通松高站"]["state"] == "known" and by["台灣聯通松高站"]["count"] == 0
    assert dodo["freshness"] == "fresh"


def test_distance_mode_ignores_brand(client: TestClient) -> None:
    body = client.get(
        "/api/v1/parking/nearby",
        params={"lat": CENTER.lat, "lng": CENTER.lng, "mode": "distance"},
    ).json()
    assert body["results"][0]["name"] == "一般停車場"  # 25.0376 is the nearest to 25.0375


def test_search_by_address_resolves_then_ranks(client: TestClient) -> None:
    body = client.get("/api/v1/search", params={"q": "臺北市信義區市府路1號"}).json()
    assert body["origin"]["label"] == "110台北市信義區市府路1號"
    assert body["meta"]["count"] == 3


def test_unknown_address_is_404_with_code(client: TestClient) -> None:
    r = client.get("/api/v1/search", params={"q": "不存在的路99號"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "address_not_found"


def test_out_of_range_coordinate_is_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/parking/nearby", params={"lat": 95, "lng": 121.5})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_food_passes_through_with_distance_and_attribution(client: TestClient) -> None:
    body = client.get("/api/v1/food/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng}).json()
    assert body["attribution"] == "Google Maps"
    assert body["results"][0]["name"] == "牛肉麵"
    assert body["results"][0]["distance_m"] > 0
    assert body["min_rating"] == 4.0
    assert body["min_reviews"] == 100


def test_unconfigured_geocoder_is_503_not_404() -> None:
    container = build(api_key=None)
    with TestClient(create_app(container=container)) as c:
        r = c.get("/api/v1/search", params={"q": "市府路1號"})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "geocoder_unavailable"
        # Coordinate search needs no geocoder and must keep working.
        ok = c.get("/api/v1/parking/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng})
        assert ok.status_code == 200
        food = c.get("/api/v1/food/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng})
        assert food.status_code == 503
    container.close()


def test_food_is_refused_with_429_once_the_monthly_limit_is_reached() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"places": []})

    container = build("k", httpx.MockTransport(handler), places_limit=2)
    with TestClient(create_app(container=container)) as c:
        params = {"lat": CENTER.lat, "lng": CENTER.lng}
        assert c.get("/api/v1/food/nearby", params=params).status_code == 200
        assert c.get("/api/v1/food/nearby", params=params).status_code == 200
        blocked = c.get("/api/v1/food/nearby", params=params)

        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "quota_exhausted"
        assert calls["n"] == 2  # the blocked request never left the process

        usage = {u["meter"]: u for u in c.get("/api/v1/health").json()["usage"]}
        assert usage["places_nearby"]["used"] == 2
        assert usage["places_nearby"]["limit"] == 2
    container.close()


def test_built_client_is_served_from_the_same_origin(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>YimmParking</title>", encoding="utf-8"
    )
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")

    container = build("k")
    object.__setattr__(container.settings, "web_dist", tmp_path)
    with TestClient(create_app(container=container)) as c:
        page = c.get("/")
        assert page.status_code == 200
        assert "YimmParking" in page.text
        assert c.get("/assets/app.js").status_code == 200
        # API routes are not shadowed by the static mount.
        assert c.get("/api/v1/health").json()["geocoder_configured"] is True
        assert c.get("/no-such-file.txt").status_code == 404
    container.close()


def test_search_meta_says_travel_times_are_unavailable_without_a_router(
    client: TestClient,
) -> None:
    body = client.get(
        "/api/v1/parking/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng}
    ).json()
    assert body["meta"]["walking"] == "unavailable"
    assert body["meta"]["pool_size"] == 3
    assert all(r["walk_seconds"] is None for r in body["results"])


def test_travel_times_reorder_results_by_walking_time() -> None:
    class Router:
        def travel_times(self, origin, destinations, mode):  # type: ignore[no-untyped-def]
            from yimmparking.domain.model import RouteTime

            # make the *farther* plain lot the quicker walk
            times = {"taipei:b": 900, "taipei:a": 300, "taipei:c": 60}
            return {i: RouteTime(times[i], times[i] * 2) for i, _ in destinations}

    container = build("k", router=Router())
    with TestClient(create_app(container=container)) as c:
        body = c.get(
            "/api/v1/parking/nearby",
            params={"lat": CENTER.lat, "lng": CENTER.lng, "mode": "distance"},
        ).json()
        assert body["meta"]["walking"] == "google"
        assert [r["name"] for r in body["results"]] == [
            "台灣聯通松高站",
            "嘟嘟房市府站停車場",
            "一般停車場",
        ]
        first = body["results"][0]
        assert first["walk_seconds"] == 60
        assert first["walk_meters"] == 120
        assert "bike_seconds" not in first
        assert first["distance_m"] > 0  # the straight-line figure is still reported
    container.close()


class _BikeFeed:
    def __init__(
        self, stations: list[BikeStation] | Exception, city: City = City.TAIPEI
    ) -> None:
        self._stations = stations
        self.city = city

    def fetch_stations(self) -> list[BikeStation]:
        if isinstance(self._stations, Exception):
            raise self._stations
        return self._stations


def _bike(sno: str, lat: float, rent: int | None = 4) -> BikeStation:
    return BikeStation(
        id=f"taipei:{sno}",
        city=City.TAIPEI,
        name=f"站{sno}",
        address="某路",
        location=GeoPoint(lat, CENTER.lng),
        active=True,
        rent=rent,
        ret=6,
        observed_at=NOW,
    )


def test_bikes_nearby_lists_stations_by_distance() -> None:
    feed = _BikeFeed([_bike("far", CENTER.lat + 0.003), _bike("near", CENTER.lat + 0.001, rent=0)])
    container = build("k", bike_feeds=[feed])
    with TestClient(create_app(container=container)) as c:
        body = c.get("/api/v1/bikes/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng}).json()
    container.close()
    assert (body["radius_m"], body["expanded"]) == (400, False)
    assert body["unavailable_cities"] == []
    assert [r["name"] for r in body["results"]] == ["站near", "站far"]
    near = body["results"][0]
    assert near["rent"] == 0 and near["ret"] == 6  # zero is a real reading, not "no data"
    assert 100 <= near["distance_m"] <= 120


def test_bikes_nearby_widens_and_reports_it() -> None:
    container = build("k", bike_feeds=[_BikeFeed([_bike("a", CENTER.lat + 0.005)])])  # ~556 m
    with TestClient(create_app(container=container)) as c:
        body = c.get("/api/v1/bikes/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng}).json()
    container.close()
    assert (body["radius_m"], body["expanded"], len(body["results"])) == (800, True, 1)


def test_bikes_nearby_says_unavailable_when_the_feed_is_down() -> None:
    container = build("k", bike_feeds=[_BikeFeed(SourceError("down"))])
    with TestClient(create_app(container=container)) as c:
        r = c.get("/api/v1/bikes/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng})
    container.close()
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "bikes_unavailable"


def test_bikes_nearby_lists_the_readable_city_when_the_other_is_down() -> None:
    feeds = [
        _BikeFeed([_bike("a", CENTER.lat + 0.001)]),
        _BikeFeed(SourceError("down"), city=City.NEW_TAIPEI),
    ]
    container = build("k", bike_feeds=feeds)
    with TestClient(create_app(container=container)) as c:
        r = c.get("/api/v1/bikes/nearby", params={"lat": CENTER.lat, "lng": CENTER.lng})
    container.close()
    assert r.status_code == 200
    assert [s["name"] for s in r.json()["results"]] == ["站a"]
    assert r.json()["unavailable_cities"] == ["new_taipei"]


def test_food_accepts_the_search_origin(client: TestClient) -> None:
    r = client.get(
        "/api/v1/food/nearby",
        params={"lat": CENTER.lat, "lng": CENTER.lng, "origin_lat": 25.05, "origin_lng": 121.55},
    )
    assert r.status_code == 200
    first = r.json()["results"][0]
    assert "walk_seconds" in first


def test_vendor_settings_set_the_order_and_the_count(client: TestClient) -> None:
    none_first = "liantong:0,iparking_dodohome:0,dodohome:0,times:0,uspace:0"
    body = client.get(
        "/api/v1/parking/nearby",
        params={"lat": CENTER.lat, "lng": CENTER.lng, "vendors": none_first},
    ).json()
    assert all(r["block"] != "priority" for r in body["results"])  # nothing shown first

    liantong_first = "liantong:1,iparking_dodohome:2"
    body = client.get(
        "/api/v1/parking/nearby",
        params={"lat": CENTER.lat, "lng": CENTER.lng, "vendors": liantong_first},
    ).json()
    priority = [r["vendor"] for r in body["results"] if r["block"] == "priority"]
    assert priority[:2] == ["liantong", "iparking_dodohome"]


@pytest.mark.parametrize(
    "vendors",
    [
        "和停:2",  # a small operator cannot be added
        "dodohome:2,dodohome:1",  # listed twice
        "liantong:9",  # more than the maximum
        "liantong:-1",
        "liantong:two",
    ],
)
def test_invalid_vendor_settings_are_refused(client: TestClient, vendors: str) -> None:
    r = client.get(
        "/api/v1/parking/nearby",
        params={"lat": CENTER.lat, "lng": CENTER.lng, "vendors": vendors},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_vendors"
