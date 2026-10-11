"""Small helpers shared by the government feed adapters."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from yimmparking.application.ports import SourceError
from yimmparking.domain.geo import GeoPoint

log = logging.getLogger(__name__)

# Rough envelope of Taiwan proper; anything outside is a corrupt coordinate, not a lot.
_TAIWAN_LAT = (21.5, 25.5)
_TAIWAN_LNG = (119.0, 122.5)


def get_json(http: httpx.Client, url: str, *, params: dict[str, Any] | None = None) -> Any:
    try:
        response = http.get(url, params=params)
        response.raise_for_status()
        # Some feeds are served with a UTF-8 BOM, which `response.json()` rejects.
        return json.loads(response.content.decode("utf-8-sig"))
    except (httpx.HTTPError, ValueError) as exc:
        raise SourceError(f"{url}: {exc}") from exc


def to_int(value: Any) -> int | None:
    """Parse the loosely typed integers these feeds emit ('17', 17, '', None, '17.0')."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def in_taiwan(point: GeoPoint) -> bool:
    return _TAIWAN_LAT[0] <= point.lat <= _TAIWAN_LAT[1] and (
        _TAIWAN_LNG[0] <= point.lng <= _TAIWAN_LNG[1]
    )
