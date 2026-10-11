"""新北市 public off-street parking feeds (open data platform, paged JSON, no key)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from yimmparking.adapters.sources.common import get_json, in_taiwan, to_float, to_int
from yimmparking.application.ports import SourceError
from yimmparking.domain.geo import twd97_to_wgs84
from yimmparking.domain.model import (
    AvailabilityBatch,
    AvailabilityReading,
    City,
    ParkingLot,
)

log = logging.getLogger(__name__)

API = "https://data.ntpc.gov.tw/api/datasets/{dataset}/json"
INFO_DATASET = "b1464ef0-9c7c-4a6f-abf7-6bdf32847e68"
AVAILABLE_DATASET = "e09b35a5-a738-48cc-b0f5-570b67ad9c78"
PAGE_SIZE = 1000
MAX_PAGES = 20


def _clean(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _completeness(row: dict[str, Any]) -> tuple[int, int]:
    """Prefer the duplicate row that carries the most information."""
    filled = sum(1 for value in row.values() if str(value or "").strip())
    return filled, to_int(row.get("TOTALCAR")) or 0


def parse_lot(row: dict[str, Any]) -> ParkingLot | None:
    source_id = _clean(row, "ID")
    x, y = to_float(row.get("TW97X")), to_float(row.get("TW97Y"))
    if not source_id or x is None or y is None:
        return None
    try:
        location = twd97_to_wgs84(x, y)
    except ValueError:
        return None
    if not in_taiwan(location):
        return None
    return ParkingLot(
        id=f"{City.NEW_TAIPEI.value}:{source_id}",
        city=City.NEW_TAIPEI,
        source_id=source_id,
        name=_clean(row, "NAME"),
        address=_clean(row, "ADDRESS"),
        district=_clean(row, "AREA"),
        location=location,
        phone=_clean(row, "TEL"),
        total_car=to_int(row.get("TOTALCAR")),
        fee_text=_clean(row, "PAYEX"),
        service_time=_clean(row, "SERVICETIME"),
        kind=_clean(row, "SUMMARY"),
    )


class NewTaipeiFeed:
    city = City.NEW_TAIPEI

    def __init__(
        self,
        http: httpx.Client,
        info_dataset: str = INFO_DATASET,
        available_dataset: str = AVAILABLE_DATASET,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._http = http
        self._info_url = API.format(dataset=info_dataset)
        self._available_url = API.format(dataset=available_dataset)
        self._now = now

    def _fetch_all(self, url: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in range(MAX_PAGES):
            chunk = get_json(self._http, url, params={"page": page, "size": PAGE_SIZE})
            if not isinstance(chunk, list):
                raise SourceError(f"{url}: expected a JSON array")
            rows.extend(row for row in chunk if isinstance(row, dict))
            if len(chunk) < PAGE_SIZE:
                return rows
        raise SourceError(f"{url}: more than {MAX_PAGES} pages, refusing to continue")

    def fetch_lots(self) -> list[ParkingLot]:
        # The feed repeats some ids with different completeness; keep the fullest row per id.
        best: dict[str, dict[str, Any]] = {}
        for row in self._fetch_all(self._info_url):
            source_id = _clean(row, "ID")
            if not source_id:
                continue
            current = best.get(source_id)
            if current is None or _completeness(row) > _completeness(current):
                best[source_id] = row

        lots = [lot for row in best.values() if (lot := parse_lot(row)) is not None]
        dropped = len(best) - len(lots)
        if dropped:
            log.warning("new_taipei: dropped %d lots without a usable coordinate", dropped)
        if not lots:
            raise SourceError(f"{self._info_url}: no usable lots")
        return lots

    def fetch_availability(self) -> AvailabilityBatch:
        merged: dict[str, int | None] = {}
        for row in self._fetch_all(self._available_url):
            source_id = _clean(row, "ID")
            if not source_id:
                continue
            count = to_int(row.get("AVAILABLECAR"))
            if count is not None and count < 0:
                count = None  # -9 means the operator supplies no real-time data
            # Duplicated ids carry the same value in practice; if they ever disagree, a real
            # reading beats "no data".
            if source_id not in merged or merged[source_id] is None:
                merged[source_id] = count

        readings = tuple(
            AvailabilityReading(lot_id=f"{City.NEW_TAIPEI.value}:{sid}", count=count)
            for sid, count in merged.items()
        )
        # The feed carries no timestamp of its own, so the fetch time stands in for it.
        return AvailabilityBatch(city=City.NEW_TAIPEI, observed_at=self._now(), readings=readings)
