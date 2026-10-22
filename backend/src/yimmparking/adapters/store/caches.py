"""Result caches in front of billed providers: geocodes, food places, walking times."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from yimmparking.adapters.store.database import IN_CHUNK, Database, chunks, from_iso, to_iso
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import GeocodeCandidate, Place, RouteTime
from yimmparking.domain.opening import OpeningPeriod


class SqliteRouteCache:
    """Walking times between fixed points; seconds NULL means "no route"."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def get_routes(self, keys: list[str], now: datetime) -> dict[str, RouteTime | None]:
        out: dict[str, RouteTime | None] = {}
        with self._db.read() as conn:
            for chunk in chunks(keys, IN_CHUNK):
                marks = ",".join("?" * len(chunk))
                rows = conn.execute(
                    f"SELECT key, seconds, meters, expires_at FROM walk_cache "
                    f"WHERE key IN ({marks})",
                    chunk,
                ).fetchall()
                for r in rows:
                    if from_iso(r["expires_at"]) <= now:
                        continue
                    out[r["key"]] = (
                        None
                        if r["seconds"] is None
                        else RouteTime(seconds=r["seconds"], meters=r["meters"])
                    )
        return out

    def put_routes(self, walks: dict[str, RouteTime | None], now: datetime, ttl: timedelta) -> None:
        expires = to_iso(now + ttl)
        with self._db.write() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO walk_cache (key, seconds, meters, expires_at) "
                "VALUES (?,?,?,?)",
                [
                    (k, None if w is None else w.seconds, None if w is None else w.meters, expires)
                    for k, w in walks.items()
                ],
            )

    def purge_expired_routes(self, now: datetime) -> int:
        with self._db.write() as conn:
            cur = conn.execute("DELETE FROM walk_cache WHERE expires_at <= ?", (to_iso(now),))
        return cur.rowcount


class SqlitePlaceCache:
    """Food lookups, held for a bounded time."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def get_places(self, key: str, now: datetime) -> list[Place] | None:
        with self._db.read() as conn:
            row = conn.execute(
                "SELECT payload, expires_at FROM place_cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None or from_iso(row["expires_at"]) <= now:
            return None
        return [_place_from_dict(item) for item in json.loads(row["payload"])]

    def put_places(self, key: str, places: list[Place], now: datetime, ttl: timedelta) -> None:
        payload = json.dumps([_place_to_dict(p) for p in places], ensure_ascii=False)
        with self._db.write() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO place_cache (key, payload, expires_at) VALUES (?,?,?)",
                (key, payload, to_iso(now + ttl)),
            )

    def purge_expired_places(self, now: datetime) -> int:
        with self._db.write() as conn:
            cur = conn.execute("DELETE FROM place_cache WHERE expires_at <= ?", (to_iso(now),))
        return cur.rowcount


class SqliteGeocodeCache:
    """Address lookups, as coordinates only."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # Only coordinates and the place id are stored — never the formatted address — which is the
    # part of a Google geocode result its terms allow to be cached, and only for a limited time.

    def get_geocode(self, key: str, now: datetime) -> list[GeocodeCandidate] | None:
        with self._db.read() as conn:
            row = conn.execute(
                "SELECT payload, expires_at FROM geocode_cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None or from_iso(row["expires_at"]) <= now:
            return None
        return [
            GeocodeCandidate(
                formatted_address=item.get("label", key),
                location=GeoPoint(item["lat"], item["lng"]),
                place_id=item.get("place_id"),
            )
            for item in json.loads(row["payload"])
        ]

    def put_geocode(
        self, key: str, candidates: list[GeocodeCandidate], now: datetime, ttl: timedelta
    ) -> None:
        payload = json.dumps(
            [
                {"lat": c.location.lat, "lng": c.location.lng, "place_id": c.place_id}
                for c in candidates
            ]
        )
        with self._db.write() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO geocode_cache (key, payload, expires_at) VALUES (?,?,?)",
                (key, payload, to_iso(now + ttl)),
            )

    def purge_expired_geocodes(self, now: datetime) -> int:
        with self._db.write() as conn:
            cur = conn.execute(
                "DELETE FROM geocode_cache WHERE expires_at <= ?", (to_iso(now),)
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
