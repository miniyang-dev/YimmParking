"""Core domain entities and value objects. Pure data, no I/O, no framework imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.opening import OpeningPeriod


class TravelMode(StrEnum):
    WALK = "WALK"
    BICYCLE = "BICYCLE"


class City(StrEnum):
    TAIPEI = "taipei"
    NEW_TAIPEI = "new_taipei"


class Brand(StrEnum):
    DODOHOME = "dodohome"  # 嘟嘟房
    LIANTONG = "liantong"  # 台灣聯通
    TIMES = "times"  # Times 停車場
    USPACE = "uspace"  # USPACE
    OTHER = "other"


class BrandEvidence(StrEnum):
    NAME = "name"
    PHONE = "phone"
    NONE = "none"


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """Age thresholds for a real-time reading.

    The Taipei feed lags wall-clock time by several minutes even when healthy, so `fresh_s`
    is deliberately generous.
    """

    fresh_s: int = 15 * 60
    expire_s: int = 60 * 60

    def classify(self, observed_at: datetime | None, now: datetime) -> Freshness:
        if observed_at is None:
            return Freshness.UNKNOWN
        age = (now - observed_at).total_seconds()
        if age <= self.fresh_s:
            return Freshness.FRESH
        if age <= self.expire_s:
            return Freshness.STALE
        return Freshness.EXPIRED


@dataclass(frozen=True, slots=True)
class Availability:
    """Remaining car spaces for one lot.

    `count is None` means "no data". Source sentinels such as -9 must never reach here as a
    number: a missing reading is not the same as zero spaces.
    """

    count: int | None
    observed_at: datetime | None = None
    suspect: bool = False

    @property
    def is_known(self) -> bool:
        return self.count is not None

    @classmethod
    def unknown(cls) -> Availability:
        return cls(count=None)

    @classmethod
    def from_reading(
        cls, raw: int | None, total_car: int | None, observed_at: datetime | None
    ) -> Availability:
        if raw is None or raw < 0:
            return cls(count=None, observed_at=observed_at)
        # A source's total capacity is unreliable, so an over-capacity reading is flagged rather
        # than dropped or clamped: the caller decides how loudly to present it.
        suspect = total_car is not None and raw > total_car
        return cls(count=raw, observed_at=observed_at, suspect=suspect)


@dataclass(frozen=True, slots=True)
class ParkingLot:
    id: str  # "<city>:<source id>", unique across sources
    city: City
    source_id: str
    name: str
    address: str
    district: str
    location: GeoPoint
    phone: str = ""
    total_car: int | None = None
    fee_text: str = ""
    service_time: str = ""
    kind: str = ""
    ev_charging_spaces: int | None = None
    accessible_spaces: int | None = None
    brand: Brand = Brand.OTHER
    brand_evidence: BrandEvidence = BrandEvidence.NONE
    iparking_code: str | None = None

    @property
    def has_iparking(self) -> bool:
        return self.iparking_code is not None


@dataclass(frozen=True, slots=True)
class IParkingStation:
    """A station listed on the iParking directory (all of them are 嘟嘟房 stations)."""

    code: str
    name: str
    address: str
    city_code: str
    location: GeoPoint


@dataclass(frozen=True, slots=True)
class AvailabilityReading:
    """One raw reading from a source feed, before it is joined to a lot."""

    lot_id: str
    count: int | None  # None = source reported no data


@dataclass(frozen=True, slots=True)
class AvailabilityBatch:
    city: City
    observed_at: datetime
    readings: tuple[AvailabilityReading, ...]


@dataclass(frozen=True, slots=True)
class GeocodeCandidate:
    formatted_address: str
    location: GeoPoint
    place_id: str | None = None


@dataclass(frozen=True, slots=True)
class RouteTime:
    """Real route from an origin, as reported by the routing service."""

    seconds: int
    meters: int


@dataclass(frozen=True, slots=True)
class Place:
    """A nearby point of interest (food). Passed through, never persisted."""

    id: str
    name: str
    location: GeoPoint
    address: str = ""
    rating: float | None = None
    user_rating_count: int | None = None
    price_level: str | None = None
    primary_type: str | None = None
    primary_type_code: str | None = None  # Google's machine type, e.g. "chinese_restaurant"
    # Weekly schedule, cached. `open_now` is worked out per request from it, never cached.
    opening: tuple[OpeningPeriod, ...] | None = None
    open_now: bool | None = None
    maps_uri: str | None = None
    walking: RouteTime | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
