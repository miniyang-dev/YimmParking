"""YouBike 2.0 real-time station feeds (臺北市 and 新北市 open data, no key required).

The two cities publish different field names and types, so each has its own parser; both
produce the same `BikeStation`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx

from yimmparking.adapters.sources.common import get_json, in_taiwan, to_float, to_int
from yimmparking.application.ports import SourceError
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import BikeStation, City

TAIPEI_URL = "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json"
NEW_TAIPEI_URL = "https://data.ntpc.gov.tw/api/datasets/010e5b15-3823-4b20-b401-b1cf000550c5/json"
PAGE_SIZE = 1000
MAX_PAGES = 10

_TAIWAN_TZ = timezone(timedelta(hours=8))
_NAME_PREFIX = "YouBike2.0_"


def _clean_name(raw: Any) -> str:
    return str(raw or "").strip().removeprefix(_NAME_PREFIX).strip()


def _observed(text: Any, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(str(text).strip(), fmt).replace(tzinfo=_TAIWAN_TZ).astimezone(UTC)
    except ValueError:
        return None


def _point(lat: float | None, lng: float | None) -> GeoPoint | None:
    if lat is None or lng is None:
        return None
    try:
        point = GeoPoint(lat, lng)
    except ValueError:
        return None
    return point if in_taiwan(point) else None


def _reading(value: Any) -> int | None:
    """A count, or None when the feed gave nothing usable. A negative count is a sentinel."""
    count = to_int(value)
    return count if count is not None and count >= 0 else None


def parse_taipei(row: dict[str, Any]) -> BikeStation | None:
    sno = str(row.get("sno") or "").strip()
    point = _point(to_float(row.get("latitude")), to_float(row.get("longitude")))
    if not sno or point is None:
        return None
    return BikeStation(
        id=f"{City.TAIPEI.value}:{sno}",
        city=City.TAIPEI,
        name=_clean_name(row.get("sna")),
        address=str(row.get("ar") or "").strip(),
        location=point,
        active=str(row.get("act")).strip() == "1",
        rent=_reading(row.get("available_rent_bikes")),
        ret=_reading(row.get("available_return_bikes")),
        total=_reading(row.get("Quantity")),
        observed_at=_observed(row.get("infoTime"), "%Y-%m-%d %H:%M:%S"),
    )


def parse_new_taipei(row: dict[str, Any]) -> BikeStation | None:
    sno = str(row.get("sno") or "").strip()
    point = _point(to_float(row.get("lat")), to_float(row.get("lng")))
    if not sno or point is None:
        return None
    return BikeStation(
        id=f"{City.NEW_TAIPEI.value}:{sno}",
        city=City.NEW_TAIPEI,
        name=_clean_name(row.get("sna")),
        address=str(row.get("ar") or "").strip(),
        location=point,
        active=str(row.get("act")).strip() == "1",
        rent=_reading(row.get("sbi_quantity")),
        ret=_reading(row.get("bemp")),
        total=_reading(row.get("tot_quantity")),
        observed_at=_observed(row.get("mday"), "%Y%m%dT%H%M%S"),
    )


class TaipeiBikeFeed:
    city = City.TAIPEI

    def __init__(self, http: httpx.Client, url: str = TAIPEI_URL) -> None:
        self._http, self._url = http, url

    def fetch_stations(self) -> list[BikeStation]:
        rows = get_json(self._http, self._url)
        if not isinstance(rows, list):
            raise SourceError(f"{self._url}: expected a JSON array")
        stations = [s for row in rows if isinstance(row, dict) and (s := parse_taipei(row))]
        if not stations:
            raise SourceError(f"{self._url}: no usable stations")
        return stations


class NewTaipeiBikeFeed:
    city = City.NEW_TAIPEI

    def __init__(self, http: httpx.Client, url: str = NEW_TAIPEI_URL) -> None:
        self._http, self._url = http, url

    def fetch_stations(self) -> list[BikeStation]:
        rows: list[dict[str, Any]] = []
        for page in range(MAX_PAGES):
            chunk = get_json(self._http, self._url, params={"page": page, "size": PAGE_SIZE})
            if not isinstance(chunk, list):
                raise SourceError(f"{self._url}: expected a JSON array")
            rows.extend(r for r in chunk if isinstance(r, dict))
            if len(chunk) < PAGE_SIZE:
                break
        else:
            raise SourceError(f"{self._url}: more than {MAX_PAGES} pages, refusing to continue")
        stations = [s for row in rows if (s := parse_new_taipei(row))]
        if not stations:
            raise SourceError(f"{self._url}: no usable stations")
        return stations
