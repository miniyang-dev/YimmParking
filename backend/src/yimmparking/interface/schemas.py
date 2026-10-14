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


class BikeSearchResponse(BaseModel):
    origin: OriginDTO
    radius_m: int = Field(description="The radius that was searched (400, or 800 if widened)")
    expanded: bool = Field(description="True when nothing was within 400 m so 800 m was used")
    results: list[BikeStationDTO]


class SourceStatusDTO(BaseModel):
    city: Literal["taipei", "new_taipei"]
    lots: int
    availability_as_of: datetime | None


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
