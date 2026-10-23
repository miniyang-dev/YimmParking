"""TDX off-street parking: live free spaces per car park, a second source for a city's lots.

`/v1/Parking/OffStreet/ParkingAvailability/City/{City}` (TDX lists Taipei, not New Taipei). The
car park ids are the city's own (`TPE0096`), so they join the lots already held.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from yimmparking.adapters.tdx.client import TdxClient
from yimmparking.adapters.tdx.parse import TDX_CITY, car_spaces, observed_time
from yimmparking.application.ports import SourceError
from yimmparking.domain.curb import SpaceKind
from yimmparking.domain.model import (
    AvailabilityBatch,
    AvailabilityReading,
    AvailabilitySource,
    City,
)

# Rows in one answer carry their own collection times, normally within a few minutes of each
# other. A row far behind the newest is a car park whose own reporting stopped: no data.
ROW_STALE_AFTER = timedelta(minutes=30)


def car_count(row: dict[str, Any]) -> int | None:
    _, available, kind = car_spaces(row)
    return available if kind is not SpaceKind.NO_CAR else None


class TdxOffStreetAvailability:
    def __init__(self, client: TdxClient, city: City) -> None:
        self._client = client
        self.city = city
        self._path = f"v1/Parking/OffStreet/ParkingAvailability/City/{TDX_CITY[city]}"

    def fetch_availability(self) -> AvailabilityBatch:
        rows = self._client.get_items(self._path)
        timed = [
            (
                str(row.get("CarParkID") or "").strip(),
                observed_time(row.get("DataCollectTime")),
                row,
            )
            for row in rows
        ]
        times = [at for _, at, _ in timed if at is not None]
        if not times:
            raise SourceError(f"{self._path}: no row carries a collection time")
        newest = max(times)
        readings = tuple(
            AvailabilityReading(
                lot_id=f"{self.city.value}:{park_id}",
                count=(
                    car_count(row)
                    if at is not None and newest - at <= ROW_STALE_AFTER
                    else None
                ),
            )
            for park_id, at, row in timed
            if park_id
        )
        return AvailabilityBatch(
            city=self.city,
            observed_at=newest,
            readings=readings,
            source=AvailabilitySource.TDX,
        )
