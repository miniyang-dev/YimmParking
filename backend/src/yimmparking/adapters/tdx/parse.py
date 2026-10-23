"""Reading TDX rows: names, counts, times, and the car spaces in a space-type breakdown.

Shared by the on-street (segments) and off-street (car parks) adapters, whose live rows carry the
same `Availabilities` breakdown.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from yimmparking.adapters.sources.common import to_int
from yimmparking.domain.curb import SpaceKind
from yimmparking.domain.model import City

TDX_CITY = {City.TAIPEI: "Taipei", City.NEW_TAIPEI: "NewTaipei"}
SPACE_ALL = 0
SPACE_CAR = 1  # 自小客車位


def name_of(raw: Any) -> str:
    """`{"Zh_tw": ..., "En": ...}` (or plain text) → the Chinese name."""
    if isinstance(raw, dict):
        return str(raw.get("Zh_tw") or raw.get("En") or "").strip()
    return str(raw or "").strip()


def space_count(value: Any) -> int | None:
    """A space count; -1 (and anything negative) is TDX's "unknown", never zero."""
    count = to_int(value)
    return count if count is not None and count >= 0 else None


def observed_time(text: Any) -> datetime | None:
    """An ISO-8601 time with its zone, or None (a time without a zone is not trusted)."""
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def lookup(table: dict[int, Any], value: Any, default: Any) -> Any:
    code = to_int(value)
    return default if code is None else table.get(code, default)


def car_spaces(row: dict[str, Any]) -> tuple[int | None, int | None, SpaceKind]:
    """`(total, available, kind)` for cars in one live row.

    The car-space reading is what a driver needs; an all-types total may count scooters too. A
    row broken down into types without a car type has no car spaces at all (Taipei marks
    scooter-only segments this way, e.g. "太原路B(含機車)" with only SpaceType 2).
    """
    by_type = {
        to_int(a.get("SpaceType")): a
        for a in row.get("Availabilities") or []
        if isinstance(a, dict)
    }
    if by_type and SPACE_CAR not in by_type and SPACE_ALL not in by_type:
        return None, None, SpaceKind.NO_CAR
    if SPACE_CAR in by_type:
        car = by_type[SPACE_CAR]
        return (
            space_count(car.get("NumberOfSpaces")),
            space_count(car.get("AvailableSpaces")),
            SpaceKind.CAR,
        )
    source = by_type.get(SPACE_ALL, row)
    total = space_count(source.get("NumberOfSpaces", row.get("TotalSpaces")))
    return total, space_count(source.get("AvailableSpaces")), SpaceKind.ALL
