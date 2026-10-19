"""Ingestion use cases: pull government feeds and persist them.

Both are idempotent and default to dry-run: they fetch, validate and report, but only write
when asked to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from yimmparking.application.ports import (
    Clock,
    IParkingDirectory,
    LotRepository,
    ParkingFeed,
    SourceError,
)
from yimmparking.domain.brand import BrandClassifier
from yimmparking.domain.iparking import match_iparking
from yimmparking.domain.model import Brand, City, IParkingStation, ParkingLot

log = logging.getLogger(__name__)

# A feed that suddenly returns far fewer lots than we already hold is more likely broken than
# real, and replacing good data with it would silently hollow out the search.
MIN_KEEP_RATIO = 0.5


@dataclass(slots=True)
class CityReport:
    city: City
    fetched: int = 0
    written: bool = False
    brand_counts: dict[str, int] = field(default_factory=dict)
    brand_by_phone: int = 0
    iparking_matched: int = 0
    error: str | None = None


@dataclass(slots=True)
class LotsReport:
    dry_run: bool
    iparking_stations: int = 0
    iparking_error: str | None = None  # directory unavailable; flags already held were kept
    cities: list[CityReport] = field(default_factory=list)


@dataclass(slots=True)
class AvailabilityCityReport:
    city: City
    readings: int = 0
    known: int = 0
    unknown: int = 0
    orphans: int = 0
    written: bool = False
    error: str | None = None


@dataclass(slots=True)
class AvailabilityReport:
    dry_run: bool
    cities: list[AvailabilityCityReport] = field(default_factory=list)


class RefreshLots:
    def __init__(
        self,
        feeds: list[ParkingFeed],
        directory: IParkingDirectory,
        repo: LotRepository,
        classifier: BrandClassifier | None = None,
    ) -> None:
        self._feeds = feeds
        self._directory = directory
        self._repo = repo
        self._classifier = classifier or BrandClassifier()

    def run(self, *, dry_run: bool = True) -> LotsReport:
        report = LotsReport(dry_run=dry_run)

        stations: list[IParkingStation] | None = None
        try:
            stations = self._directory.fetch_stations()
        except SourceError as exc:
            # iParking is an enrichment: its absence must not block the government data.
            log.warning("iParking directory unavailable, keeping the flags already held: %s", exc)
            report.iparking_error = str(exc)
        report.iparking_stations = len(stations) if stations is not None else 0

        for feed in self._feeds:
            city_report = CityReport(city=feed.city)
            report.cities.append(city_report)
            try:
                lots = [self._classifier.apply(lot) for lot in feed.fetch_lots()]
            except SourceError as exc:
                log.warning("lot feed for %s failed: %s", feed.city, exc)
                city_report.error = str(exc)
                continue

            if stations is not None:
                matches = match_iparking(lots, stations)
            else:
                matches = self._held_iparking(feed.city, lots)
            lots = [
                replace(lot, iparking_code=matches[lot.id]) if lot.id in matches else lot
                for lot in lots
            ]

            city_report.fetched = len(lots)
            for brand in Brand:
                city_report.brand_counts[brand.value] = sum(1 for lot in lots if lot.brand is brand)
            city_report.brand_by_phone = sum(
                1 for lot in lots if lot.brand_evidence.value == "phone"
            )
            city_report.iparking_matched = len(matches)

            existing = self._repo.lot_count(feed.city)
            if existing and len(lots) < existing * MIN_KEEP_RATIO:
                city_report.error = (
                    f"refusing to replace {existing} lots with {len(lots)}: feed looks truncated"
                )
                log.warning("%s: %s", feed.city, city_report.error)
                continue

            if not dry_run:
                self._repo.replace_lots(feed.city, lots)
                city_report.written = True
        return report

    def _held_iparking(self, city: City, lots: list[ParkingLot]) -> dict[str, str]:
        """Without the directory, each lot keeps the flag it already had.

        Replacing the lots would otherwise drop every iParking flag until the next successful
        refresh, which silently moves those lots out of their vendor section. Only 嘟嘟房 lots
        are eligible, exactly as when matching against the directory.
        """
        held = self._repo.iparking_codes(city)
        return {
            lot.id: held[lot.id]
            for lot in lots
            if lot.id in held and lot.brand is Brand.DODOHOME
        }


class RefreshAvailability:
    def __init__(self, feeds: list[ParkingFeed], repo: LotRepository, clock: Clock) -> None:
        self._feeds = feeds
        self._repo = repo
        self._clock = clock

    def run(self, *, dry_run: bool = True) -> AvailabilityReport:
        report = AvailabilityReport(dry_run=dry_run)
        for feed in self._feeds:
            city_report = AvailabilityCityReport(city=feed.city)
            report.cities.append(city_report)
            try:
                batch = feed.fetch_availability()
            except SourceError as exc:
                log.warning("availability feed for %s failed: %s", feed.city, exc)
                city_report.error = str(exc)
                continue

            city_report.readings = len(batch.readings)
            city_report.known = sum(1 for r in batch.readings if r.count is not None)
            city_report.unknown = city_report.readings - city_report.known
            # Readings for lots we do not hold are still recorded (a static refresh may be
            # pending) but counted, so a feed that stops matching our lots is visible.
            held = self._repo.lot_ids(feed.city)
            city_report.orphans = sum(1 for r in batch.readings if r.lot_id not in held)

            if not dry_run:
                self._repo.record_availability(batch)
                city_report.written = True
        return report
