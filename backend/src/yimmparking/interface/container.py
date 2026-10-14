"""Composition root: the only place concrete adapters are chosen and wired together."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import httpx

from yimmparking.adapters.clock import SystemClock
from yimmparking.adapters.geocode.google import ENDPOINT as GEOCODE_ENDPOINT
from yimmparking.adapters.geocode.google import GoogleGeocoder
from yimmparking.adapters.iparking.findata import FindataDirectory
from yimmparking.adapters.places.google_places import ENDPOINT as PLACES_ENDPOINT
from yimmparking.adapters.places.google_places import GooglePlaces
from yimmparking.adapters.routes.google_routes import ENDPOINT as ROUTES_ENDPOINT
from yimmparking.adapters.routes.google_routes import GoogleRoutes
from yimmparking.adapters.sources.new_taipei import NewTaipeiFeed
from yimmparking.adapters.sources.taipei import TaipeiFeed
from yimmparking.adapters.sources.youbike import NewTaipeiBikeFeed, TaipeiBikeFeed
from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.application.limits import (
    GEOCODING,
    PLACES_NEARBY,
    ROUTES_ELEMENTS,
    LimitedGeocoder,
    LimitedPlaces,
    LimitedRouter,
    UsageGate,
)
from yimmparking.application.place_cache import CachedPlaces
from yimmparking.application.ports import (
    Clock,
    Geocoder,
    ParkingFeed,
    PlaceSource,
    TravelRouter,
)
from yimmparking.application.refresh import RefreshAvailability, RefreshLots
from yimmparking.application.route_cache import CachedRouter
from yimmparking.application.search import (
    ResolveAddress,
    SearchNearbyFood,
    SearchNearbyParking,
)
from yimmparking.application.search_bikes import SearchNearbyBikes
from yimmparking.interface.settings import Settings


@dataclass(slots=True)
class Container:
    settings: Settings
    http: httpx.Client
    clock: Clock
    store: SqliteStore
    feeds: list[ParkingFeed]
    geocoder: Geocoder
    places: PlaceSource
    refresh_lots: RefreshLots
    refresh_availability: RefreshAvailability
    search_parking: SearchNearbyParking
    resolve_address: ResolveAddress
    search_food: SearchNearbyFood
    search_bikes: SearchNearbyBikes
    usage: UsageGate
    router: TravelRouter | None

    @property
    def geocoder_configured(self) -> bool:
        return self.settings.google_maps_api_key is not None

    def close(self) -> None:
        self.http.close()
        self.store.close()


def build_container(settings: Settings, *, http: httpx.Client | None = None) -> Container:
    http = http or httpx.Client(
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent},
    )
    clock = SystemClock()
    store = SqliteStore(settings.db_path)

    feeds: list[ParkingFeed] = [TaipeiFeed(http), NewTaipeiFeed(http, now=clock.now)]
    usage = UsageGate(
        store,
        clock,
        {
            GEOCODING: settings.geocode_monthly_limit,
            PLACES_NEARBY: settings.places_monthly_limit,
            ROUTES_ELEMENTS: settings.routes_monthly_limit,
        },
    )
    geocoder: Geocoder = GoogleGeocoder(
        http,
        settings.google_maps_api_key,
        endpoint=settings.geocode_endpoint or GEOCODE_ENDPOINT,
    )
    places: PlaceSource = GooglePlaces(
        http,
        settings.google_maps_api_key,
        endpoint=settings.places_endpoint or PLACES_ENDPOINT,
    )
    if settings.google_maps_api_key:
        # Without a key the adapters refuse before any request, so there is nothing to count.
        geocoder = LimitedGeocoder(geocoder, usage)
        places = LimitedPlaces(places, usage)
        if settings.food_cache_ttl_hours > 0:
            # Outside the limiter: a cache hit makes no call and so spends no quota.
            places = CachedPlaces(
                places, store, clock, timedelta(hours=settings.food_cache_ttl_hours)
            )

    router: TravelRouter | None = None
    if settings.google_maps_api_key:
        router = LimitedRouter(
            GoogleRoutes(
                http,
                settings.google_maps_api_key,
                endpoint=settings.routes_endpoint or ROUTES_ENDPOINT,
            ),
            usage,
        )
        if settings.route_cache_ttl_days > 0:
            # Outside the limiter: a cached pair makes no request and spends no quota.
            router = CachedRouter(
                router, store, clock, timedelta(days=settings.route_cache_ttl_days)
            )

    return Container(
        settings=settings,
        http=http,
        clock=clock,
        store=store,
        feeds=feeds,
        geocoder=geocoder,
        places=places,
        refresh_lots=RefreshLots(feeds, FindataDirectory(http), store),
        refresh_availability=RefreshAvailability(feeds, store, clock),
        search_parking=SearchNearbyParking(store, clock, router=router),
        resolve_address=ResolveAddress(geocoder, store, clock),
        search_food=SearchNearbyFood(
            places,
            min_rating=settings.food_min_rating,
            min_reviews=settings.food_min_reviews,
            clock=clock,
        ),
        search_bikes=SearchNearbyBikes([TaipeiBikeFeed(http), NewTaipeiBikeFeed(http)], clock),
        usage=usage,
        router=router,
    )
