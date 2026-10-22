"""HTTP response models. These are the contract the web client is generated from."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AvailabilityDTO(BaseModel):
    state: Literal["known", "unknown"]
    count: int | None = Field(description="Remaining car spaces; null when the source has no data")
    observed_at: datetime | None
    freshness: Literal["fresh", "stale", "expired", "unknown"]
    suspect: bool = Field(description="Reading exceeds the lot's listed capacity; treat as rough")


class TrendDTO(BaseModel):
    minutes: int = Field(description="The window compared, e.g. the last 30 minutes")
    delta: int = Field(description="Spaces now minus spaces `minutes` ago; negative = filling")
    direction: Literal["filling", "emptying", "steady"]
    full_in_min: int | None = Field(
        description="At this pace, minutes until full (filling only, up to 2 hours); else null"
    )


class HoursDTO(BaseModel):
    status: Literal["always", "open", "closing_soon", "closed", "unknown"] = Field(
        description="From the service time when it is a plain daily range; else unknown"
    )
    opens_at: str | None = Field(description="HH:MM when closed now")
    closes_at: str | None = Field(description="HH:MM when closing within 2 hours")


class ParkingLotDTO(BaseModel):
    id: str
    name: str
    city: Literal["taipei", "new_taipei"]
    district: str
    address: str
    lat: float
    lng: float
    distance_m: int = Field(description="Straight-line distance from the search origin")
    walk_seconds: int | None = Field(
        description="Real walking time from the search origin; null when it could not be routed"
    )
    walk_meters: int | None = Field(description="Length of that walking route")
    bearing_deg: int = Field(ge=0, lt=360, description="Compass bearing from the search origin")
    brand: Literal["dodohome", "liantong", "times", "uspace", "other"]
    brand_evidence: Literal["name", "phone", "none"]
    iparking: bool
    vendor: Literal["iparking_dodohome", "dodohome", "liantong", "times", "uspace"] | None = Field(
        description="The configurable vendor this lot belongs to; null for a small operator"
    )
    block: Literal["priority", "other", "distance"] = Field(
        description="priority: in a vendor section; other: after them; distance: walking only"
    )
    total_car: int | None
    availability: AvailabilityDTO
    fee_text: str
    hourly_rate: int | None = Field(
        description="Best-effort headline car rate per hour; null when it cannot be read"
    )
    service_time: str
    phone: str
    kind: str
    ev_charging_spaces: int | None
    accessible_spaces: int | None
    trend: TrendDTO | None = Field(
        description="How the count moved lately; null when the history cannot tell"
    )
    doubts: list[Literal["frozen", "over_capacity", "often_missing"]] = Field(
        description="Reasons from the last week's readings to treat the number with care"
    )
    hours: HoursDTO


class TypicalSlotDTO(BaseModel):
    minute: int = Field(description="Minutes after local midnight")
    median: float | None = Field(description="Usual spaces left; null with too few past days")
    samples: int


class TypicalDayResponse(BaseModel):
    lot_id: str
    weekday: int = Field(ge=0, le=6, description="0 = Monday … 6 = Sunday")
    days_used: int = Field(description="Past days of this weekday that had readings")
    min_days: int = Field(description="Readings a half hour needs before it shows a value")
    slots: list[TypicalSlotDTO]


class OriginDTO(BaseModel):
    lat: float
    lng: float
    label: str | None = None


class AlternativeDTO(BaseModel):
    label: str
    lat: float
    lng: float


class SearchMetaDTO(BaseModel):
    radius_m: int
    mode: Literal["tiered", "distance"]
    count: int
    pool_size: int = Field(description="Lots inside the radius; only a shortlist is returned")
    walking: Literal["google", "quota_exhausted", "unavailable"] = Field(
        description="Where the walking times came from; anything but google means straight-line"
    )
    stale_sources: list[StaleSourceDTO] = Field(
        description="Cities whose real-time feed has stopped; their lots all read as no data"
    )


class StaleSourceDTO(BaseModel):
    city: Literal["taipei", "new_taipei"]
    as_of: datetime | None = Field(description="Newest reading held for the city; null if none")


class ParkingSearchResponse(BaseModel):
    origin: OriginDTO
    alternatives: list[AlternativeDTO] = []
    results: list[ParkingLotDTO]
    meta: SearchMetaDTO


class FoodDTO(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    distance_m: int
    walk_seconds: int | None = Field(description="Walking time from the search origin, if known")
    walk_meters: int | None
    address: str
    rating: float | None
    user_rating_count: int | None
    price_level: str | None
    primary_type: str | None
    category: Literal[
        "chinese",
        "japanese",
        "korean",
        "thai",
        "southeast_asian",
        "western",
        "seafood",
        "cafe",
        "other",
    ]
    open_now: bool | None
    maps_uri: str | None


class FoodSearchResponse(BaseModel):
    origin: OriginDTO
    results: list[FoodDTO]
    min_rating: float = Field(description="Rating floor already applied to every result")
    min_reviews: int = Field(description="Review-count floor already applied to every result")
    attribution: str = "Google Maps"


class BikeStationDTO(BaseModel):
    id: str
    name: str
    address: str
    lat: float
    lng: float
    distance_m: int = Field(description="Straight-line distance from the query point")
    rent: int | None = Field(description="Bikes that can be taken; null = no reading")
    ret: int | None = Field(description="Free docks; null = no reading")
    observed_at: datetime | None = Field(description="When the feed says the reading was taken")
    bearing_deg: int = Field(ge=0, lt=360, description="Compass bearing from the query point")


class BikeSearchResponse(BaseModel):
    origin: OriginDTO
    radius_m: int = Field(description="The radius that was searched (400, or 800 if widened)")
    expanded: bool = Field(description="True when nothing was within 400 m so 800 m was used")
    results: list[BikeStationDTO]
    unavailable_cities: list[Literal["taipei", "new_taipei"]] = Field(
        description="Cities whose feed could not be read; their stations are missing from results"
    )


class CurbSegmentDTO(BaseModel):
    id: str
    name: str
    description: str
    fare: str
    town: str
    lat: float
    lng: float
    distance_m: int = Field(description="Straight-line distance to the segment's marker point")
    total: int | None = Field(description="Spaces on the segment; null when TDX gave none")
    available: int | None = Field(description="Free spaces now; null = no data, never zero")
    space_kind: Literal["car", "all"] = Field(
        description="car: the car-space count; all: an all-types total that may include scooters"
    )
    fullness: Literal["available", "almost_full", "full", "overcrowded", "unknown"]
    service: Literal["open", "resting", "suspended", "outside_hours", "unknown"]
    observed_at: datetime | None


class CurbSearchResponse(BaseModel):
    origin: OriginDTO
    radius_m: int = Field(description="The radius searched (300, or 600 if widened)")
    expanded: bool
    results: list[CurbSegmentDTO]
    unavailable_cities: list[Literal["taipei", "new_taipei"]]


class SourceStatusDTO(BaseModel):
    city: Literal["taipei", "new_taipei"]
    lots: int
    availability_as_of: datetime | None
    stale: bool = Field(description="No reading, or the newest is over an hour old")


class UsageDTO(BaseModel):
    meter: Literal["geocoding", "places_nearby", "routes_elements"]
    period: str
    used: int
    limit: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    geocoder_configured: bool
    sources: list[SourceStatusDTO]
    usage: list[UsageDTO]
    # Which build is answering (see interface/build_info.py); a deploy check compares these.
    version: str | None = None  # git commit of the running backend; None when unknown
    frontend_version: str | None = None  # commit the served web build was made from
    started_at: str  # when this process started, ISO-8601 UTC


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
