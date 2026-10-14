"""Ports: the interfaces the application layer needs from the outside world.

Adapters implement these; the application layer and domain never import an adapter.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from yimmparking.domain.geo import BoundingBox, GeoPoint
from yimmparking.domain.model import (
    AvailabilityBatch,
    BikeStation,
    City,
    GeocodeCandidate,
    IParkingStation,
    ParkingLot,
    Place,
    RouteTime,
    TravelMode,
)


class SourceError(Exception):
    """A data source could not be read or returned something unusable."""


class GeocodingUnavailable(Exception):
    """No geocoder is configured, or it is not reachable."""


class GeocodingError(Exception):
    """The geocoder answered, but with an error."""


class PlacesError(Exception):
    """The places provider answered with an error or is not configured."""


class RoutesError(Exception):
    """The routing provider answered with an error or is not configured."""


class QuotaExceeded(Exception):
    """A paid external API reached its self-imposed monthly limit; the call was not made."""

    def __init__(self, meter: str, limit: int, period: str) -> None:
        super().__init__(f"{meter} monthly limit of {limit} reached for {period}")
        self.meter = meter
        self.limit = limit
        self.period = period


class Clock(Protocol):
    def now(self) -> datetime: ...


class ParkingFeed(Protocol):
    """One city's government feeds: static lot data plus real-time availability."""

    city: City

    def fetch_lots(self) -> list[ParkingLot]: ...

    def fetch_availability(self) -> AvailabilityBatch: ...


class BikeFeed(Protocol):
    """One city's real-time YouBike station feed."""

    city: City

    def fetch_stations(self) -> list[BikeStation]: ...


class IParkingDirectory(Protocol):
    def fetch_stations(self) -> list[IParkingStation]: ...


class Geocoder(Protocol):
    def geocode(self, query: str) -> list[GeocodeCandidate]: ...


class GeocodeCache(Protocol):
    def get(self, key: str, now: datetime) -> list[GeocodeCandidate] | None: ...

    def put(self, key: str, candidates: list[GeocodeCandidate], now: datetime) -> None: ...

    def purge_expired(self, now: datetime) -> int: ...


class TravelRouter(Protocol):
    def travel_times(
        self, origin: GeoPoint, destinations: list[tuple[str, GeoPoint]], mode: TravelMode
    ) -> dict[str, RouteTime | None]:
        """Travel time by `mode` from `origin` to each `(key, point)`. A destination with no route
        maps to None. Billed per destination and per mode, so callers pass only what they need."""


class RouteCache(Protocol):
    def get_routes(self, keys: list[str], now: datetime) -> dict[str, RouteTime | None]:
        """Entries present and unexpired. A key mapped to None means "no route", cached too."""

    def put_routes(
        self, walks: dict[str, RouteTime | None], now: datetime, ttl: timedelta
    ) -> None: ...

    def purge_expired_routes(self, now: datetime) -> int: ...


class PlaceCache(Protocol):
    def get_places(self, key: str, now: datetime) -> list[Place] | None: ...

    def put_places(self, key: str, places: list[Place], now: datetime, ttl: timedelta) -> None: ...

    def purge_expired_places(self, now: datetime) -> int: ...


class QuotaStore(Protocol):
    """Durable per-period call counters, so a limit survives restarts."""

    def try_consume(self, meter: str, period: str, limit: int, amount: int = 1) -> bool:
        """Atomically add `amount` calls if the total stays within `limit`, else return False."""

    def used(self, meter: str, period: str) -> int: ...


class PlaceSource(Protocol):
    def nearby_food(
        self,
        center: GeoPoint,
        radius_m: int,
        limit: int,
        min_rating: float = 0.0,
        origin: GeoPoint | None = None,
    ) -> list[Place]:
        """Places within roughly `radius_m` of `center`, already filtered to `min_rating` or better
        by the provider, so that the limited result slots are not spent on low-rated places."""


class LotRepository(Protocol):
    def lot_count(self, city: City) -> int: ...

    def lot_ids(self, city: City) -> set[str]: ...

    def replace_lots(self, city: City, lots: list[ParkingLot]) -> None:
        """Atomically replace every lot of `city`."""

    def lots_in_box(self, box: BoundingBox) -> list[ParkingLot]: ...

    def record_availability(self, batch: AvailabilityBatch) -> None: ...

    def latest_availability(self, lot_ids: list[str]) -> dict[str, tuple[int | None, datetime]]: ...

    def last_availability_at(self) -> dict[City, datetime]: ...
