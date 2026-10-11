"""Geographic value objects and pure geodesy helpers. No I/O."""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000.0
_METERS_PER_DEGREE_LAT = 111_320.0


@dataclass(frozen=True, slots=True)
class GeoPoint:
    lat: float
    lng: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.lat <= 90.0:
            raise ValueError(f"latitude out of range: {self.lat}")
        if not -180.0 <= self.lng <= 180.0:
            raise ValueError(f"longitude out of range: {self.lng}")


@dataclass(frozen=True, slots=True)
class BoundingBox:
    min_lat: float
    min_lng: float
    max_lat: float
    max_lng: float


def haversine_m(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance in meters."""
    phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
    d_phi = phi2 - phi1
    d_lambda = math.radians(b.lng - a.lng)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def initial_bearing_deg(origin: GeoPoint, target: GeoPoint) -> float:
    """Compass bearing in degrees [0, 360) from `origin` towards `target`."""
    phi1, phi2 = math.radians(origin.lat), math.radians(target.lat)
    d_lambda = math.radians(target.lng - origin.lng)
    y = math.sin(d_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def bounding_box(center: GeoPoint, radius_m: float) -> BoundingBox:
    """Axis-aligned box that fully contains the circle of `radius_m` around `center`."""
    d_lat = radius_m / _METERS_PER_DEGREE_LAT
    cos_lat = max(math.cos(math.radians(center.lat)), 1e-6)
    d_lng = radius_m / (_METERS_PER_DEGREE_LAT * cos_lat)
    return BoundingBox(
        min_lat=center.lat - d_lat,
        min_lng=center.lng - d_lng,
        max_lat=center.lat + d_lat,
        max_lng=center.lng + d_lng,
    )


def twd97_to_wgs84(easting: float, northing: float) -> GeoPoint:
    """Convert TWD97 / TM2 zone 121 (EPSG:3826) to WGS84 (inverse transverse Mercator)."""
    a = 6_378_137.0
    f = 1 / 298.257222101
    k0 = 0.9999
    lon0 = math.radians(121.0)
    false_easting = 250_000.0

    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    x = easting - false_easting
    m = northing / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    s, c, t = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = ep2 * c * c
    t1 = t * t
    n1 = a / math.sqrt(1 - e2 * s * s)
    r1 = a * (1 - e2) / (1 - e2 * s * s) ** 1.5
    d = x / (n1 * k0)

    lat = phi1 - (n1 * t / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    lon = (
        lon0
        + (
            d
            - (1 + 2 * t1 + c1) * d**3 / 6
            + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
        )
        / c
    )
    return GeoPoint(lat=math.degrees(lat), lng=math.degrees(lon))
