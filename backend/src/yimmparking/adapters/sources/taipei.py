"""臺北市 parking feeds (TCMSV_alldesc.json / TCMSV_allavailable.json).

Both files are plain JSON on a public blob, no key required.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx

from yimmparking.adapters.sources.common import get_json, in_taiwan, to_float, to_int
from yimmparking.application.ports import SourceError
from yimmparking.domain.geo import GeoPoint, haversine_m, twd97_to_wgs84
from yimmparking.domain.model import (
    AvailabilityBatch,
    AvailabilityReading,
    City,
    ParkingLot,
)

log = logging.getLogger(__name__)

DESC_URL = "https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_alldesc.json"
AVAILABLE_URL = "https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_allavailable.json"

_TAIWAN_TZ = timezone(timedelta(hours=8))
# An entrance coordinate is preferred (it is where a driver actually goes), but one that lies far
# from the lot's own TWD97 position is a data-entry error, not a better answer.
_MAX_ENTRANCE_OFFSET_M = 500.0


def parse_update_time(text: str) -> datetime:
    """'Sat Oct 10 22:27:00 CST 2026' → timezone-aware datetime. CST here is Taiwan time."""
    parts = text.split()
    if len(parts) != 6 or parts[4] != "CST":
        raise SourceError(f"unrecognised UPDATETIME: {text!r}")
    del parts[4]
    parsed = datetime.strptime(" ".join(parts), "%a %b %d %H:%M:%S %Y")
    return parsed.replace(tzinfo=_TAIWAN_TZ).astimezone(UTC)


def _entrance_point(raw: dict[str, Any]) -> GeoPoint | None:
    entrance = raw.get("EntranceCoord") or {}
    for info in entrance.get("EntrancecoordInfo") or []:
        # The feed names latitude "Xcod" and longitude "Ycod".
        lat, lng = to_float(info.get("Xcod")), to_float(info.get("Ycod"))
        if lat is None or lng is None:
            continue
        try:
            point = GeoPoint(lat, lng)
        except ValueError:
            continue
        if in_taiwan(point):
            return point
    return None


def parse_lot(raw: dict[str, Any]) -> ParkingLot | None:
    source_id = str(raw.get("id", "")).strip()
    x, y = to_float(raw.get("tw97x")), to_float(raw.get("tw97y"))
    if not source_id or x is None or y is None:
        return None
    try:
        centroid = twd97_to_wgs84(x, y)
    except ValueError:
        return None
    if not in_taiwan(centroid):
        return None

    location = centroid
    entrance = _entrance_point(raw)
    if entrance is not None and haversine_m(entrance, centroid) <= _MAX_ENTRANCE_OFFSET_M:
        location = entrance

    return ParkingLot(
        id=f"{City.TAIPEI.value}:{source_id}",
        city=City.TAIPEI,
        source_id=source_id,
        name=str(raw.get("name", "")).strip(),
        address=str(raw.get("address", "")).strip(),
        district=str(raw.get("area", "")).strip(),
        location=location,
        phone=str(raw.get("tel", "")).strip(),
        total_car=to_int(raw.get("totalcar")),
        fee_text=str(raw.get("payex", "")).strip(),
        service_time=str(raw.get("serviceTime", "")).strip(),
        kind=str(raw.get("type2", "")).strip(),
        ev_charging_spaces=to_int(raw.get("ChargingStation")),
        accessible_spaces=to_int(raw.get("Handicap_First")),
    )


class TaipeiFeed:
    city = City.TAIPEI

    def __init__(
        self,
        http: httpx.Client,
        desc_url: str = DESC_URL,
        available_url: str = AVAILABLE_URL,
    ) -> None:
        self._http = http
        self._desc_url = desc_url
        self._available_url = available_url

    def fetch_lots(self) -> list[ParkingLot]:
        payload = get_json(self._http, self._desc_url)
        try:
            parks = payload["data"]["park"]
        except (KeyError, TypeError) as exc:
            raise SourceError(f"{self._desc_url}: unexpected structure") from exc

        lots: dict[str, ParkingLot] = {}
        skipped = 0
        for raw in parks:
            lot = parse_lot(raw)
            if lot is None:
                skipped += 1
                continue
            lots.setdefault(lot.id, lot)
        if skipped:
            log.warning("taipei: skipped %d lots without a usable id or coordinate", skipped)
        if not lots:
            raise SourceError(f"{self._desc_url}: no usable lots")
        return list(lots.values())

    def fetch_availability(self) -> AvailabilityBatch:
        payload = get_json(self._http, self._available_url)
        try:
            data = payload["data"]
            observed_at = parse_update_time(data["UPDATETIME"])
            parks = data["park"]
        except (KeyError, TypeError) as exc:
            raise SourceError(f"{self._available_url}: unexpected structure") from exc

        readings: dict[str, AvailabilityReading] = {}
        for raw in parks:
            source_id = str(raw.get("id", "")).strip()
            if not source_id:
                continue
            count = to_int(raw.get("availablecar"))
            # -9 (and any other negative) is the feed's "no data" marker, not a count.
            if count is not None and count < 0:
                count = None
            lot_id = f"{City.TAIPEI.value}:{source_id}"
            readings[lot_id] = AvailabilityReading(lot_id=lot_id, count=count)
        return AvailabilityBatch(
            city=City.TAIPEI, observed_at=observed_at, readings=tuple(readings.values())
        )
