"""TDX on-street parking: segment basics and live free spaces, for one city.

Field names follow the TDX Parking OpenAPI document (OnStreet group):
`/v1/Parking/OnStreet/ParkingSegment/City/{City}` and
`/v1/Parking/OnStreet/ParkingSegmentAvailability/City/{City}`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from yimmparking.adapters.sources.common import in_taiwan, to_float
from yimmparking.adapters.tdx.client import TdxClient
from yimmparking.adapters.tdx.parse import (
    TDX_CITY,
    car_spaces,
    lookup,
    name_of,
    observed_time,
)
from yimmparking.application.ports import SourceError
from yimmparking.domain.curb import (
    CurbFullness,
    CurbReading,
    CurbSegment,
    CurbService,
)
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import City

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
        name=name_of(row.get("ParkingSegmentName")) or source_id,
        location=point,
        description=str(row.get("Description") or "").strip(),
        fare=str(row.get("FareDescription") or "").strip(),
        town=str(row.get("TownName") or "").strip(),
    )


def parse_availability(row: dict[str, Any], city: City) -> CurbReading | None:
    source_id = str(row.get("ParkingSegmentID") or "").strip()
    if not source_id:
        return None
    total, available, kind = car_spaces(row)
    return CurbReading(
        segment_id=f"{city.value}:{source_id}",
        total=total,
        available=available,
        kind=kind,
        fullness=lookup(_FULLNESS, row.get("FullStatus"), CurbFullness.UNKNOWN),
        service=lookup(_SERVICE, row.get("ServiceStatus"), CurbService.UNKNOWN),
        observed_at=observed_time(row.get("DataCollectTime")),
    )


def _quoted(value: str) -> str:
    """An OData string literal: single quotes, an inner quote doubled."""
    return "'" + value.replace("'", "''") + "'"


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

    def fetch_availability(self, segment_ids: Sequence[str]) -> dict[str, CurbReading]:
        """Only the named segments: TDX bills by the byte as well as by the call, and a city's
        full list is 60–75 KB compressed against under 1 KB for the few near a search."""
        prefix = f"{self.city.value}:"
        source_ids = [i.removeprefix(prefix) for i in segment_ids if i.startswith(prefix)]
        if not source_ids:
            return {}
        rows = self._client.get_items(
            f"v1/Parking/OnStreet/ParkingSegmentAvailability/City/{self._tdx_city}",
            {"$filter": " or ".join(f"ParkingSegmentID eq {_quoted(i)}" for i in source_ids)},
        )
        readings = (parse_availability(row, self.city) for row in rows)
        return {r.segment_id: r for r in readings if r is not None}
