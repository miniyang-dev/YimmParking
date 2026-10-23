"""Taipei's counts fall back to TDX's off-street data while the city's own feed has stopped.

`tdx_offstreet_availability.json` is a real TDX answer recorded on 2026-10-23 (three rows kept).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.adapters.tdx.client import TdxClient
from yimmparking.adapters.tdx.offstreet import TdxOffStreetAvailability
from yimmparking.application.fallback import PRIMARY_MAX_AGE, FallbackFeed
from yimmparking.application.ports import SourceError
from yimmparking.application.search import SearchNearbyParking
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import (
    AvailabilityBatch,
    AvailabilityReading,
    AvailabilitySource,
    City,
    ParkingLot,
)

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "tdx_offstreet_availability.json").read_text(
        encoding="utf-8"
    )
)
ROWS = FIXTURE["ParkingAvailabilities"]
NOW = datetime(2026, 10, 23, 4, 50, tzinfo=UTC)  # 12:50 Taipei, just after the recording


def tdx_answering(body: Any) -> TdxClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 86400})
        return httpx.Response(200, json=body)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return TdxClient(http, "id", "secret", token_url="https://tdx.example/token", api_base="https://tdx.example/api")


class TestOffStreet:
    def test_car_counts_per_car_park_with_the_newest_collection_time(self) -> None:
        batch = TdxOffStreetAvailability(tdx_answering(FIXTURE), City.TAIPEI).fetch_availability()
        counts = {r.lot_id: r.count for r in batch.readings}
        # The car-space reading (SpaceType 1), not the all-types total that adds scooters.
        assert counts == {"taipei:TPE0096": 938, "taipei:TPE0070": 412, "taipei:TPE0567": 4}
        assert batch.observed_at == datetime(2026, 10, 23, 4, 47, 45, tzinfo=UTC)
        assert batch.source is AvailabilitySource.TDX and batch.city is City.TAIPEI

    def test_a_car_park_whose_own_reporting_stopped_has_no_count(self) -> None:
        rows = [dict(ROWS[0]), {**ROWS[1], "DataCollectTime": "2026-10-23T11:00:00+08:00"}]
        batch = TdxOffStreetAvailability(
            tdx_answering({"ParkingAvailabilities": rows}), City.TAIPEI
        ).fetch_availability()
        counts = {r.lot_id: r.count for r in batch.readings}
        assert counts == {"taipei:TPE0096": 938, "taipei:TPE0070": None}

    def test_minus_one_and_scooter_only_are_no_car_count(self) -> None:
        unknown = {**ROWS[0], "Availabilities": [{"SpaceType": 1, "NumberOfSpaces": 9, "AvailableSpaces": -1}]}
        scooters = {**ROWS[1], "Availabilities": [{"SpaceType": 2, "NumberOfSpaces": 50, "AvailableSpaces": 20}]}
        batch = TdxOffStreetAvailability(
            tdx_answering({"ParkingAvailabilities": [unknown, scooters]}), City.TAIPEI
        ).fetch_availability()
        assert [r.count for r in batch.readings] == [None, None]

    def test_an_answer_without_times_is_an_error(self) -> None:
        rows = [{k: v for k, v in ROWS[0].items() if k != "DataCollectTime"}]
        with pytest.raises(SourceError):
            TdxOffStreetAvailability(
                tdx_answering({"ParkingAvailabilities": rows}), City.TAIPEI
            ).fetch_availability()


# ---- choosing between the city's feed and the backup -------------------------------------------


class Clock:
    def now(self) -> datetime:
        return NOW


def batch(at: datetime, count: int, source: AvailabilitySource) -> AvailabilityBatch:
    return AvailabilityBatch(
        City.TAIPEI, at, (AvailabilityReading("taipei:TPE0096", count),), source=source
    )


class Feed:
    def __init__(self, result: AvailabilityBatch | Exception) -> None:
        self.city = City.TAIPEI
        self.result = result
        self.calls = 0

    def fetch_lots(self) -> list[ParkingLot]:
        return []

    def fetch_availability(self) -> AvailabilityBatch:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


CITY_NOW = batch(NOW - timedelta(minutes=6), 900, AvailabilitySource.CITY)
CITY_STUCK = batch(datetime(2026, 10, 19, 2, 26, tzinfo=UTC), 100, AvailabilitySource.CITY)
TDX_NOW = batch(NOW - timedelta(minutes=2), 938, AvailabilitySource.TDX)


class TestFallback:
    def test_the_citys_own_feed_is_used_while_it_is_current(self) -> None:
        backup = Feed(TDX_NOW)
        assert FallbackFeed(Feed(CITY_NOW), backup, Clock()).fetch_availability() is CITY_NOW
        assert backup.calls == 0  # TDX is not asked at all

    def test_a_stuck_city_feed_gives_way_to_the_backup(self) -> None:
        got = FallbackFeed(Feed(CITY_STUCK), Feed(TDX_NOW), Clock()).fetch_availability()
        assert got is TDX_NOW

    def test_a_failing_city_feed_gives_way_to_the_backup(self) -> None:
        got = FallbackFeed(Feed(SourceError("down")), Feed(TDX_NOW), Clock()).fetch_availability()
        assert got is TDX_NOW

    def test_with_both_down_the_old_city_reading_is_still_returned(self) -> None:
        got = FallbackFeed(Feed(CITY_STUCK), Feed(SourceError("429")), Clock()).fetch_availability()
        assert got is CITY_STUCK  # the freshness rules will show it as no data

    def test_with_nothing_readable_it_is_an_error(self) -> None:
        feed = FallbackFeed(Feed(SourceError("down")), Feed(SourceError("429")), Clock())
        with pytest.raises(SourceError, match="backup failed too"):
            feed.fetch_availability()

    def test_it_goes_back_to_the_city_once_it_moves_again(self) -> None:
        primary = Feed(CITY_STUCK)
        feed = FallbackFeed(primary, Feed(TDX_NOW), Clock())
        assert feed.fetch_availability() is TDX_NOW
        primary.result = CITY_NOW
        assert feed.fetch_availability() is CITY_NOW

    def test_the_threshold_is_well_past_the_citys_normal_lag(self) -> None:
        assert timedelta(minutes=20) <= PRIMARY_MAX_AGE

    def test_a_backup_for_another_city_is_refused(self) -> None:
        other = Feed(TDX_NOW)
        other.city = City.NEW_TAIPEI
        with pytest.raises(ValueError):
            FallbackFeed(Feed(CITY_NOW), other, Clock())  # type: ignore[arg-type]


# ---- the source travels to the search result ---------------------------------------------------


def test_the_search_says_where_each_count_came_from() -> None:
    store = SqliteStore(":memory:")
    lots = [
        ParkingLot("taipei:TPE0096", City.TAIPEI, "TPE0096", "府前廣場", "", "", GeoPoint(25.0375, 121.5637)),
        ParkingLot("taipei:TPE0070", City.TAIPEI, "TPE0070", "松壽廣場", "", "", GeoPoint(25.0376, 121.5637)),
    ]
    store.replace_lots(City.TAIPEI, lots)
    store.record_availability(
        AvailabilityBatch(City.TAIPEI, NOW - timedelta(minutes=3), (AvailabilityReading("taipei:TPE0070", 7),))
    )
    store.record_availability(TDX_NOW)

    hits = SearchNearbyParking(store, Clock()).execute(GeoPoint(25.0375, 121.5637)).hits
    sources = {h.ranked.lot.id: (h.availability.count, h.availability.source) for h in hits}
    assert sources == {
        "taipei:TPE0096": (938, AvailabilitySource.TDX),
        "taipei:TPE0070": (7, AvailabilitySource.CITY),
    }
    assert store.latest_source(City.TAIPEI) is AvailabilitySource.TDX
    assert store.latest_source(City.NEW_TAIPEI) is None
    store.close()


def test_the_backup_is_read_at_most_once_per_interval() -> None:
    class Ticking(Clock):
        def __init__(self) -> None:
            self.at = NOW

        def now(self) -> datetime:
            return self.at

    clock = Ticking()
    backup = Feed(TDX_NOW)
    feed = FallbackFeed(Feed(CITY_STUCK), backup, clock, backup_interval=timedelta(minutes=30))
    for minutes in (0, 2, 10, 28):
        clock.at = NOW + timedelta(minutes=minutes)
        assert feed.fetch_availability() is TDX_NOW
    assert backup.calls == 1  # the last answer is served in between, at no cost
    clock.at = NOW + timedelta(minutes=31)
    feed.fetch_availability()
    assert backup.calls == 2
