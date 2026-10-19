"""SQLite storage: lots, latest availability, an availability history, and the geocode cache.

The schema is created by idempotent, versioned migrations (`PRAGMA user_version`), so running
them against an existing database is always safe.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from yimmparking.application.search import GEOCODE_CACHE_TTL
from yimmparking.domain.geo import BoundingBox, GeoPoint
from yimmparking.domain.model import (
    AvailabilityBatch,
    Brand,
    BrandEvidence,
    City,
    GeocodeCandidate,
    ParkingLot,
    Place,
    RouteTime,
)
from yimmparking.domain.opening import OpeningPeriod

OBSERVATION_RETENTION = timedelta(days=14)
_IN_CHUNK = 500

# Migrations are applied by position and recorded in PRAGMA user_version, so this tuple is
# append-only: never insert or reorder. tests/unit/test_migrations.py pins the history.
_MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE parking_lot (
        id TEXT PRIMARY KEY,
        city TEXT NOT NULL,
        source_id TEXT NOT NULL,
        name TEXT NOT NULL,
        address TEXT NOT NULL,
        district TEXT NOT NULL,
        lat REAL NOT NULL,
        lng REAL NOT NULL,
        phone TEXT NOT NULL,
        total_car INTEGER,
        fee_text TEXT NOT NULL,
        service_time TEXT NOT NULL,
        kind TEXT NOT NULL,
        ev_charging_spaces INTEGER,
        accessible_spaces INTEGER,
        brand TEXT NOT NULL,
        brand_evidence TEXT NOT NULL,
        iparking_code TEXT
    );
    CREATE INDEX idx_parking_lot_geo ON parking_lot (lat, lng);
    CREATE INDEX idx_parking_lot_city ON parking_lot (city);

    CREATE TABLE availability_latest (
        lot_id TEXT PRIMARY KEY,
        city TEXT NOT NULL,
        count INTEGER,
        observed_at TEXT NOT NULL
    );

    CREATE TABLE availability_observation (
        lot_id TEXT NOT NULL,
        city TEXT NOT NULL,
        count INTEGER,
        observed_at TEXT NOT NULL,
        PRIMARY KEY (lot_id, observed_at)
    );
    CREATE INDEX idx_observation_time ON availability_observation (observed_at);

    CREATE TABLE geocode_cache (
        key TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    """,
    # v2: per-period counters for paid external APIs (self-imposed free-tier ceilings).
    """
    CREATE TABLE api_usage (
        meter TEXT NOT NULL,
        period TEXT NOT NULL,
        count INTEGER NOT NULL,
        PRIMARY KEY (meter, period)
    );
    """,
    # v3: provider results held for a bounded time so a repeated lookup is not billed twice.
    """
    CREATE TABLE place_cache (
        key TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    """,
    # v4: walking times between fixed points; seconds NULL means "no route".
    """
    CREATE TABLE walk_cache (
        key TEXT PRIMARY KEY,
        seconds INTEGER,
        meters INTEGER,
        expires_at TEXT NOT NULL
    );
    """,
)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SqliteStore:
    """Implements LotRepository and GeocodeCache on one SQLite file."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        # One shared connection guarded by a lock: the dataset is small and writes are rare.
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._migrate()

    # ---- schema ---------------------------------------------------------------------------

    def _migrate(self) -> None:
        with self._lock:
            current = self._conn.execute("PRAGMA user_version").fetchone()[0]
            for version, script in enumerate(_MIGRATIONS, start=1):
                if version <= current:
                    continue
                self._conn.executescript(
                    "BEGIN;" + script + f"PRAGMA user_version = {version};COMMIT;"
                )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- LotRepository --------------------------------------------------------------------

    def lot_count(self, city: City) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM parking_lot WHERE city = ?", (city.value,)
            ).fetchone()
        return int(row[0])

    def lot_ids(self, city: City) -> set[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM parking_lot WHERE city = ?", (city.value,)
            ).fetchall()
        return {r["id"] for r in rows}

    def iparking_codes(self, city: City) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, iparking_code FROM parking_lot "
                "WHERE city = ? AND iparking_code IS NOT NULL",
                (city.value,),
            ).fetchall()
        return {r["id"]: r["iparking_code"] for r in rows}

    def replace_lots(self, city: City, lots: list[ParkingLot]) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM parking_lot WHERE city = ?", (city.value,))
            self._conn.executemany(
                """
                INSERT INTO parking_lot (
                    id, city, source_id, name, address, district, lat, lng, phone, total_car,
                    fee_text, service_time, kind, ev_charging_spaces, accessible_spaces,
                    brand, brand_evidence, iparking_code
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        lot.id,
                        lot.city.value,
                        lot.source_id,
                        lot.name,
                        lot.address,
                        lot.district,
                        lot.location.lat,
                        lot.location.lng,
                        lot.phone,
                        lot.total_car,
                        lot.fee_text,
                        lot.service_time,
                        lot.kind,
                        lot.ev_charging_spaces,
                        lot.accessible_spaces,
                        lot.brand.value,
                        lot.brand_evidence.value,
                        lot.iparking_code,
                    )
                    for lot in lots
                ],
            )

    def lots_in_box(self, box: BoundingBox) -> list[ParkingLot]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM parking_lot WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                (box.min_lat, box.max_lat, box.min_lng, box.max_lng),
            ).fetchall()
        return [_lot_from_row(r) for r in rows]

    def record_availability(self, batch: AvailabilityBatch) -> None:
        observed = _iso(batch.observed_at)
        with self._lock, self._conn:
            self._conn.executemany(
                """
                INSERT OR IGNORE INTO availability_observation (lot_id, city, count, observed_at)
                VALUES (?,?,?,?)
                """,
                [(r.lot_id, batch.city.value, r.count, observed) for r in batch.readings],
            )
            # Only move "latest" forward: re-running with an older feed must not rewind it.
            self._conn.executemany(
                """
                INSERT INTO availability_latest (lot_id, city, count, observed_at)
                VALUES (?,?,?,?)
                ON CONFLICT(lot_id) DO UPDATE SET
                    count = excluded.count,
                    observed_at = excluded.observed_at
                WHERE excluded.observed_at >= availability_latest.observed_at
                """,
                [(r.lot_id, batch.city.value, r.count, observed) for r in batch.readings],
            )
            self._conn.execute(
                "DELETE FROM availability_observation WHERE observed_at < ?",
                (_iso(batch.observed_at - OBSERVATION_RETENTION),),
            )

    def latest_availability(self, lot_ids: list[str]) -> dict[str, tuple[int | None, datetime]]:
        out: dict[str, tuple[int | None, datetime]] = {}
        with self._lock:
            for chunk in _chunks(lot_ids, _IN_CHUNK):
                marks = ",".join("?" * len(chunk))
                rows = self._conn.execute(
                    f"SELECT lot_id, count, observed_at FROM availability_latest "
                    f"WHERE lot_id IN ({marks})",
                    chunk,
                ).fetchall()
                for r in rows:
                    out[r["lot_id"]] = (r["count"], _parse(r["observed_at"]))
        return out

    def last_availability_at(self) -> dict[City, datetime]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT city, MAX(observed_at) AS at FROM availability_latest GROUP BY city"
            ).fetchall()
        return {City(r["city"]): _parse(r["at"]) for r in rows}

    # ---- QuotaStore ----------------------------------------------------------------------

    def try_consume(self, meter: str, period: str, limit: int, amount: int = 1) -> bool:
        if amount <= 0:
            return True
        if limit <= 0 or amount > limit:
            return False
        with self._lock, self._conn:
            # One statement, so check-and-increment cannot interleave with another caller.
            cur = self._conn.execute(
                """
                INSERT INTO api_usage (meter, period, count) VALUES (?, ?, ?)
                ON CONFLICT(meter, period) DO UPDATE SET count = count + ?
                WHERE count + ? <= ?
                """,
                (meter, period, amount, amount, amount, limit),
            )
        return cur.rowcount == 1

    def used(self, meter: str, period: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT count FROM api_usage WHERE meter = ? AND period = ?", (meter, period)
            ).fetchone()
        return int(row["count"]) if row else 0

    # ---- RouteCache -----------------------------------------------------------------------

    def get_routes(self, keys: list[str], now: datetime) -> dict[str, RouteTime | None]:
        out: dict[str, RouteTime | None] = {}
        with self._lock:
            for chunk in _chunks(keys, _IN_CHUNK):
                marks = ",".join("?" * len(chunk))
                rows = self._conn.execute(
                    f"SELECT key, seconds, meters, expires_at FROM walk_cache "
                    f"WHERE key IN ({marks})",
                    chunk,
                ).fetchall()
                for r in rows:
                    if _parse(r["expires_at"]) <= now:
                        continue
                    out[r["key"]] = (
                        None
                        if r["seconds"] is None
                        else RouteTime(seconds=r["seconds"], meters=r["meters"])
                    )
        return out

    def put_routes(self, walks: dict[str, RouteTime | None], now: datetime, ttl: timedelta) -> None:
        expires = _iso(now + ttl)
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO walk_cache (key, seconds, meters, expires_at) "
                "VALUES (?,?,?,?)",
                [
                    (k, None if w is None else w.seconds, None if w is None else w.meters, expires)
                    for k, w in walks.items()
                ],
            )

    def purge_expired_routes(self, now: datetime) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM walk_cache WHERE expires_at <= ?", (_iso(now),))
        return cur.rowcount

    # ---- PlaceCache ----------------------------------------------------------------------

    def get_places(self, key: str, now: datetime) -> list[Place] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload, expires_at FROM place_cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None or _parse(row["expires_at"]) <= now:
            return None
        return [_place_from_dict(item) for item in json.loads(row["payload"])]

    def put_places(self, key: str, places: list[Place], now: datetime, ttl: timedelta) -> None:
        payload = json.dumps([_place_to_dict(p) for p in places], ensure_ascii=False)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO place_cache (key, payload, expires_at) VALUES (?,?,?)",
                (key, payload, _iso(now + ttl)),
            )

    def purge_expired_places(self, now: datetime) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM place_cache WHERE expires_at <= ?", (_iso(now),))
        return cur.rowcount

    # ---- GeocodeCache ---------------------------------------------------------------------
    # Only coordinates and the place id are stored — never the formatted address — which is the
    # part of a Google geocode result its terms allow to be cached, and only for a limited time.

    def get(self, key: str, now: datetime) -> list[GeocodeCandidate] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload, expires_at FROM geocode_cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None or _parse(row["expires_at"]) <= now:
            return None
        return [
            GeocodeCandidate(
                formatted_address=item.get("label", key),
                location=GeoPoint(item["lat"], item["lng"]),
                place_id=item.get("place_id"),
            )
            for item in json.loads(row["payload"])
        ]

    def put(self, key: str, candidates: list[GeocodeCandidate], now: datetime) -> None:
        payload = json.dumps(
            [
                {"lat": c.location.lat, "lng": c.location.lng, "place_id": c.place_id}
                for c in candidates
            ]
        )
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO geocode_cache (key, payload, expires_at) VALUES (?,?,?)",
                (key, payload, _iso(now + GEOCODE_CACHE_TTL)),
            )

    def purge_expired(self, now: datetime) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM geocode_cache WHERE expires_at <= ?", (_iso(now),)
            )
        return cur.rowcount


def _place_to_dict(p: Place) -> dict[str, object]:
    return {
        "id": p.id,
        "name": p.name,
        "lat": p.location.lat,
        "lng": p.location.lng,
        "address": p.address,
        "rating": p.rating,
        "user_rating_count": p.user_rating_count,
        "price_level": p.price_level,
        "primary_type": p.primary_type,
        "primary_type_code": p.primary_type_code,
        "opening": ([[o.start, o.end] for o in p.opening] if p.opening is not None else None),
        "maps_uri": p.maps_uri,
        "walk_seconds": p.walking.seconds if p.walking else None,
        "walk_meters": p.walking.meters if p.walking else None,
    }


def _place_from_dict(d: dict[str, Any]) -> Place:
    return Place(
        id=d["id"],
        name=d["name"],
        location=GeoPoint(d["lat"], d["lng"]),
        address=d.get("address", ""),
        rating=d.get("rating"),
        user_rating_count=d.get("user_rating_count"),
        price_level=d.get("price_level"),
        primary_type=d.get("primary_type"),
        primary_type_code=d.get("primary_type_code"),
        opening=(
            tuple(OpeningPeriod(start=s, end=e) for s, e in d["opening"])
            if d.get("opening") is not None
            else None
        ),
        maps_uri=d.get("maps_uri"),
        walking=(
            RouteTime(seconds=d["walk_seconds"], meters=d["walk_meters"])
            if d.get("walk_seconds") is not None
            else None
        ),
    )


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _lot_from_row(r: sqlite3.Row) -> ParkingLot:
    return ParkingLot(
        id=r["id"],
        city=City(r["city"]),
        source_id=r["source_id"],
        name=r["name"],
        address=r["address"],
        district=r["district"],
        location=GeoPoint(r["lat"], r["lng"]),
        phone=r["phone"],
        total_car=r["total_car"],
        fee_text=r["fee_text"],
        service_time=r["service_time"],
        kind=r["kind"],
        ev_charging_spaces=r["ev_charging_spaces"],
        accessible_spaces=r["accessible_spaces"],
        brand=Brand(r["brand"]),
        brand_evidence=BrandEvidence(r["brand_evidence"]),
        iparking_code=r["iparking_code"],
    )
