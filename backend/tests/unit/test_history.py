"""Availability history kept as changes, its retention, and the one-off conversion of the old table."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yimmparking.adapters.store import history, schema
from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.domain.model import AvailabilityBatch, AvailabilityReading, City
from yimmparking.interface import cli

T0 = datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
MIN = timedelta(minutes=1)


def batch(at: datetime, *readings: tuple[str, int | None], city: City = City.TAIPEI) -> AvailabilityBatch:
    return AvailabilityBatch(
        city, at, tuple(AvailabilityReading(lot_id, count) for lot_id, count in readings)
    )


def changes(store: SqliteStore, lot_id: str) -> list[tuple[int, int | None]]:
    conn = store.db._conn
    return [
        (s - history.to_seconds(T0), c)
        for s, c in conn.execute(
            """
            SELECT c.observed_s, c.count FROM availability_change c
            JOIN lot_key k ON k.key = c.lot_key WHERE k.lot_id = ? ORDER BY c.observed_s
            """,
            (lot_id,),
        )
    ]


def polls(store: SqliteStore, city: str = "taipei") -> list[int]:
    rows = store.db._conn.execute(
        "SELECT observed_s FROM availability_poll WHERE city = ? ORDER BY observed_s", (city,)
    )
    return [s - history.to_seconds(T0) for (s,) in rows]


@pytest.fixture
def store() -> SqliteStore:
    s = SqliteStore(":memory:")
    yield s  # type: ignore[misc]
    s.close()


class TestRecord:
    def test_only_changes_are_stored(self, store: SqliteStore) -> None:
        store.record_availability(batch(T0, ("taipei:a", 10)))
        store.record_availability(batch(T0 + 2 * MIN, ("taipei:a", 10)))
        store.record_availability(batch(T0 + 4 * MIN, ("taipei:a", 7)))
        store.record_availability(batch(T0 + 6 * MIN, ("taipei:a", 7)))
        assert changes(store, "taipei:a") == [(0, 10), (240, 7)]
        # Every poll is still known, so "unchanged" can be told apart from "not read".
        assert polls(store) == [0, 120, 240, 360]

    def test_going_to_and_from_no_data_is_a_change(self, store: SqliteStore) -> None:
        for minute, count in ((0, 5), (2, None), (4, None), (6, 5)):
            store.record_availability(batch(T0 + minute * MIN, ("taipei:a", count)))
        assert changes(store, "taipei:a") == [(0, 5), (120, None), (360, 5)]

    def test_a_feed_stuck_on_one_timestamp_adds_nothing(self, store: SqliteStore) -> None:
        store.record_availability(batch(T0, ("taipei:a", 10)))
        store.record_availability(batch(T0, ("taipei:a", 10)))
        store.record_availability(batch(T0, ("taipei:a", 10)))
        assert changes(store, "taipei:a") == [(0, 10)]
        assert polls(store) == [0]  # the gap after it shows the feed stopped

    def test_an_older_feed_does_not_rewrite_history(self, store: SqliteStore) -> None:
        store.record_availability(batch(T0, ("taipei:a", 10)))
        store.record_availability(batch(T0 - 10 * MIN, ("taipei:a", 3)))
        assert changes(store, "taipei:a") == [(0, 10)]
        assert store.latest_availability(["taipei:a"])["taipei:a"] == (10, T0)

    def test_each_lot_and_city_is_tracked_on_its_own(self, store: SqliteStore) -> None:
        store.record_availability(batch(T0, ("taipei:a", 1), ("taipei:b", 2)))
        store.record_availability(
            batch(T0 + 30 * MIN / 60, ("new_taipei:c", 3), city=City.NEW_TAIPEI)
        )
        store.record_availability(batch(T0 + 2 * MIN, ("taipei:a", 1), ("taipei:b", 9)))
        assert changes(store, "taipei:a") == [(0, 1)]
        assert changes(store, "taipei:b") == [(0, 2), (120, 9)]
        assert changes(store, "new_taipei:c") == [(30, 3)]
        assert polls(store, "new_taipei") == [30]


class TestPurge:
    def test_keeps_the_window_and_the_value_at_its_start(self, store: SqliteStore) -> None:
        for minute, count in ((0, 1), (10, 2), (20, 3), (30, 4)):
            store.record_availability(batch(T0 + minute * MIN, ("taipei:a", count)))

        store.purge_history(T0 + 40 * MIN, keep=25 * MIN)  # window starts at minute 15

        # Minute 10 stays: it is the value at minute 15. Minute 0 goes.
        assert changes(store, "taipei:a") == [(600, 2), (1200, 3), (1800, 4)]
        assert polls(store) == [1200, 1800]

    def test_nothing_older_than_the_window_means_nothing_to_drop(self, store: SqliteStore) -> None:
        store.record_availability(batch(T0, ("taipei:a", 1)))
        assert store.purge_history(T0 + MIN, keep=timedelta(days=365)) == 0
        assert changes(store, "taipei:a") == [(0, 1)]


# ---- conversion of the old per-poll table ----------------------------------------------------

OLD_ROWS = [
    # lot, city, count, observed_at (as the old code wrote it: with and without microseconds)
    ("taipei:a", "taipei", 10, "2026-10-20T08:00:00+00:00"),
    ("taipei:a", "taipei", 10, "2026-10-20T08:02:00+00:00"),
    ("taipei:a", "taipei", 7, "2026-10-20T08:04:00+00:00"),
    ("taipei:a", "taipei", None, "2026-10-20T08:06:00+00:00"),
    ("taipei:a", "taipei", None, "2026-10-20T08:08:00+00:00"),
    ("taipei:a", "taipei", 7, "2026-10-20T08:10:00+00:00"),
    ("new_taipei:c", "new_taipei", 3, "2026-10-20T08:00:31.123456+00:00"),
    ("new_taipei:c", "new_taipei", 3, "2026-10-20T08:02:31.654321+00:00"),
]


def old_database(path: Path) -> Path:
    """A database as the previous release left it: version 4, WAL, readings every poll."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    for script in schema.MIGRATIONS[:4]:
        conn.executescript(script)
    conn.execute("PRAGMA user_version = 4")
    conn.executemany(
        "INSERT INTO availability_observation (lot_id, city, count, observed_at) VALUES (?,?,?,?)",
        OLD_ROWS,
    )
    conn.commit()
    conn.close()
    return path


def value_at(store: SqliteStore, lot_id: str, iso: str) -> int | None:
    at = history.to_seconds(datetime.fromisoformat(iso))
    row = store.db._conn.execute(
        """
        SELECT c.count FROM availability_change c JOIN lot_key k ON k.key = c.lot_key
        WHERE k.lot_id = ? AND c.observed_s <= ? ORDER BY c.observed_s DESC LIMIT 1
        """,
        (lot_id, at),
    ).fetchone()
    assert row is not None
    return row[0]


def has_old_table(path: Path) -> bool:
    conn = sqlite3.connect(path)
    try:
        return history._old_table_exists(conn)
    finally:
        conn.close()


class TestConvert:
    def test_dry_run_reports_and_writes_nothing(self, tmp_path: Path) -> None:
        path = old_database(tmp_path / "y.db")
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        report = history.convert(conn, write=False)
        conn.close()

        assert (report.rows, report.lots, report.changes, report.polls) == (8, 2, 5, 8)
        assert report.written is False
        conn = sqlite3.connect(path)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4  # not even migrated
        conn.close()

    def test_every_old_reading_is_rebuilt_then_the_old_table_goes(self, tmp_path: Path) -> None:
        store = SqliteStore(old_database(tmp_path / "y.db"))
        report = store.convert_history()

        assert report.verified and report.written
        assert (report.changes, report.polls) == (5, 8)
        for lot_id, _, count, observed_at in OLD_ROWS:
            assert value_at(store, lot_id, observed_at) == count
        store.close()
        assert not has_old_table(tmp_path / "y.db")

    def test_running_it_again_does_nothing(self, tmp_path: Path) -> None:
        store = SqliteStore(old_database(tmp_path / "y.db"))
        store.convert_history()
        again = store.convert_history()
        assert (again.old_table, again.written) == (False, False)
        assert changes(store, "taipei:a") != []
        store.close()

    def test_a_disagreement_changes_nothing(self, tmp_path: Path) -> None:
        store = SqliteStore(old_database(tmp_path / "y.db"))
        # A row already in the new table that contradicts the old reading of 10 at 08:02.
        store.db._conn.execute("INSERT INTO lot_key (key, lot_id) VALUES (1, 'taipei:a')")
        store.db._conn.execute(
            "INSERT INTO availability_change VALUES (1, ?, 99)",
            (history.to_seconds(datetime.fromisoformat("2026-10-20T08:02:00+00:00")),),
        )
        store.db._conn.commit()

        with pytest.raises(history.ConversionMismatch):
            store.convert_history()

        assert store.db._conn.execute("SELECT COUNT(*) FROM availability_change").fetchone()[0] == 1
        store.close()
        assert has_old_table(tmp_path / "y.db")

    def test_live_writes_after_the_old_data_are_kept(self, tmp_path: Path) -> None:
        store = SqliteStore(old_database(tmp_path / "y.db"))
        store.db._conn.execute(
            "INSERT INTO availability_latest VALUES ('taipei:a', 'taipei', 7, ?)",
            ("2026-10-20T08:10:00+00:00",),
        )
        store.db._conn.commit()
        store.record_availability(batch(T0 + 12 * MIN, ("taipei:a", 4)))

        store.convert_history()

        assert changes(store, "taipei:a")[-2:] == [(600, 7), (720, 4)]
        store.close()


class TestCommand:
    def test_dry_run_by_default_and_write_with_yes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = old_database(tmp_path / "y.db")
        monkeypatch.setenv("YIMM_DB_PATH", str(path))

        assert cli.main(["convert-history"]) == 0
        err = capsys.readouterr().err
        assert f"target database: {path}" in err and "DRY-RUN" in err
        assert has_old_table(path)

        assert cli.main(["convert-history", "--yes"]) == 0
        assert not has_old_table(path)
        conn = sqlite3.connect(path)
        assert conn.execute("SELECT COUNT(*) FROM availability_change").fetchone()[0] == 5
        conn.close()
