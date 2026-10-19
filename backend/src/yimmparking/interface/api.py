"""FastAPI application. Thin: parse input, call a use case, map the result to a DTO."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from yimmparking.application.limits import GEOCODING, PLACES_NEARBY, ROUTES_ELEMENTS
from yimmparking.application.ports import (
    GeocodingError,
    GeocodingUnavailable,
    PlacesError,
    QuotaExceeded,
    SourceError,
)
from yimmparking.application.search import FoodHit, ParkingHit
from yimmparking.application.search_bikes import BikeHit
from yimmparking.domain.fee import hourly_car_rate
from yimmparking.domain.food_category import category_of
from yimmparking.domain.geo import GeoPoint, initial_bearing_deg
from yimmparking.domain.model import City
from yimmparking.domain.ranking import RankingPolicy, SortMode
from yimmparking.domain.vendor import DEFAULT_SHOW, Preference, Vendor, VendorPick
from yimmparking.interface.build_info import frontend_version, process_build_info
from yimmparking.interface.container import Container, build_container
from yimmparking.interface.schemas import (
    AlternativeDTO,
    AvailabilityDTO,
    BikeSearchResponse,
    BikeStationDTO,
    ErrorResponse,
    FoodDTO,
    FoodSearchResponse,
    HealthResponse,
    OriginDTO,
    ParkingLotDTO,
    ParkingSearchResponse,
    SearchMetaDTO,
    SourceStatusDTO,
    UsageDTO,
)
from yimmparking.interface.settings import BACKEND_DIR, Settings

Lat = Annotated[float, Query(ge=21.5, le=25.5, description="WGS84 latitude (Taiwan)")]
Lng = Annotated[float, Query(ge=119.0, le=122.5, description="WGS84 longitude (Taiwan)")]
Mode = Annotated[
    SortMode, Query(description="tiered = vendor sections, distance = walking time only")
]
Vendors = Annotated[
    str | None,
    Query(
        max_length=200,
        description="Vendor order and how many to show, e.g. iparking_dodohome:2,dodohome:2",
    ),
]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


def parse_vendors(raw: str | None) -> Preference:
    """`iparking_dodohome:2,dodohome:2,...`: the order is the priority, the number is how many show.

    Only configurable (large) vendors are accepted; any other name is refused.
    """
    if raw is None or not raw.strip():
        return Preference()
    picks: list[VendorPick] = []
    for part in raw.split(","):
        key, has_count, count = part.strip().partition(":")
        try:
            picks.append(VendorPick(Vendor(key), int(count) if has_count else DEFAULT_SHOW))
        except ValueError as exc:
            raise ApiError(422, "invalid_vendors", f"not a configurable vendor: {part!r}") from exc
    try:
        return Preference.from_picks(picks)
    except ValueError as exc:
        raise ApiError(422, "invalid_vendors", str(exc)) from exc


def to_lot_dto(hit: ParkingHit, origin: GeoPoint) -> ParkingLotDTO:
    r, a = hit.ranked, hit.availability
    lot = r.lot
    return ParkingLotDTO(
        id=lot.id,
        name=lot.name,
        city=lot.city.value,
        district=lot.district,
        address=lot.address,
        lat=lot.location.lat,
        lng=lot.location.lng,
        distance_m=round(r.distance_m),
        walk_seconds=r.walking.seconds if r.walking else None,
        walk_meters=r.walking.meters if r.walking else None,
        bearing_deg=int(round(initial_bearing_deg(origin, lot.location))) % 360,
        brand=lot.brand.value,
        brand_evidence=lot.brand_evidence.value,
        iparking=lot.has_iparking,
        vendor=r.vendor.value if r.vendor else None,
        block=r.block.value,
        total_car=lot.total_car,
        availability=AvailabilityDTO(
            state="known" if a.is_known else "unknown",
            count=a.count,
            observed_at=a.observed_at,
            freshness=hit.freshness.value,
            suspect=a.suspect,
        ),
        fee_text=lot.fee_text,
        hourly_rate=hourly_car_rate(lot.fee_text),
        service_time=lot.service_time,
        phone=lot.phone,
        kind=lot.kind,
        ev_charging_spaces=lot.ev_charging_spaces,
        accessible_spaces=lot.accessible_spaces,
    )


def to_food_dto(hit: FoodHit) -> FoodDTO:
    p = hit.place
    return FoodDTO(
        id=p.id,
        name=p.name,
        lat=p.location.lat,
        lng=p.location.lng,
        distance_m=round(hit.distance_m),
        walk_seconds=p.walking.seconds if p.walking else None,
        walk_meters=p.walking.meters if p.walking else None,
        address=p.address,
        rating=p.rating,
        user_rating_count=p.user_rating_count,
        price_level=p.price_level,
        primary_type=p.primary_type,
        category=category_of(p.primary_type_code).value,
        open_now=p.open_now,
        maps_uri=p.maps_uri,
    )


def to_bike_dto(hit: BikeHit) -> BikeStationDTO:
    s = hit.station
    return BikeStationDTO(
        id=s.id,
        name=s.name,
        address=s.address,
        lat=s.location.lat,
        lng=s.location.lng,
        distance_m=round(hit.distance_m),
        rent=s.rent,
        ret=s.ret,
        observed_at=s.observed_at,
    )


def create_app(container: Container | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or (container.settings if container else Settings.from_env())
    owns_container = container is None
    state: dict[str, Container] = {}
    if container is not None:
        state["c"] = container

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if owns_container:
            state["c"] = build_container(settings)
        try:
            yield
        finally:
            if owns_container:
                state["c"].close()

    app = FastAPI(title="YimmParking", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    build = process_build_info(BACKEND_DIR.parent)

    def c() -> Container:
        return state["c"]

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}}
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": str(exc.errors()[0]["msg"])}},
        )

    responses: dict[int | str, dict[str, Any]] = {
        404: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    }

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        ct = c()
        as_of = ct.store.last_availability_at()
        sources = [
            SourceStatusDTO(
                city=city.value,
                lots=ct.store.lot_count(city),
                availability_as_of=as_of.get(city),
            )
            for city in City
        ]
        ok = all(s.lots > 0 for s in sources)
        usage = [
            UsageDTO(
                meter=meter,  # type: ignore[arg-type]
                period=ct.usage.period,
                used=ct.usage.used(meter),
                limit=limit,
            )
            for meter, limit in (
                (GEOCODING, ct.usage.limit(GEOCODING)),
                (PLACES_NEARBY, ct.usage.limit(PLACES_NEARBY)),
                (ROUTES_ELEMENTS, ct.usage.limit(ROUTES_ELEMENTS)),
            )
        ]
        return HealthResponse(
            status="ok" if ok else "degraded",
            geocoder_configured=ct.geocoder_configured,
            sources=sources,
            usage=usage,
            version=build.version,
            frontend_version=frontend_version(settings.web_dist),
            started_at=build.started_at,
        )

    @app.get("/api/v1/parking/nearby", response_model=ParkingSearchResponse, responses=responses)
    def parking_nearby(
        lat: Lat, lng: Lng, mode: Mode = SortMode.TIERED, vendors: Vendors = None
    ) -> ParkingSearchResponse:
        return _search(
            c(),
            GeoPoint(lat, lng),
            mode,
            parse_vendors(vendors),
            label=None,
            alternatives=[],
        )

    @app.get("/api/v1/search", response_model=ParkingSearchResponse, responses=responses)
    def search(
        q: Annotated[str, Query(min_length=1, max_length=200, description="A Taiwan address")],
        mode: Mode = SortMode.TIERED,
        vendors: Vendors = None,
    ) -> ParkingSearchResponse:
        ct = c()
        preference = parse_vendors(vendors)
        try:
            candidates = ct.resolve_address.execute(q)
        except QuotaExceeded as exc:
            raise ApiError(429, "quota_exhausted", f"geocoding: {exc}") from exc
        except GeocodingUnavailable as exc:
            raise ApiError(503, "geocoder_unavailable", str(exc)) from exc
        except GeocodingError as exc:
            raise ApiError(502, "geocoder_error", str(exc)) from exc
        if not candidates:
            raise ApiError(404, "address_not_found", f"找不到地址：{q}")
        first, rest = candidates[0], candidates[1:]
        return _search(
            ct,
            first.location,
            mode,
            preference,
            label=first.formatted_address,
            alternatives=[
                AlternativeDTO(label=r.formatted_address, lat=r.location.lat, lng=r.location.lng)
                for r in rest
            ],
        )

    @app.get("/api/v1/food/nearby", response_model=FoodSearchResponse, responses=responses)
    def food_nearby(
        lat: Lat,
        lng: Lng,
        radius: Annotated[int, Query(ge=100, le=2000)] = 500,
        limit: Annotated[int, Query(ge=1, le=20)] = 20,
        origin_lat: Annotated[float | None, Query(ge=21.5, le=25.5)] = None,
        origin_lng: Annotated[float | None, Query(ge=119.0, le=122.5)] = None,
    ) -> FoodSearchResponse:
        ct = c()
        center = GeoPoint(lat, lng)
        try:
            origin = (
                GeoPoint(origin_lat, origin_lng)
                if origin_lat is not None and origin_lng is not None
                else None
            )
            found = ct.search_food.execute(center, radius, limit, origin)
        except QuotaExceeded as exc:
            raise ApiError(429, "quota_exhausted", f"places: {exc}") from exc
        except PlacesError as exc:
            status = 503 if "not configured" in str(exc) else 502
            raise ApiError(status, "places_unavailable", str(exc)) from exc
        return FoodSearchResponse(
            origin=OriginDTO(lat=lat, lng=lng),
            results=[to_food_dto(h) for h in found.hits],
            min_rating=found.min_rating,
            min_reviews=found.min_reviews,
        )

    @app.get("/api/v1/bikes/nearby", response_model=BikeSearchResponse, responses=responses)
    def bikes_nearby(lat: Lat, lng: Lng) -> BikeSearchResponse:
        try:
            found = c().search_bikes.execute(GeoPoint(lat, lng))
        except SourceError as exc:
            raise ApiError(502, "bikes_unavailable", str(exc)) from exc
        return BikeSearchResponse(
            origin=OriginDTO(lat=lat, lng=lng),
            radius_m=found.radius_m,
            expanded=found.expanded,
            results=[to_bike_dto(h) for h in found.hits],
            unavailable_cities=[city.value for city in found.missing],
        )

    def _search(
        ct: Container,
        center: GeoPoint,
        mode: SortMode,
        preference: Preference,
        *,
        label: str | None,
        alternatives: list[AlternativeDTO],
    ) -> ParkingSearchResponse:
        policy = RankingPolicy(mode=mode, preference=preference)
        result = ct.search_parking.execute(center, policy)
        return ParkingSearchResponse(
            origin=OriginDTO(lat=center.lat, lng=center.lng, label=label),
            alternatives=alternatives,
            results=[to_lot_dto(h, center) for h in result.hits],
            meta=SearchMetaDTO(
                radius_m=result.radius_m,
                mode=mode.value,
                count=len(result.hits),
                pool_size=result.pool_size,
                walking=result.walking.value,
            ),
        )

    # Last, so every /api route wins; serves the built client when one exists.
    if settings.web_dist is not None:
        app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")

    return app
