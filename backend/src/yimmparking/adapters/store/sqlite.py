"""All the SQLite stores on one database file.

Each role lives in its own module and class, working through a shared `Database`; this class only
puts them together, so the composition root (and the tests) can open one file and hand the same
object to every port. Nothing here is specific to any one table.
"""

from __future__ import annotations

from pathlib import Path

from yimmparking.adapters.store.caches import (
    SqliteGeocodeCache,
    SqlitePlaceCache,
    SqliteRouteCache,
)
from yimmparking.adapters.store.database import Database
from yimmparking.adapters.store.history import SqliteHistory
from yimmparking.adapters.store.lots import SqliteLots
from yimmparking.adapters.store.quota import SqliteQuota


class SqliteStore(
    SqliteLots,
    SqliteHistory,
    SqliteQuota,
    SqliteRouteCache,
    SqlitePlaceCache,
    SqliteGeocodeCache,
):
    def __init__(self, path: str | Path) -> None:
        self.db = Database(path)
        self._db = self.db  # every role reads and writes through the same database

    def backup_to(self, target: Path) -> None:
        self.db.backup_to(target)

    def vacuum(self) -> None:
        self.db.vacuum()

    def close(self) -> None:
        self.db.close()
