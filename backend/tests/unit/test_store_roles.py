"""Each SQLite store works on its own over a shared Database; SqliteStore only combines them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from yimmparking.adapters.store.caches import SqliteGeocodeCache, SqliteRouteCache
from yimmparking.adapters.store.database import Database
from yimmparking.adapters.store.history import SqliteHistory
from yimmparking.adapters.store.lots import SqliteLots
from yimmparking.adapters.store.quota import SqliteQuota
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import (
    AvailabilityBatch,
    AvailabilityReading,
    City,
    GeocodeCandidate,
    RouteTime,
)

NOW = datetime(2026, 10, 22, 4, 0, tzinfo=UTC)


def test_roles_share_one_database_without_knowing_each_other() -> None:
    db = Database(":memory:")
    lots, history, quota = SqliteLots(db), SqliteHistory(db), SqliteQuota(db)
    routes, geocodes = SqliteRouteCache(db), SqliteGeocodeCache(db)

    lots.record_availability(
        AvailabilityBatch(City.TAIPEI, NOW, (AvailabilityReading("taipei:a", 5),))
    )
    assert lots.latest_availability(["taipei:a"]) == {"taipei:a": (5, NOW)}
    # The lot store wrote the history in the same transaction; the history store reads it.
    assert history.availability_changes("taipei:a", NOW - timedelta(hours=1)) == [
        (int(NOW.timestamp()), 5)
    ]

    assert quota.try_consume("geocoding", "2026-10", limit=1)
    assert not quota.try_consume("geocoding", "2026-10", limit=1)

    routes.put_routes({"k": RouteTime(60, 80)}, NOW, timedelta(days=1))
    assert routes.get_routes(["k"], NOW) == {"k": RouteTime(60, 80)}

    candidate = GeocodeCandidate("市府路1號", GeoPoint(25.0375, 121.5637), "p1")
    geocodes.put_geocode("市府路1號", [candidate], NOW, timedelta(days=28))
    [cached] = geocodes.get_geocode("市府路1號", NOW) or []
    assert (cached.location, cached.place_id) == (candidate.location, "p1")
    db.close()


def test_a_failed_write_is_rolled_back() -> None:
    db = Database(":memory:")
    try:
        with db.write() as conn:
            conn.execute("INSERT INTO api_usage (meter, period, count) VALUES ('m', 'p', 1)")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert SqliteQuota(db).used("m", "p") == 0
    db.close()
