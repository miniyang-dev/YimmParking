"""Matching iParking directory stations to government parking lots.

The directory and the government feeds share no identifier, so they are joined by location.
Only 嘟嘟房 lots are eligible: a neighbouring non-嘟嘟房 lot within the radius must not inherit
the flag.
"""

from __future__ import annotations

from collections.abc import Iterable

from yimmparking.domain.geo import bounding_box, haversine_m
from yimmparking.domain.model import Brand, IParkingStation, ParkingLot

DEFAULT_MATCH_RADIUS_M = 150.0


def match_iparking(
    lots: Iterable[ParkingLot],
    stations: Iterable[IParkingStation],
    max_distance_m: float = DEFAULT_MATCH_RADIUS_M,
) -> dict[str, str]:
    """Return `{lot_id: station_code}`. Each station claims its nearest 嘟嘟房 lot in range.

    When two stations claim the same lot, the nearer one wins.
    """
    candidates = [lot for lot in lots if lot.brand is Brand.DODOHOME]
    claimed: dict[str, tuple[float, str]] = {}
    for station in stations:
        box = bounding_box(station.location, max_distance_m)
        best: tuple[float, ParkingLot] | None = None
        for lot in candidates:
            loc = lot.location
            if not (
                box.min_lat <= loc.lat <= box.max_lat and box.min_lng <= loc.lng <= box.max_lng
            ):
                continue
            d = haversine_m(station.location, loc)
            if d <= max_distance_m and (best is None or d < best[0]):
                best = (d, lot)
        if best is None:
            continue
        d, lot = best
        current = claimed.get(lot.id)
        if current is None or d < current[0]:
            claimed[lot.id] = (d, station.code)
    return {lot_id: code for lot_id, (_, code) in claimed.items()}
