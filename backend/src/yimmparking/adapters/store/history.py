"""Availability history, kept as changes only.

A lot's count is stored when it differs from the lot's previous reading, so the value at any moment
is the last change at or before it. Whether the feed was actually read at that moment is a separate
fact, kept per city in `availability_poll`: a feed that stops (or keeps repeating one timestamp)
leaves a gap there, so a frozen number is never mistaken for a steady one.

Times are whole UTC seconds and lots are small integer keys (`lot_key`), which keeps a year of
history in a few hundred megabytes.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from yimmparking.domain.model import AvailabilityBatch, City

if TYPE_CHECKING:  # database imports the schema, which imports this module
    from yimmparking.adapters.store.database import Database

log = logging.getLogger(__name__)

OLD_TABLE = "availability_observation"  # every reading every poll; replaced by the tables above

SCHEMA = """
    CREATE TABLE lot_key (
        key INTEGER PRIMARY KEY,
        lot_id TEXT NOT NULL UNIQUE
    );
    CREATE TABLE availability_change (
        lot_key INTEGER NOT NULL,
        observed_s INTEGER NOT NULL,
        count INTEGER,
        PRIMARY KEY (lot_key, observed_s)
    ) WITHOUT ROWID;
    CREATE TABLE availability_poll (
        city TEXT NOT NULL,
        observed_s INTEGER NOT NULL,
        PRIMARY KEY (city, observed_s)
    ) WITHOUT ROWID;
"""


def to_seconds(moment: datetime) -> int:
    return int(moment.timestamp())


def _lot_keys(conn: sqlite3.Connection, lot_ids: list[str]) -> dict[str, int]:
    conn.executemany("INSERT OR IGNORE INTO lot_key (lot_id) VALUES (?)", [(i,) for i in lot_ids])
    keys: dict[str, int] = {}
    for start in range(0, len(lot_ids), 500):
        chunk = lot_ids[start : start + 500]
        marks = ",".join("?" * len(chunk))
        for key, lot_id in conn.execute(
            f"SELECT key, lot_id FROM lot_key WHERE lot_id IN ({marks})", chunk
        ):
            keys[lot_id] = key
    return keys


def record(
    conn: sqlite3.Connection,
    batch: AvailabilityBatch,
    previous: dict[str, tuple[int | None, datetime]],
) -> int:
    """Store the poll and every reading that changed; returns how many changes were stored.

    `previous` is each lot's latest reading before this batch. A reading no newer than it (the same
    feed timestamp again, or an older feed) adds nothing.
    """
    observed_s = to_seconds(batch.observed_at)
    conn.execute(
        "INSERT OR IGNORE INTO availability_poll (city, observed_s) VALUES (?, ?)",
        (batch.city.value, observed_s),
    )
    changed = []
    for reading in batch.readings:
        before = previous.get(reading.lot_id)
        if before is None:
            changed.append(reading)
            continue
        count, observed_at = before
        if batch.observed_at > observed_at and reading.count != count:
            changed.append(reading)
    if not changed:
        return 0
    keys = _lot_keys(conn, [r.lot_id for r in changed])
    conn.executemany(
        "INSERT OR IGNORE INTO availability_change (lot_key, observed_s, count) VALUES (?, ?, ?)",
        [(keys[r.lot_id], observed_s, r.count) for r in changed],
    )
    return len(changed)


def purge(conn: sqlite3.Connection, cutoff: datetime) -> int:
    """Drop history older than `cutoff`, keeping each lot's last change before it.

    That one row is the lot's value at the start of the window, without which the first hours of
    the window would read as unknown. Deletes run per lot over the primary key, so this never scans
    the whole table.
    """
    cutoff_s = to_seconds(cutoff)
    removed = 0
    for (key,) in conn.execute("SELECT key FROM lot_key").fetchall():
        cur = conn.execute(
            """
            DELETE FROM availability_change
            WHERE lot_key = ?1 AND observed_s < (
                SELECT MAX(observed_s) FROM availability_change
                WHERE lot_key = ?1 AND observed_s < ?2
            )
            """,
            (key, cutoff_s),
        )
        removed += cur.rowcount
    for (city,) in conn.execute("SELECT DISTINCT city FROM availability_poll").fetchall():
        cur = conn.execute(
            "DELETE FROM availability_poll WHERE city = ? AND observed_s < ?", (city, cutoff_s)
        )
        removed += cur.rowcount
    return removed


# ---- one-off conversion of the old per-poll table --------------------------------------------


@dataclass(slots=True)
class Conversion:
    old_table: bool  # whether the old table is still there
    rows: int = 0  # readings in the old table
    lots: int = 0
    changes: int = 0  # rows the change-only table gets from them
    polls: int = 0
    first: str | None = None
    last: str | None = None
    verified: bool = False  # every old reading equals the value rebuilt from the changes
    written: bool = False


class ConversionMismatch(Exception):
    """The rebuilt history disagrees with the old table; nothing was changed."""


def _old_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (OLD_TABLE,)
    ).fetchone()
    return row is not None


def _old_rows(conn: sqlite3.Connection) -> Iterator[tuple[str, int, int | None]]:
    cur = conn.execute(
        f"SELECT lot_id, observed_at, count FROM {OLD_TABLE} ORDER BY lot_id, observed_at"
    )
    for lot_id, observed_at, count in cur:
        yield lot_id, to_seconds(datetime.fromisoformat(observed_at)), count


def _changes_from_old(
    conn: sqlite3.Connection,
) -> tuple[list[tuple[str, int, int | None]], int]:
    """The old readings reduced to changes, and how many readings there were."""
    changes: list[tuple[str, int, int | None]] = []
    rows = 0
    last_lot: str | None = None
    last_count: int | None = None
    for lot_id, observed_s, count in _old_rows(conn):
        rows += 1
        if lot_id != last_lot or count != last_count:
            changes.append((lot_id, observed_s, count))
        last_lot, last_count = lot_id, count
    return changes, rows


def _verify(conn: sqlite3.Connection) -> None:
    """Rebuild every old reading from the stored changes; raise on the first disagreement."""
    lot_id: str | None = None
    stored: list[tuple[int, int | None]] = []
    index = 0
    for old_lot, observed_s, count in _old_rows(conn):
        if old_lot != lot_id:
            lot_id, index = old_lot, 0
            stored = conn.execute(
                """
                SELECT c.observed_s, c.count FROM availability_change c
                JOIN lot_key k ON k.key = c.lot_key
                WHERE k.lot_id = ? ORDER BY c.observed_s
                """,
                (lot_id,),
            ).fetchall()
        while index + 1 < len(stored) and stored[index + 1][0] <= observed_s:
            index += 1
        if not stored or stored[index][0] > observed_s or stored[index][1] != count:
            raise ConversionMismatch(
                f"{lot_id} at {observed_s}: old reading {count}, rebuilt "
                f"{stored[index][1] if stored and stored[index][0] <= observed_s else 'nothing'}"
            )


def convert(conn: sqlite3.Connection, *, write: bool) -> Conversion:
    """Move the old per-poll readings into the change-only tables.

    Without `write` this only reads and reports (the connection may be read-only). With it, the
    changes and polls are inserted, every old reading is checked against the rebuilt history, and
    only then is the old table dropped, all in one transaction: on any mismatch nothing changes.
    Running it again once the old table is gone does nothing.
    """
    if not _old_table_exists(conn):
        return Conversion(old_table=False)

    changes, rows = _changes_from_old(conn)
    polls = conn.execute(f"SELECT DISTINCT city, observed_at FROM {OLD_TABLE}").fetchall()
    first, last = conn.execute(
        f"SELECT MIN(observed_at), MAX(observed_at) FROM {OLD_TABLE}"
    ).fetchone()
    report = Conversion(
        old_table=True,
        rows=rows,
        lots=len({lot_id for lot_id, _, _ in changes}),
        changes=len(changes),
        polls=len({(city, to_seconds(datetime.fromisoformat(at))) for city, at in polls}),
        first=first,
        last=last,
    )
    if not write:
        return report

    try:
        conn.execute("BEGIN IMMEDIATE")
        keys = _lot_keys(conn, sorted({lot_id for lot_id, _, _ in changes}))
        conn.executemany(
            "INSERT OR IGNORE INTO availability_change (lot_key, observed_s, count) VALUES (?,?,?)",
            [(keys[lot_id], observed_s, count) for lot_id, observed_s, count in changes],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO availability_poll (city, observed_s) VALUES (?, ?)",
            [(city, to_seconds(datetime.fromisoformat(at))) for city, at in polls],
        )
        _verify(conn)
        conn.execute(f"DROP TABLE {OLD_TABLE}")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    report.verified = report.written = True
    return report


# ---- reading it back ----------------------------------------------------------------------


def changes_since(
    conn: sqlite3.Connection, lot_id: str, since_s: int
) -> list[tuple[int, int | None]]:
    """A lot's changes from `since_s` on, led by the last change before it (the value in force
    at `since_s`)."""
    rows = conn.execute(
        """
        SELECT c.observed_s, c.count
        FROM availability_change c JOIN lot_key k ON k.key = c.lot_key
        WHERE k.lot_id = ?1 AND c.observed_s >= COALESCE(
            (SELECT MAX(c2.observed_s) FROM availability_change c2
             WHERE c2.lot_key = k.key AND c2.observed_s < ?2),
            ?2)
        ORDER BY c.observed_s
        """,
        (lot_id, since_s),
    ).fetchall()
    return [(int(at), count) for at, count in rows]


def polls_since(conn: sqlite3.Connection, city: str, since_s: int) -> list[int]:
    rows = conn.execute(
        "SELECT observed_s FROM availability_poll WHERE city = ? AND observed_s >= ? "
        "ORDER BY observed_s",
        (city, since_s),
    ).fetchall()
    return [int(at) for (at,) in rows]


class SqliteHistory:
    """The change-only availability history (AvailabilityHistory), its retention, and the one-off
    conversion of the old per-poll table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def availability_changes(self, lot_id: str, since: datetime) -> list[tuple[int, int | None]]:
        with self._db.read() as conn:
            return changes_since(conn, lot_id, to_seconds(since))

    def feed_polls(self, city: City, since: datetime) -> list[int]:
        with self._db.read() as conn:
            return polls_since(conn, city.value, to_seconds(since))

    def purge_history(self, now: datetime, keep: timedelta) -> int:
        with self._db.write() as conn:
            return purge(conn, now - keep)

    def convert_history(self) -> Conversion:
        """Convert the old per-poll table into the change-only history (see `history.convert`)."""
        with self._db.read() as conn:
            return convert(conn, write=True)
