"""The SQLite file itself: one shared connection, its lock, the schema, backups.

Each store (lots, history, quotas, caches) works through a `Database` and owns only its tables.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from yimmparking.adapters.store.schema import MIGRATIONS

log = logging.getLogger(__name__)

BUSY_TIMEOUT_S = 15.0
IN_CHUNK = 500  # ids per `IN (...)`, well under SQLite's variable limit


def to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # One shared connection guarded by a lock: the dataset is small and writes are rare.
        # The API and the worker are separate processes on the same file, so a write may find the
        # other one mid-write: wait for it (`timeout`) instead of failing with "database is locked".
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=BUSY_TIMEOUT_S)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._use_wal()
        self._migrate()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """The connection, held for this block (re-entrant)."""
        with self._lock:
            yield self._conn

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """The connection inside a transaction: committed at the end, rolled back on error."""
        with self._lock, self._conn:
            yield self._conn

    def _use_wal(self) -> None:
        """Write-ahead logging, so the API keeps reading while the worker writes.

        The mode is stored in the file, so it only has to succeed once. If another process holds
        the file right now, the database still works in its current mode and the next start
        tries again.
        """
        if self.path == ":memory:":
            return
        with self.read() as conn:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as exc:
                log.warning("%s: could not switch to WAL, keeping its mode: %s", self.path, exc)

    def _migrate(self) -> None:
        with self.read() as conn:
            current = conn.execute("PRAGMA user_version").fetchone()[0]
            for version, script in enumerate(MIGRATIONS, start=1):
                if version <= current:
                    continue
                conn.executescript("BEGIN;" + script + f"PRAGMA user_version = {version};COMMIT;")

    def backup_to(self, target: Path) -> None:
        """A consistent copy of the whole database at `target`, checked before it is put there.

        Written beside the target first and renamed into place, so a failed or interrupted copy
        never replaces a good one.
        """
        partial = target.with_name(target.name + ".partial")
        partial.unlink(missing_ok=True)
        copy = sqlite3.connect(partial)
        try:
            with self.read() as conn:
                conn.backup(copy)
            check = copy.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            copy.close()
        if check != "ok":
            partial.unlink(missing_ok=True)
            raise sqlite3.DatabaseError(f"backup failed its check: {check}")
        partial.replace(target)

    def vacuum(self) -> None:
        """Rewrite the file without its free pages, so space freed by a large delete is returned."""
        with self.read() as conn:
            conn.execute("VACUUM")

    def close(self) -> None:
        with self.read() as conn:
            conn.close()
