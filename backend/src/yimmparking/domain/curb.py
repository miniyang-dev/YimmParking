"""On-street (curb) parking: road segments with metered spaces, and how many are free.

A segment is a stretch of road, not a lot: its position is one representative point, so the
distance to it is approximate and is labelled as straight-line to that point.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import City


class CurbFullness(StrEnum):
    """The operator's own reading of the segment (TDX FullStatus)."""

    AVAILABLE = "available"  # 尚有空位
    ALMOST_FULL = "almost_full"  # 車位將滿
    FULL = "full"  # 車位已滿
    OVERCROWDED = "overcrowded"  # 過度擁擠
    UNKNOWN = "unknown"


class CurbService(StrEnum):
    """Whether parking is in service on the segment now (TDX ServiceStatus)."""

    OPEN = "open"  # 營業中
    RESTING = "resting"  # 休息中
    SUSPENDED = "suspended"  # 暫停營業
    OUTSIDE_HOURS = "outside_hours"  # 非營業時段
    UNKNOWN = "unknown"


class SpaceKind(StrEnum):
    CAR = "car"  # counted from the car-space reading
    ALL = "all"  # only an all-types total was given: it may include scooter spaces


@dataclass(frozen=True, slots=True)
class CurbSegment:
    id: str  # "<city>:<segment id>"
    city: City
    name: str
    location: GeoPoint  # representative point of the segment
    description: str = ""
    fare: str = ""
    town: str = ""


@dataclass(frozen=True, slots=True)
class CurbReading:
    """Free spaces on one segment. `None` counts are "no data", never zero."""

    segment_id: str
    total: int | None
    available: int | None
    kind: SpaceKind
    fullness: CurbFullness
    service: CurbService
    observed_at: datetime | None
