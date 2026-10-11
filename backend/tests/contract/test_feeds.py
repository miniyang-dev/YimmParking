"""Adapter contract tests against recorded (trimmed) real feed payloads."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from tests.conftest import fixture_bytes
from yimmparking.adapters.iparking.findata import FindataDirectory, parse_stations
from yimmparking.adapters.sources import new_taipei, taipei
from yimmparking.application.ports import SourceError
from yimmparking.domain.brand import BrandClassifier
from yimmparking.domain.model import Brand, BrandEvidence

pytestmark = pytest.mark.contract

Handler = Callable[[httpx.Request], httpx.Response]
ClientFactory = Callable[[Handler], httpx.Client]


class TestTaipeiFeed:
    def feed(self, make_client: ClientFactory) -> taipei.TaipeiFeed:
        def handler(request: httpx.Request) -> httpx.Response:
            body = {
                taipei.DESC_URL: fixture_bytes("taipei_alldesc.json"),
                taipei.AVAILABLE_URL: fixture_bytes("taipei_allavailable.json"),
            }[str(request.url)]
            return httpx.Response(200, content=body)

        return taipei.TaipeiFeed(make_client(handler))

    def test_parses_lots_with_wgs84_locations(self, make_client: ClientFactory) -> None:
        lots = self.feed(make_client).fetch_lots()
        by_source = {lot.source_id: lot for lot in lots}
        expo = by_source["TPE0002"]
        assert expo.id == "taipei:TPE0002"
        assert expo.name == "嘟嘟房世貿一館站停車場"
        assert expo.district == "信義區"
        assert expo.total_car == 335
        assert expo.ev_charging_spaces == 7
        # The published entrance coordinate wins over the TWD97 centroid.
        assert (expo.location.lat, expo.location.lng) == (25.0331, 121.5622)

    def test_all_locations_are_in_taiwan(self, make_client: ClientFactory) -> None:
        for lot in self.feed(make_client).fetch_lots():
            assert 24.9 < lot.location.lat < 25.3
            assert 121.4 < lot.location.lng < 121.7

    def test_update_time_is_taiwan_time_converted_to_utc(self, make_client: ClientFactory) -> None:
        batch = self.feed(make_client).fetch_availability()
        # Fixture says "Sat Oct 10 22:37:00 CST 2026" → 14:37 UTC.
        assert batch.observed_at == datetime(2026, 10, 10, 14, 37, tzinfo=UTC)

    def test_no_data_marker_becomes_none_not_a_number(self, make_client: ClientFactory) -> None:
        raw = json.loads(fixture_bytes("taipei_allavailable.json"))
        had_negative = {p["id"] for p in raw["data"]["park"] if p["availablecar"] < 0}
        assert had_negative, "fixture must contain a -9 reading to make this test meaningful"

        batch = self.feed(make_client).fetch_availability()
        by_id = {r.lot_id: r.count for r in batch.readings}
        for source_id in had_negative:
            assert by_id[f"taipei:{source_id}"] is None
        assert all(c is None or c >= 0 for c in by_id.values())

    def test_brand_by_name_and_by_phone(self, make_client: ClientFactory) -> None:
        classifier = BrandClassifier()
        lots = [classifier.apply(lot) for lot in self.feed(make_client).fetch_lots()]
        by_source = {lot.source_id: lot for lot in lots}
        assert by_source["TPE0001"].brand is Brand.LIANTONG
        assert by_source["TPE0001"].brand_evidence is BrandEvidence.NAME
        by_phone = [lot for lot in lots if lot.brand_evidence is BrandEvidence.PHONE]
        assert by_phone, "fixture should include a lot recognised only by its phone number"
        assert all("嘟嘟房" not in lot.name and "聯通" not in lot.name for lot in by_phone)

    def test_http_error_is_a_source_error(self, make_client: ClientFactory) -> None:
        feed = taipei.TaipeiFeed(make_client(lambda r: httpx.Response(503)))
        with pytest.raises(SourceError):
            feed.fetch_lots()

    def test_unexpected_structure_is_a_source_error(self, make_client: ClientFactory) -> None:
        feed = taipei.TaipeiFeed(make_client(lambda r: httpx.Response(200, json={"oops": 1})))
        with pytest.raises(SourceError):
            feed.fetch_availability()


class TestNewTaipeiFeed:
    fixed = datetime(2026, 10, 10, 14, 40, tzinfo=UTC)

    def feed(self, make_client: ClientFactory) -> new_taipei.NewTaipeiFeed:
        def handler(request: httpx.Request) -> httpx.Response:
            if new_taipei.INFO_DATASET in str(request.url):
                return httpx.Response(200, content=fixture_bytes("ntpc_info.json"))
            return httpx.Response(200, content=fixture_bytes("ntpc_avail.json"))

        return new_taipei.NewTaipeiFeed(make_client(handler), now=lambda: self.fixed)

    def test_duplicate_ids_collapse_to_the_fullest_row(self, make_client: ClientFactory) -> None:
        raw = json.loads(fixture_bytes("ntpc_info.json"))
        ids = [r["ID"] for r in raw]
        assert len(ids) > len(set(ids)), "fixture must contain duplicate ids"

        lots = self.feed(make_client).fetch_lots()
        assert len(lots) == len(set(ids))
        by_source = {lot.source_id: lot for lot in lots}
        # 170120 appears three times; only one row carries the capacity of 1121.
        assert by_source["170120"].total_car == 1121

    def test_locations_converted_from_twd97(self, make_client: ClientFactory) -> None:
        for lot in self.feed(make_client).fetch_lots():
            assert 24.6 < lot.location.lat < 25.3
            assert 121.2 < lot.location.lng < 122.1

    def test_availability_uses_fetch_time_and_none_for_no_data(
        self, make_client: ClientFactory
    ) -> None:
        batch = self.feed(make_client).fetch_availability()
        assert batch.observed_at == self.fixed
        counts = [r.count for r in batch.readings]
        assert any(c is None for c in counts), "fixture should contain a -9 reading"
        assert all(c is None or c >= 0 for c in counts)

    def test_pages_until_a_short_page(self, make_client: ClientFactory) -> None:
        pages: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params["page"])
            pages.append(page)
            full = [
                {"ID": f"{page}{i:05d}"[:6], "NAME": "x", "TW97X": "300000", "TW97Y": "2770000"}
                for i in range(new_taipei.PAGE_SIZE)
            ]
            return httpx.Response(200, json=full if page == 0 else full[:3])

        feed = new_taipei.NewTaipeiFeed(make_client(handler))
        feed.fetch_lots()
        assert pages == [0, 1]


class TestIParkingDirectory:
    def test_parses_stations_with_coordinates(self) -> None:
        html = fixture_bytes("iparking_lots.html").decode("utf-8")
        stations = parse_stations(html)
        assert len(stations) == 8
        first = stations[0]
        assert first.code == "DDHTPC098"
        assert first.name == "四平站"
        assert first.city_code == "TPC"
        assert (first.location.lat, first.location.lng) == (25.052805, 121.535947)

    def test_empty_page_is_an_error_not_an_empty_directory(
        self, make_client: ClientFactory
    ) -> None:
        directory = FindataDirectory(
            make_client(lambda r: httpx.Response(200, text="<html><body>redesigned</body></html>"))
        )
        with pytest.raises(SourceError):
            directory.fetch_stations()
