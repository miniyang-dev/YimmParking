"""Daily database copies: consistent, checked, and rotated without touching other files."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from yimmparking.adapters.store import backup
from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.domain.model import AvailabilityBatch, AvailabilityReading, City

DAY = date(2026, 10, 22)


def seeded(path: Path) -> SqliteStore:
    store = SqliteStore(path)
    store.record_availability(
        AvailabilityBatch(
            City.TAIPEI,
            datetime(2026, 10, 22, 1, 0, tzinfo=UTC),
            (AvailabilityReading("taipei:a", 7),),
        )
    )
    return store


def test_the_copy_holds_the_data_and_passes_its_check(tmp_path: Path) -> None:
    store = seeded(tmp_path / "data" / "y.db")
    result = backup.backup_daily(store, tmp_path / "backup", DAY, keep=7)
    store.close()

    assert result.path == tmp_path / "backup" / "yimmparking-daily-20261022.db"
    copy = sqlite3.connect(result.path)
    assert copy.execute("SELECT count FROM availability_latest").fetchone()[0] == 7
    assert copy.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    copy.close()
    assert not list((tmp_path / "backup").glob("*.partial"))


def test_a_second_copy_the_same_day_replaces_the_first(tmp_path: Path) -> None:
    store = seeded(tmp_path / "y.db")
    backup.backup_daily(store, tmp_path / "backup", DAY, keep=7)
    backup.backup_daily(store, tmp_path / "backup", DAY, keep=7)
    store.close()
    assert [p.name for p in (tmp_path / "backup").iterdir()] == ["yimmparking-daily-20261022.db"]


def test_only_the_newest_daily_copies_are_kept_and_other_files_are_left_alone(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "backup"
    folder.mkdir()
    for day in range(10, 22):  # twelve older daily copies
        (folder / f"yimmparking-daily-202610{day:02d}.db").write_bytes(b"old")
    by_hand = folder / "yimmparking-20261020-193444-before-history.db"
    by_hand.write_bytes(b"keep me")
    unrelated = folder / "notes.txt"
    unrelated.write_text("keep me too", encoding="utf-8")

    store = seeded(tmp_path / "y.db")
    result = backup.backup_daily(store, folder, DAY, keep=7)
    store.close()

    daily = sorted(p.name for p in folder.glob("yimmparking-daily-*.db"))
    assert daily == [f"yimmparking-daily-202610{d}.db" for d in range(16, 23)]
    assert len(result.removed) == 6
    assert by_hand.exists() and unrelated.exists()
