"""Migrations run by position against databases that already exist, so their order is history."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from yimmparking.adapters.store import schema
from yimmparking.adapters.store.sqlite import SqliteStore

# The table each migration created, in the order it shipped. Appending is fine; changing or
# reordering an existing entry breaks every database already at that version.
HISTORY = ["parking_lot", "api_usage", "place_cache", "walk_cache", "lot_key"]


def tables(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    finally:
        conn.close()


def test_migration_history_is_pinned() -> None:
    scripts = schema.MIGRATIONS
    assert len(scripts) >= len(HISTORY)
    for index, table in enumerate(HISTORY):
        assert f"CREATE TABLE {table} " in scripts[index], (
            f"migration {index + 1} no longer creates {table}: migrations must be append-only"
        )


@pytest.mark.parametrize("version", range(len(HISTORY) + 1))
def test_a_database_left_at_any_earlier_version_upgrades(tmp_path: Path, version: int) -> None:
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    for script in schema.MIGRATIONS[:version]:
        conn.executescript(script)
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()

    SqliteStore(db).close()  # must not raise "table ... already exists"

    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(schema.MIGRATIONS)
    conn.close()
    assert set(HISTORY) <= tables(db)


def test_existing_rows_survive_an_upgrade(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    for script in schema.MIGRATIONS[:3]:  # the shape a deployed database actually had
        conn.executescript(script)
    conn.execute("PRAGMA user_version = 3")
    conn.execute(
        "INSERT INTO api_usage (meter, period, count) VALUES ('places_nearby', '2026-10', 7)"
    )
    conn.execute(
        "INSERT INTO place_cache (key, payload, expires_at) VALUES ('k', '[]', '2099-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    store = SqliteStore(db)
    assert store.used("places_nearby", "2026-10") == 7
    store.close()

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM place_cache").fetchone()[0] == 1
    conn.close()


def test_v6_records_the_source_of_each_latest_reading() -> None:
    assert "ADD COLUMN source" in schema.MIGRATIONS[5]
