from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from yimmparking.adapters.sources.youbike import (
    NewTaipeiBikeFeed,
    TaipeiBikeFeed,
    parse_new_taipei,
    parse_taipei,
)
from yimmparking.application.ports import SourceError
from yimmparking.application.search_bikes import MAX_STALE, SearchNearbyBikes
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import BikeStation, City

# Rows copied from the live feeds (2026-10-14); note the differing names and value types.
TAIPEI_ROW = {
    "sno": "500101001",
    "sna": "YouBike2.0_捷運科技大樓站",
    "sarea": "大安區",
    "mday": "2026-10-14 19:18:04",
    "ar": "復興南路二段235號前",
    "act": "1",
    "infoTime": "2026-10-14 19:18:04",
    "Quantity": 28,
    "available_rent_bikes": 8,
    "latitude": 25.02605,
    "longitude": 121.5436,
    "available_return_bikes": 20,
}
NEW_TAIPEI_ROW = {
    "sna": "YouBike2.0_八里行政中心",
    "sarea": "八里區",
    "ar": "十三行路",
    "sno": "500201002",
    "tot_quantity": "20",
    "sbi_quantity": "10",
    "mday": "20261014T191402",
    "lat": "25.15397",
    "lng": "121.40721",
    "bemp": "10",
    "act": "1",
}

NOW = datetime(2026, 10, 14, 11, 20, tzinfo=UTC)
ORIGIN = GeoPoint(25.0260, 121.5436)


class Clock:
    def __init__(self) -> None:
        self.at = NOW

    def now(self) -> datetime:
        return self.at


class Feed:
    def __init__(self, stations: list[BikeStation] | Exception, city: City = City.TAIPEI) -> None:
        self.city = city
        self.stations = stations
        self.calls = 0

    def fetch_stations(self) -> list[BikeStation]:
        self.calls += 1
        if isinstance(self.stations, Exception):
            raise self.stations
        return self.stations


def station(sno: str, north_m: float, *, active: bool = True, rent: int | None = 3) -> BikeStation:
    # ~111 km per degree of latitude, so this lands `north_m` metres north of ORIGIN.
    return BikeStation(
        id=f"taipei:{sno}",
        city=City.TAIPEI,
        name=sno,
        address="",
        location=GeoPoint(ORIGIN.lat + north_m / 111_195, ORIGIN.lng),
        active=active,
        rent=rent,
        ret=5,
    )


def test_taipei_row_is_parsed() -> None:
    s = parse_taipei(TAIPEI_ROW)
    assert s is not None
    assert (s.id, s.name, s.active) == ("taipei:500101001", "捷運科技大樓站", True)
    assert (s.rent, s.ret, s.total) == (8, 20, 28)
    assert s.location == GeoPoint(25.02605, 121.5436)
    # The feed's clock is Taiwan local time.
    assert s.observed_at == datetime(2026, 10, 14, 11, 18, 4, tzinfo=UTC)


def test_new_taipei_row_with_string_values_is_parsed() -> None:
    s = parse_new_taipei(NEW_TAIPEI_ROW)
    assert s is not None
    assert (s.id, s.name) == ("new_taipei:500201002", "八里行政中心")
    assert (s.rent, s.ret, s.total) == (10, 10, 20)
    assert s.location == GeoPoint(25.15397, 121.40721)
    assert s.observed_at == datetime(2026, 10, 14, 11, 14, 2, tzinfo=UTC)


def test_inactive_and_unreadable_rows() -> None:
    closed = parse_taipei({**TAIPEI_ROW, "act": "0"})
    assert closed is not None and closed.active is False
    # A negative or missing count is "no reading", never zero bikes.
    nodata = parse_taipei({**TAIPEI_ROW, "available_rent_bikes": -9, "available_return_bikes": None})
    assert nodata is not None and (nodata.rent, nodata.ret) == (None, None)
    assert parse_taipei({**TAIPEI_ROW, "latitude": None}) is None
    assert parse_taipei({**TAIPEI_ROW, "latitude": 0, "longitude": 0}) is None  # outside Taiwan
    assert parse_taipei({**TAIPEI_ROW, "sno": ""}) is None


def test_feeds_fetch_and_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "tcgbusfs" in str(request.url):
            return httpx.Response(200, json=[TAIPEI_ROW, {"junk": 1}])
        assert request.url.params["page"] == "0"
        return httpx.Response(200, json=[NEW_TAIPEI_ROW])

    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert [s.id for s in TaipeiBikeFeed(http).fetch_stations()] == ["taipei:500101001"]
    assert [s.id for s in NewTaipeiBikeFeed(http).fetch_stations()] == ["new_taipei:500201002"]


def test_an_empty_or_broken_feed_is_an_error() -> None:
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(SourceError):
        TaipeiBikeFeed(http).fetch_stations()
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(SourceError):
        NewTaipeiBikeFeed(http).fetch_stations()


def test_stations_within_400m_win_and_are_sorted_and_capped() -> None:
    stations = [station(f"s{n}", 50 * n) for n in range(1, 8)] + [station("far", 600)]
    found = SearchNearbyBikes([Feed(stations)], Clock()).execute(ORIGIN)  # type: ignore[list-item]
    assert (found.radius_m, found.expanded) == (400, False)
    assert [h.station.name for h in found.hits] == ["s1", "s2", "s3", "s4", "s5"]
    assert found.hits[0].distance_m == pytest.approx(50, abs=2)


def test_widens_to_800m_only_when_400m_is_empty() -> None:
    stations = [station("a", 450), station("b", 700), station("c", 900)]
    found = SearchNearbyBikes([Feed(stations)], Clock()).execute(ORIGIN)  # type: ignore[list-item]
    assert (found.radius_m, found.expanded) == (800, True)
    assert [h.station.name for h in found.hits] == ["a", "b"]


def test_nothing_within_800m() -> None:
    found = SearchNearbyBikes([Feed([station("far", 900)])], Clock()).execute(ORIGIN)  # type: ignore[list-item]
    assert (found.radius_m, found.expanded, found.hits) == (800, True, ())


def test_inactive_stations_are_not_listed() -> None:
    stations = [station("closed", 50, active=False), station("open", 300)]
    found = SearchNearbyBikes([Feed(stations)], Clock()).execute(ORIGIN)  # type: ignore[list-item]
    assert [h.station.name for h in found.hits] == ["open"]


def test_a_station_with_no_reading_is_still_listed_as_no_data() -> None:
    found = SearchNearbyBikes([Feed([station("x", 50, rent=None)])], Clock()).execute(ORIGIN)  # type: ignore[list-item]
    assert found.hits[0].station.rent is None


def test_feed_is_cached_then_refreshed() -> None:
    feed, clock = Feed([station("a", 50)]), Clock()
    search = SearchNearbyBikes([feed], clock)  # type: ignore[list-item]
    search.execute(ORIGIN)
    search.execute(ORIGIN)
    assert feed.calls == 1
    clock.at = NOW + timedelta(seconds=61)
    search.execute(ORIGIN)
    assert feed.calls == 2


def test_failed_refresh_serves_the_last_copy_for_a_while_then_errors() -> None:
    feed, clock = Feed([station("a", 50)]), Clock()
    search = SearchNearbyBikes([feed], clock)  # type: ignore[list-item]
    search.execute(ORIGIN)
    feed.stations = SourceError("down")
    clock.at = NOW + timedelta(minutes=5)
    assert search.execute(ORIGIN).hits  # last copy
    clock.at = NOW + MAX_STALE + timedelta(seconds=1)
    with pytest.raises(SourceError):
        search.execute(ORIGIN)


def test_first_load_failure_is_an_error() -> None:
    with pytest.raises(SourceError):
        SearchNearbyBikes([Feed(SourceError("down"))], Clock()).execute(ORIGIN)  # type: ignore[list-item]


def test_one_city_down_still_lists_the_other_and_says_which_is_missing() -> None:
    taipei = Feed([station("a", 50)])
    new_taipei = Feed(SourceError("down"), city=City.NEW_TAIPEI)
    found = SearchNearbyBikes([taipei, new_taipei], Clock()).execute(ORIGIN)  # type: ignore[list-item]
    assert [h.station.name for h in found.hits] == ["a"]
    assert found.missing == (City.NEW_TAIPEI,)


def test_nothing_missing_when_every_feed_reads() -> None:
    found = SearchNearbyBikes([Feed([station("a", 50)])], Clock()).execute(ORIGIN)  # type: ignore[list-item]
    assert found.missing == ()


def test_a_failed_feed_is_not_asked_again_until_the_ttl_passes() -> None:
    taipei = Feed([station("a", 50)])
    new_taipei = Feed(SourceError("down"), city=City.NEW_TAIPEI)
    clock = Clock()
    search = SearchNearbyBikes([taipei, new_taipei], clock)  # type: ignore[list-item]
    for _ in range(3):
        search.execute(ORIGIN)
    assert new_taipei.calls == 1  # an outage does not make every request wait for it

    clock.at = NOW + timedelta(seconds=61)
    new_taipei.stations = [station("b", 80)]
    found = search.execute(ORIGIN)
    assert new_taipei.calls == 2
    assert found.missing == ()
