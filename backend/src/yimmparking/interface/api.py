"""FastAPI application. Thin: parse input, call a use case, map the result to a DTO."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from yimmparking.application.feed_watch import source_statuses, stale_cities
from yimmparking.application.insights import LotInsight
from yimmparking.application.ports import (
    CurbUnconfigured,
    GeocodingError,
    GeocodingUnavailable,
    PlacesError,
    PlacesUnavailable,
    QuotaExceeded,
    SourceError,
)
from yimmparking.application.search import FoodHit, ParkingHit
from yimmparking.application.search_bikes import BikeHit
from yimmparking.application.search_curb import CurbHit
from yimmparking.domain.curb import SpaceKind
from yimmparking.domain.fee import hourly_car_rate
from yimmparking.domain.food_category import category_of
from yimmparking.domain.geo import GeoPoint, initial_bearing_deg
from yimmparking.domain.hours import hours_now
from yimmparking.domain.model import City
from yimmparking.domain.occupancy import MIN_WEEKS, Trend
from yimmparking.domain.ranking import RankingPolicy, SortMode
from yimmparking.domain.vendor import DEFAULT_SHOW, MAX_SHOW, Preference, Vendor, VendorPick
from yimmparking.interface.build_info import frontend_version, process_build_info
from yimmparking.interface.container import Container, build_container
from yimmparking.interface.schemas import (
    AlternativeDTO,
    AvailabilityDTO,
    BikeSearchResponse,
    BikeStationDTO,
    CurbSearchResponse,
    CurbSegmentDTO,
    ErrorResponse,
    FoodDTO,
    FoodSearchResponse,
    HealthResponse,
    HoursDTO,
    OriginDTO,
    ParkingLotDTO,
    ParkingSearchResponse,
    SearchMetaDTO,
    SourceStatusDTO,
    StaleSourceDTO,
    TrendDTO,
    TypicalDayResponse,
    TypicalSlotDTO,
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
            vendor = Vendor(key)
        except ValueError as exc:
            raise ApiError(422, "invalid_vendors", f"not a configurable vendor: {key!r}") from exc
        try:
            picks.append(VendorPick(vendor, int(count) if has_count else DEFAULT_SHOW))
        except ValueError as exc:
            raise ApiError(
                422, "invalid_vendors", f"{key}: count must be 0 to {MAX_SHOW}, got {count!r}"
            ) from exc
    try:
        return Preference.from_picks(picks)
    except ValueError as exc:
        raise ApiError(422, "invalid_vendors", str(exc)) from exc


def to_trend_dto(trend: Trend | None) -> TrendDTO | None:
    if trend is None:
        return None
    return TrendDTO(
        minutes=trend.minutes,
        delta=trend.delta,
        direction=trend.direction.value,
        full_in_min=trend.full_in_min,
    )


def to_lot_dto(
    hit: ParkingHit, origin: GeoPoint, insight: LotInsight, now: datetime
) -> ParkingLotDTO:
    r, a = hit.ranked, hit.availability
    lot = r.lot
    hours = hours_now(lot.service_time, now)
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
        trend=to_trend_dto(insight.trend),
        doubts=[d.value for d in insight.doubts],
        hours=HoursDTO(
            status=hours.status.value, opens_at=hours.opens_at, closes_at=hours.closes_at
        ),
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


def to_curb_dto(hit: CurbHit) -> CurbSegmentDTO:
    s, r = hit.segment, hit.reading
    return CurbSegmentDTO(
        id=s.id,
        name=s.name,
        description=s.description,
        fare=s.fare,
        town=s.town,
        lat=s.location.lat,
        lng=s.location.lng,
        distance_m=round(hit.distance_m),
        total=r.total if r else None,
        available=r.available if r else None,
        # Scooter-only segments never get here (the search drops them): it is car or all.
        space_kind="car" if r and r.kind is SpaceKind.CAR else "all",
        fullness=r.fullness.value if r else "unknown",
        service=r.service.value if r else "unknown",
        observed_at=r.observed_at if r else None,
    )


def to_bike_dto(hit: BikeHit, origin: GeoPoint) -> BikeStationDTO:
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
        bearing_deg=int(round(initial_bearing_deg(origin, s.location))) % 360,
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
        sources = [
            SourceStatusDTO(
                city=s.city.value,
                lots=s.lots,
                availability_as_of=s.as_of,
                stale=s.stale,
            )
            for s in source_statuses(ct.store, ct.clock.now())
        ]
        ok = all(s.lots > 0 and not s.stale for s in sources)
        usage = [
            UsageDTO(
                meter=meter,  # type: ignore[arg-type]
                period=ct.usage.period,
                used=ct.usage.used(meter),
                limit=ct.usage.limit(meter),
            )
            for meter in ct.usage.meters
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
        except PlacesUnavailable as exc:
            raise ApiError(503, "places_unavailable", str(exc)) from exc
        except PlacesError as exc:
            raise ApiError(502, "places_unavailable", str(exc)) from exc
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
            results=[to_bike_dto(h, GeoPoint(lat, lng)) for h in found.hits],
            unavailable_cities=[city.value for city in found.missing],
        )

    @app.get("/api/v1/curb/nearby", response_model=CurbSearchResponse, responses=responses)
    def curb_nearby(lat: Lat, lng: Lng) -> CurbSearchResponse:
        try:
            found = c().search_curb.execute(GeoPoint(lat, lng))
        except CurbUnconfigured as exc:
            raise ApiError(503, "curb_unconfigured", str(exc)) from exc
        except SourceError as exc:
            raise ApiError(502, "curb_unavailable", str(exc)) from exc
        return CurbSearchResponse(
            origin=OriginDTO(lat=lat, lng=lng),
            radius_m=found.radius_m,
            expanded=found.expanded,
            results=[to_curb_dto(h) for h in found.hits],
            unavailable_cities=[city.value for city in found.missing],
        )

    @app.get("/api/v1/parking/typical", response_model=TypicalDayResponse, responses=responses)
    def parking_typical(
        lot: Annotated[str, Query(max_length=80, description="Lot id, e.g. taipei:TPE0044")],
        weekday: Annotated[int | None, Query(ge=0, le=6, description="0 = Monday")] = None,
    ) -> TypicalDayResponse:
        city_text, _, source_id = lot.partition(":")
        try:
            city = City(city_text)
        except ValueError as exc:
            raise ApiError(422, "invalid_lot", f"not a lot id: {lot!r}") from exc
        if not source_id:
            raise ApiError(422, "invalid_lot", f"not a lot id: {lot!r}")
        day = c().insights.typical(lot, city, weekday)
        return TypicalDayResponse(
            lot_id=lot,
            weekday=day.weekday,
            days_used=day.days_used,
            min_days=MIN_WEEKS,
            slots=[
                TypicalSlotDTO(minute=s.minute, median=s.median, samples=s.samples)
                for s in day.slots
            ],
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
        insights = ct.insights.for_hits(result.hits)
        now = ct.clock.now()
        return ParkingSearchResponse(
            origin=OriginDTO(lat=center.lat, lng=center.lng, label=label),
            alternatives=alternatives,
            results=[
                to_lot_dto(h, center, insights[h.ranked.lot.id], now) for h in result.hits
            ],
            meta=SearchMetaDTO(
                radius_m=result.radius_m,
                mode=mode.value,
                count=len(result.hits),
                pool_size=result.pool_size,
                walking=result.walking.value,
                stale_sources=[
                    StaleSourceDTO(city=city.value, as_of=as_of)
                    for city, as_of in stale_cities(ct.store, ct.clock.now()).items()
                ],
            ),
        )

    # Last, so every /api route wins; serves the built client when one exists.
    if settings.web_dist is not None:
        app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")

    return app
