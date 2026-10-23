"""TDX on-street parking: segment basics and live free spaces, for one city.

Field names follow the TDX Parking OpenAPI document (OnStreet group):
`/v1/Parking/OnStreet/ParkingSegment/City/{City}` and
`/v1/Parking/OnStreet/ParkingSegmentAvailability/City/{City}`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from yimmparking.adapters.sources.common import in_taiwan, to_float, to_int
from yimmparking.adapters.tdx.client import TdxClient
from yimmparking.application.ports import SourceError
from yimmparking.domain.curb import (
    CurbFullness,
    CurbReading,
    CurbSegment,
    CurbService,
    SpaceKind,
)
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import City

TDX_CITY = {City.TAIPEI: "Taipei", City.NEW_TAIPEI: "NewTaipei"}

_FULLNESS = {
    0: CurbFullness.AVAILABLE,
    1: CurbFullness.ALMOST_FULL,
    2: CurbFullness.FULL,
    3: CurbFullness.OVERCROWDED,
}
_SERVICE = {
    0: CurbService.RESTING,
    1: CurbService.OPEN,
    2: CurbService.SUSPENDED,
    3: CurbService.OUTSIDE_HOURS,
}
SPACE_ALL = 0
SPACE_CAR = 1  # 自小客車位


def _name(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("Zh_tw") or raw.get("En") or "").strip()
    return str(raw or "").strip()


def _count(value: Any) -> int | None:
    """A space count; -1 (and anything negative) is TDX's "unknown", never zero."""
    count = to_int(value)
    return count if count is not None and count >= 0 else None


def parse_segment(row: dict[str, Any], city: City) -> CurbSegment | None:
    source_id = str(row.get("ParkingSegmentID") or "").strip()
    position = row.get("ParkingSegmentPosition") or {}
    lat, lng = to_float(position.get("PositionLat")), to_float(position.get("PositionLon"))
    if not source_id or lat is None or lng is None:
        return None
    try:
        point = GeoPoint(lat, lng)
    except ValueError:
        return None
    if not in_taiwan(point):
        return None
    return CurbSegment(
        id=f"{city.value}:{source_id}",
        city=city,
        name=_name(row.get("ParkingSegmentName")) or source_id,
        location=point,
        description=str(row.get("Description") or "").strip(),
        fare=str(row.get("FareDescription") or "").strip(),
        town=str(row.get("TownName") or "").strip(),
    )


def _lookup(table: dict[int, Any], value: Any, default: Any) -> Any:
    code = to_int(value)
    return default if code is None else table.get(code, default)


def _observed(text: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def parse_availability(row: dict[str, Any], city: City) -> CurbReading | None:
    source_id = str(row.get("ParkingSegmentID") or "").strip()
    if not source_id:
        return None
    by_type = {
        to_int(a.get("SpaceType")): a
        for a in row.get("Availabilities") or []
        if isinstance(a, dict)
    }
    # The car-space reading is what a driver needs; an all-types total may count scooters too.
    # A segment broken down into types without a car type has no car spaces at all (Taipei marks
    # scooter-only segments this way, e.g. "太原路B(含機車)" with only SpaceType 2).
    if by_type and SPACE_CAR not in by_type and SPACE_ALL not in by_type:
        total, available, kind = None, None, SpaceKind.NO_CAR
    elif SPACE_CAR in by_type:
        car = by_type[SPACE_CAR]
        total, available, kind = (
            _count(car.get("NumberOfSpaces")),
            _count(car.get("AvailableSpaces")),
            SpaceKind.CAR,
        )
    else:
        source = by_type.get(SPACE_ALL, row)
        total = _count(source.get("NumberOfSpaces", row.get("TotalSpaces")))
        available = _count(source.get("AvailableSpaces"))
        kind = SpaceKind.ALL
    return CurbReading(
        segment_id=f"{city.value}:{source_id}",
        total=total,
        available=available,
        kind=kind,
        fullness=_lookup(_FULLNESS, row.get("FullStatus"), CurbFullness.UNKNOWN),
        service=_lookup(_SERVICE, row.get("ServiceStatus"), CurbService.UNKNOWN),
        observed_at=_observed(row.get("DataCollectTime")),
    )


class TdxCurbFeed:
    def __init__(self, client: TdxClient, city: City) -> None:
        self._client = client
        self.city = city
        self._tdx_city = TDX_CITY[city]

    def fetch_segments(self) -> list[CurbSegment]:
        rows = self._client.get_items(f"v1/Parking/OnStreet/ParkingSegment/City/{self._tdx_city}")
        segments = [s for row in rows if (s := parse_segment(row, self.city)) is not None]
        if rows and not segments:
            raise SourceError(f"{self._tdx_city} curb segments: none had a usable position")
        return segments

    def fetch_availability(self) -> dict[str, CurbReading]:
        rows = self._client.get_items(
            f"v1/Parking/OnStreet/ParkingSegmentAvailability/City/{self._tdx_city}"
        )
        readings = (parse_availability(row, self.city) for row in rows)
        return {r.segment_id: r for r in readings if r is not None}
