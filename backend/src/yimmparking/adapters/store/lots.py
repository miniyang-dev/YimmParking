"""Parking lots and their latest availability (LotRepository)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from yimmparking.adapters.store import history
from yimmparking.adapters.store.database import IN_CHUNK, Database, chunks, from_iso, to_iso
from yimmparking.domain.geo import BoundingBox, GeoPoint
from yimmparking.domain.model import AvailabilityBatch, Brand, BrandEvidence, City, ParkingLot


class SqliteLots:
    """Lots per city, replaced whole; the latest reading per lot, only ever moved forward.

    Every batch also goes into the change-only history, in the same transaction.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def lot_count(self, city: City) -> int:
        with self._db.read() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM parking_lot WHERE city = ?", (city.value,)
            ).fetchone()
        return int(row[0])

    def lot_ids(self, city: City) -> set[str]:
        with self._db.read() as conn:
            rows = conn.execute(
                "SELECT id FROM parking_lot WHERE city = ?", (city.value,)
            ).fetchall()
        return {r["id"] for r in rows}

    def iparking_codes(self, city: City) -> dict[str, str]:
        with self._db.read() as conn:
            rows = conn.execute(
                "SELECT id, iparking_code FROM parking_lot "
                "WHERE city = ? AND iparking_code IS NOT NULL",
                (city.value,),
            ).fetchall()
        return {r["id"]: r["iparking_code"] for r in rows}

    def replace_lots(self, city: City, lots: list[ParkingLot]) -> None:
        with self._db.write() as conn:
            conn.execute("DELETE FROM parking_lot WHERE city = ?", (city.value,))
            conn.executemany(
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
        with self._db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM parking_lot WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                (box.min_lat, box.max_lat, box.min_lng, box.max_lng),
            ).fetchall()
        return [_lot_from_row(r) for r in rows]

    def record_availability(self, batch: AvailabilityBatch) -> None:
        observed = to_iso(batch.observed_at)
        with self._db.write() as conn:
            previous = self.latest_availability([r.lot_id for r in batch.readings])
            history.record(conn, batch, previous)
            # Only move "latest" forward: re-running with an older feed must not rewind it.
            conn.executemany(
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

    def latest_availability(self, lot_ids: list[str]) -> dict[str, tuple[int | None, datetime]]:
        out: dict[str, tuple[int | None, datetime]] = {}
        with self._db.read() as conn:
            for chunk in chunks(lot_ids, IN_CHUNK):
                marks = ",".join("?" * len(chunk))
                rows = conn.execute(
                    f"SELECT lot_id, count, observed_at FROM availability_latest "
                    f"WHERE lot_id IN ({marks})",
                    chunk,
                ).fetchall()
                for r in rows:
                    out[r["lot_id"]] = (r["count"], from_iso(r["observed_at"]))
        return out

    def last_availability_at(self) -> dict[City, datetime]:
        with self._db.read() as conn:
            rows = conn.execute(
                "SELECT city, MAX(observed_at) AS at FROM availability_latest GROUP BY city"
            ).fetchall()
        return {City(r["city"]): from_iso(r["at"]) for r in rows}


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
