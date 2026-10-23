"""On-street parking from TDX: token handling, paging, parsing, and the nearby search.

The fixtures are real TDX answers recorded on 2026-10-23 (wrapper kept, a few telling rows picked):
note the list is named per endpoint (`ParkingSegments`, `CurbParkingSegmentAvailabilities`), not
`Items` as the OpenAPI document says.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from yimmparking.adapters.tdx.client import PAGE_SIZE, TdxClient, _rows
from yimmparking.adapters.tdx.curb import TdxCurbFeed, parse_availability, parse_segment
from yimmparking.application.ports import CurbUnconfigured, SourceError
from yimmparking.application.search_curb import LIVE_TTL, MAX_STALE, SearchNearbyCurb
from yimmparking.domain.curb import (
    CurbFullness,
    CurbReading,
    CurbSegment,
    CurbService,
    SpaceKind,
)
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import City

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SEGMENTS = json.loads((FIXTURES / "tdx_curb_segments.json").read_text(encoding="utf-8"))
LIVE = json.loads((FIXTURES / "tdx_curb_availability.json").read_text(encoding="utf-8"))
LIVE_NTPC = json.loads(
    (FIXTURES / "tdx_curb_availability_newtaipei.json").read_text(encoding="utf-8")
)
SEGMENT_ROWS = SEGMENTS["ParkingSegments"]
LIVE_ROWS = LIVE["CurbParkingSegmentAvailabilities"]
LIVE_NTPC_ROWS = LIVE_NTPC["CurbParkingSegmentAvailabilities"]
TOKEN_URL = "https://tdx.example/token"
API = "https://tdx.example/api"


class Tdx:
    """A stand-in TDX: counts token requests and records data requests."""

    def __init__(self, *, token_status: int = 200, expires_in: int = 86400) -> None:
        self.tokens = 0
        self.token_status = token_status
        self.expires_in = expires_in
        self.data: list[httpx.Request] = []
        self.pages: dict[str, list[list[dict[str, Any]]]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            self.tokens += 1
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["client_credentials"]
            assert form["client_id"] == ["id"] and form["client_secret"] == ["secret"]
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_client"})
            return httpx.Response(
                200, json={"access_token": f"tok{self.tokens}", "expires_in": self.expires_in}
            )
        self.data.append(request)
        path = request.url.path
        if "ParkingSegmentAvailability" in path:
            return httpx.Response(200, json=LIVE)
        if path in self.pages:
            skip = int(request.url.params["$skip"])
            pages = self.pages[path]
            index = skip // PAGE_SIZE
            rows = pages[index] if index < len(pages) else []
            return httpx.Response(200, json={"ParkingSegments": rows})
        return httpx.Response(200, json=SEGMENTS)


class Clock:
    def __init__(self) -> None:
        self.at = datetime(2026, 10, 22, 3, 30, tzinfo=UTC)
        self.mono = 0.0

    def now(self) -> datetime:
        return self.at

    def monotonic(self) -> float:
        return self.mono


def client(tdx: Tdx, clock: Clock | None = None, *, secret: str | None = "secret") -> TdxClient:
    http = httpx.Client(transport=httpx.MockTransport(tdx))
    return TdxClient(
        http,
        "id",
        secret,
        token_url=TOKEN_URL,
        api_base=API,
        monotonic=(clock or Clock()).monotonic,
    )


class TestClient:
    def test_one_token_serves_many_calls_and_is_renewed_before_it_expires(self) -> None:
        tdx, clock = Tdx(expires_in=3600), Clock()
        feed = TdxCurbFeed(client(tdx, clock), City.TAIPEI)
        feed.fetch_segments()
        feed.fetch_availability(["taipei:1002053"])
        assert tdx.tokens == 1
        assert tdx.data[0].headers["authorization"] == "Bearer tok1"

        clock.mono += 3600 - 300  # inside the renewal margin
        feed.fetch_availability(["taipei:1002053"])
        assert tdx.tokens == 2
        assert tdx.data[-1].headers["authorization"] == "Bearer tok2"

    def test_requests_ask_for_json_and_name_the_city(self) -> None:
        tdx = Tdx()
        TdxCurbFeed(client(tdx), City.NEW_TAIPEI).fetch_segments()
        [request] = tdx.data
        assert request.url.path == "/api/v1/Parking/OnStreet/ParkingSegment/City/NewTaipei"
        assert request.url.params["$format"] == "JSON"
        assert request.url.params["$top"] == str(PAGE_SIZE)

    def test_every_page_is_read(self) -> None:
        tdx = Tdx()
        path = "/api/v1/Parking/OnStreet/ParkingSegment/City/Taipei"
        row = SEGMENT_ROWS[0]
        tdx.pages[path] = [[row] * PAGE_SIZE, [row] * 3]
        rows = client(tdx).get_items("v1/Parking/OnStreet/ParkingSegment/City/Taipei")
        assert len(rows) == PAGE_SIZE + 3
        assert [r.url.params["$skip"] for r in tdx.data] == ["0", str(PAGE_SIZE)]

    def test_live_counts_are_asked_for_the_named_segments_of_this_city_only(self) -> None:
        tdx = Tdx()
        readings = TdxCurbFeed(client(tdx), City.TAIPEI).fetch_availability(
            ["taipei:1002053", "taipei:1003059", "new_taipei:N34", "taipei:O'1"]
        )
        [request] = tdx.data
        assert request.url.path.endswith("/ParkingSegmentAvailability/City/Taipei")
        assert request.url.params["$filter"] == (
            "ParkingSegmentID eq '1002053' or ParkingSegmentID eq '1003059'"
            " or ParkingSegmentID eq 'O''1'"
        )
        assert "taipei:1002053" in readings  # parsed as before, keyed by our id

    def test_no_segments_of_this_city_means_no_call(self) -> None:
        tdx = Tdx()
        assert TdxCurbFeed(client(tdx), City.TAIPEI).fetch_availability(["new_taipei:N34"]) == {}
        assert tdx.data == [] and tdx.tokens == 0

    def test_without_credentials_nothing_is_sent(self) -> None:
        tdx = Tdx()
        with pytest.raises(CurbUnconfigured):
            TdxCurbFeed(client(tdx, secret=None), City.TAIPEI).fetch_segments()
        assert tdx.tokens == 0 and tdx.data == []

    def test_a_refused_token_is_an_error_that_does_not_repeat_the_secret(self) -> None:
        with pytest.raises(SourceError) as caught:
            TdxCurbFeed(client(Tdx(token_status=401)), City.TAIPEI).fetch_segments()
        assert "401" in str(caught.value) and "secret" not in str(caught.value)


class TestParsing:
    def test_segment_name_position_and_fare(self) -> None:
        segment = parse_segment(SEGMENT_ROWS[0], City.TAIPEI)
        assert segment == CurbSegment(
            id="taipei:3060034",
            city=City.TAIPEI,
            name="辛亥路1段34巷",
            location=GeoPoint(25.01988, 121.52993),
            description="辛亥路1段34巷(辛亥路一段到羅斯福路三段269巷)",
            fare="20元(09:00-17:00)",
            town="",  # TDX gives no TownName for Taipei
        )

    def test_a_segment_without_a_position_is_dropped(self) -> None:
        row = {k: v for k, v in SEGMENT_ROWS[0].items() if k != "ParkingSegmentPosition"}
        assert parse_segment(row, City.TAIPEI) is None

    def test_a_car_segment_with_free_spaces(self) -> None:
        reading = parse_availability(LIVE_ROWS[0], City.TAIPEI)
        assert reading is not None
        assert (reading.total, reading.available, reading.kind) == (9, 4, SpaceKind.CAR)
        assert reading.fullness is CurbFullness.AVAILABLE
        assert reading.service is CurbService.OPEN
        assert reading.observed_at == datetime(2026, 10, 23, 5, 0, tzinfo=UTC)

    def test_a_full_segment(self) -> None:
        reading = parse_availability(LIVE_ROWS[1], City.TAIPEI)
        assert reading is not None
        assert (reading.available, reading.fullness) == (0, CurbFullness.FULL)

    def test_minus_one_is_unknown_never_zero(self) -> None:
        # Real rows carry -1 in the count and in FullStatus (a value the document does not list).
        reading = parse_availability(LIVE_ROWS[2], City.TAIPEI)
        assert reading is not None
        assert (reading.total, reading.available, reading.kind) == (2, None, SpaceKind.CAR)
        assert reading.fullness is CurbFullness.UNKNOWN

    def test_a_scooter_only_segment_is_no_place_for_a_car(self) -> None:
        reading = parse_availability(LIVE_ROWS[3], City.TAIPEI)  # "太原路B(含機車)": type 2 only
        assert reading is not None
        assert (reading.total, reading.available, reading.kind) == (None, None, SpaceKind.NO_CAR)

    def test_new_taipei_counts_cars_apart_from_other_space_types(self) -> None:
        # 40 car spaces all taken; the row's own total (7 free) counts other types too.
        mixed = parse_availability(LIVE_NTPC_ROWS[0], City.NEW_TAIPEI)
        assert mixed is not None
        assert (mixed.total, mixed.available, mixed.kind) == (40, 0, SpaceKind.CAR)
        scooters = parse_availability(LIVE_NTPC_ROWS[1], City.NEW_TAIPEI)
        assert scooters is not None and scooters.kind is SpaceKind.NO_CAR

    def test_without_a_breakdown_the_all_types_total_is_used_and_said(self) -> None:
        row = {**LIVE_ROWS[0], "Availabilities": [], "TotalSpaces": 15, "AvailableSpaces": 6}
        reading = parse_availability(row, City.TAIPEI)
        assert reading is not None
        assert (reading.total, reading.available, reading.kind) == (15, 6, SpaceKind.ALL)

    def test_unexpected_status_codes_are_unknown(self) -> None:
        row = {**LIVE_ROWS[0], "FullStatus": 9, "ServiceStatus": None}
        reading = parse_availability(row, City.TAIPEI)
        assert reading is not None
        assert reading.fullness is CurbFullness.UNKNOWN
        assert reading.service is CurbService.UNKNOWN


# ---- the nearby search ------------------------------------------------------------------------

ORIGIN = GeoPoint(25.0375, 121.5637)


def segment(sid: str, north_m: float, city: City = City.TAIPEI) -> CurbSegment:
    return CurbSegment(
        id=f"{city.value}:{sid}",
        city=city,
        name=sid,
        location=GeoPoint(ORIGIN.lat + north_m / 111_195, ORIGIN.lng),
    )


def reading(sid: str, available: int | None, city: City = City.TAIPEI) -> CurbReading:
    return CurbReading(
        segment_id=f"{city.value}:{sid}",
        total=10,
        available=available,
        kind=SpaceKind.CAR,
        fullness=CurbFullness.AVAILABLE,
        service=CurbService.OPEN,
        observed_at=None,
    )


class Feed:
    def __init__(
        self,
        segments: list[CurbSegment] | Exception,
        live: dict[str, CurbReading] | Exception,
        city: City = City.TAIPEI,
    ) -> None:
        self.city, self.segments, self.live = city, segments, live
        self.segment_calls = self.live_calls = 0
        self.asked: list[list[str]] = []

    def fetch_segments(self) -> list[CurbSegment]:
        self.segment_calls += 1
        if isinstance(self.segments, Exception):
            raise self.segments
        return self.segments

    def fetch_availability(self, segment_ids: list[str]) -> dict[str, CurbReading]:
        self.live_calls += 1
        self.asked.append(list(segment_ids))
        if isinstance(self.live, Exception):
            raise self.live
        return {i: r for i, r in self.live.items() if i in segment_ids}


class TestSearch:
    def test_nearest_segments_with_their_live_counts(self) -> None:
        feed = Feed(
            [segment("far", 700), segment("b", 250), segment("a", 100)],
            {"taipei:a": reading("a", 3)},
        )
        found = SearchNearbyCurb([feed], Clock()).execute(ORIGIN)  # type: ignore[list-item]
        assert (found.radius_m, found.expanded) == (300, False)
        assert [h.segment.name for h in found.hits] == ["a", "b"]
        assert found.hits[0].reading is not None and found.hits[0].reading.available == 3
        assert found.hits[1].reading is None  # no live count: "no data", not zero

    def test_widens_once_when_nothing_is_close(self) -> None:
        feed = Feed([segment("x", 450)], {})
        found = SearchNearbyCurb([feed], Clock()).execute(ORIGIN)  # type: ignore[list-item]
        assert (found.radius_m, found.expanded, len(found.hits)) == (600, True, 1)

    def test_segments_are_read_daily_and_counts_every_five_minutes(self) -> None:
        feed, clock = Feed([segment("a", 100)], {}), Clock()
        search = SearchNearbyCurb([feed], clock)  # type: ignore[list-item]
        search.execute(ORIGIN)
        search.execute(ORIGIN)
        assert (feed.segment_calls, feed.live_calls) == (1, 1)
        clock.at += LIVE_TTL
        search.execute(ORIGIN)
        assert (feed.segment_calls, feed.live_calls) == (1, 2)
        clock.at += timedelta(hours=24)
        search.execute(ORIGIN)
        assert feed.segment_calls == 2

    def test_counts_are_asked_only_for_segments_near_the_search(self) -> None:
        feed = Feed([segment("far", 700), segment("b", 250), segment("a", 100)], {})
        SearchNearbyCurb([feed], Clock()).execute(ORIGIN)  # type: ignore[list-item]
        assert feed.asked == [["taipei:a", "taipei:b"]]  # nearest first; 700 m is past 600 m

    def test_a_city_with_nothing_nearby_is_not_asked(self) -> None:
        taipei = Feed([segment("a", 100)], {})
        new_taipei = Feed([segment("n", 5000, City.NEW_TAIPEI)], {}, City.NEW_TAIPEI)
        found = SearchNearbyCurb([taipei, new_taipei], Clock()).execute(ORIGIN)  # type: ignore[list-item]
        assert (taipei.live_calls, new_taipei.live_calls) == (1, 0)
        assert found.missing == ()

    def test_a_search_elsewhere_asks_again_but_a_repeat_does_not(self) -> None:
        feed, clock = Feed([segment("a", 100), segment("z", 3000)], {}), Clock()
        search = SearchNearbyCurb([feed], clock)  # type: ignore[list-item]
        search.execute(ORIGIN)
        search.execute(ORIGIN)
        assert feed.live_calls == 1
        elsewhere = GeoPoint(ORIGIN.lat + 3000 / 111_195, ORIGIN.lng)
        search.execute(elsewhere)
        assert feed.asked[-1] == ["taipei:z"] and feed.live_calls == 2

    def test_a_failed_refresh_serves_the_last_counts_for_a_while(self) -> None:
        feed, clock = Feed([segment("a", 100)], {"taipei:a": reading("a", 3)}), Clock()
        search = SearchNearbyCurb([feed], clock)  # type: ignore[list-item]
        search.execute(ORIGIN)
        feed.live = SourceError("down")
        clock.at += LIVE_TTL
        found = search.execute(ORIGIN)
        assert found.hits[0].reading is not None and found.missing == ()
        clock.at += MAX_STALE
        found = search.execute(ORIGIN)
        assert found.hits[0].reading is None and found.missing == (City.TAIPEI,)

    def test_one_city_down_leaves_the_other_and_says_so(self) -> None:
        taipei = Feed([segment("a", 100)], {})
        new_taipei = Feed(SourceError("down"), SourceError("down"), City.NEW_TAIPEI)
        found = SearchNearbyCurb([taipei, new_taipei], Clock()).execute(ORIGIN)  # type: ignore[list-item]
        assert [h.segment.name for h in found.hits] == ["a"]
        assert found.missing == (City.NEW_TAIPEI,)

    def test_live_counts_down_still_lists_segments_without_counts(self) -> None:
        feed = Feed([segment("a", 100)], SourceError("down"))
        found = SearchNearbyCurb([feed], Clock()).execute(ORIGIN)  # type: ignore[list-item]
        assert found.hits[0].reading is None and found.missing == (City.TAIPEI,)

    def test_nothing_readable_is_an_error(self) -> None:
        feed = Feed(SourceError("down"), SourceError("down"))
        with pytest.raises(SourceError):
            SearchNearbyCurb([feed], Clock()).execute(ORIGIN)  # type: ignore[list-item]

    def test_without_credentials_it_says_unconfigured(self) -> None:
        with pytest.raises(CurbUnconfigured):
            SearchNearbyCurb([], Clock(), configured=False).execute(ORIGIN)


def test_a_failed_token_fails_fast_for_a_minute_then_is_tried_again() -> None:
    tdx, clock = Tdx(token_status=500), Clock()
    tdx_client = client(tdx, clock)
    for _ in range(3):
        with pytest.raises(SourceError):
            tdx_client.get_items("v1/x")
    assert tdx.tokens == 1  # the second city of a search does not wait out another timeout
    clock.mono += 61
    tdx.token_status = 200
    assert tdx_client.get_items("v1/Parking/OnStreet/ParkingSegment/City/Taipei")
    assert tdx.tokens == 2


def test_segments_that_failed_are_tried_again_after_minutes_not_a_day() -> None:
    feed, clock = Feed(SourceError("down"), {}), Clock()
    search = SearchNearbyCurb([feed], clock)  # type: ignore[list-item]
    with pytest.raises(SourceError):
        search.execute(ORIGIN)
    feed.segments = [segment("a", 100)]
    clock.at += timedelta(minutes=3)
    assert [h.segment.name for h in search.execute(ORIGIN).hits] == ["a"]


def test_scooter_only_segments_are_not_listed() -> None:
    no_car = CurbReading(
        "taipei:s", None, None, SpaceKind.NO_CAR, CurbFullness.AVAILABLE, CurbService.OPEN, None
    )
    feed = Feed([segment("s", 50), segment("a", 100)], {"taipei:s": no_car})
    found = SearchNearbyCurb([feed], Clock()).execute(ORIGIN)  # type: ignore[list-item]
    assert [h.segment.name for h in found.hits] == ["a"]


@pytest.mark.parametrize(
    ("body", "rows"),
    [
        ([{"a": 1}], 1),
        ({"Items": [{"a": 1}, {"b": 2}]}, 2),
        ({"UpdateTime": "x", "ParkingSegments": [{"a": 1}]}, 1),
        ({"UpdateTime": "x", "CurbParkingSegmentAvailabilities": []}, 0),
    ],
)
def test_rows_are_found_under_any_wrapper_name(body: object, rows: int) -> None:
    found = _rows(body)
    assert found is not None and len(found) == rows


def test_a_wrapper_with_no_single_list_is_refused() -> None:
    assert _rows({"a": [], "b": []}) is None
    assert _rows("nope") is None
