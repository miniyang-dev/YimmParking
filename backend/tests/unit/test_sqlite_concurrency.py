"""The API and the worker are two processes on one SQLite file; neither may fail on the other."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from yimmparking.adapters.store.sqlite import SqliteStore


def test_a_file_database_uses_write_ahead_logging(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "y.db")
    store.close()
    conn = sqlite3.connect(tmp_path / "y.db")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()


def test_reads_go_on_while_another_process_writes(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "y.db")
    other = sqlite3.connect(tmp_path / "y.db", isolation_level=None)
    try:
        other.execute("BEGIN EXCLUSIVE")
        other.execute("INSERT INTO api_usage (meter, period, count) VALUES ('x', '2026-10', 1)")

        started = time.monotonic()
        assert store.used("x", "2026-10") == 0  # the uncommitted write is not visible yet
        assert time.monotonic() - started < 1.0  # and the read did not wait for it

        other.execute("COMMIT")
        assert store.used("x", "2026-10") == 1
    finally:
        other.close()
        store.close()


def test_a_write_waits_for_the_other_writer_instead_of_failing(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "y.db")
    other = sqlite3.connect(tmp_path / "y.db", isolation_level=None, check_same_thread=False)
    other.execute("BEGIN IMMEDIATE")
    other.execute("INSERT INTO api_usage (meter, period, count) VALUES ('x', '2026-10', 1)")
    committer = threading.Timer(0.5, lambda: other.execute("COMMIT"))
    committer.start()
    try:
        assert store.try_consume("x", "2026-10", limit=10) is True  # waited, did not raise
        assert store.used("x", "2026-10") == 2
    finally:
        committer.join()
        other.close()
        store.close()
