from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from yimmparking.interface.cli import _backup_daily, _purge_expired
from yimmparking.interface.container import Container

NOW = datetime(2026, 10, 20, tzinfo=UTC)


class FlakyStore:
    """The geocode purge hits a busy database; the other purges work."""

    def __init__(self) -> None:
        self.purged: list[str] = []

    def purge_expired_geocodes(self, now: datetime) -> int:
        raise sqlite3.OperationalError("database is locked")

    def purge_expired_places(self, now: datetime) -> int:
        self.purged.append("food")
        return 0

    def purge_expired_routes(self, now: datetime) -> int:
        self.purged.append("route")
        return 0

    def purge_history(self, now: datetime, keep: timedelta) -> int:
        self.purged.append(f"history {keep.days}d")
        return 0


def _container(store: Any) -> Container:
    return cast(
        Container,
        SimpleNamespace(
            store=store,
            clock=SimpleNamespace(now=lambda: NOW),
            settings=SimpleNamespace(history_days=365),
        ),
    )


def test_a_failed_purge_is_logged_and_does_not_stop_the_worker(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = FlakyStore()
    with caplog.at_level(logging.ERROR):
        _purge_expired(_container(store))  # must not raise

    assert store.purged == ["food", "route", "history 365d"]  # the others still ran
    assert "purging the expired geocode rows failed" in caplog.text


def test_a_failed_backup_is_logged_and_does_not_stop_the_worker(
    tmp_path: Any, caplog: pytest.LogCaptureFixture
) -> None:
    class FullDisk:
        def backup_to(self, target: Any) -> None:
            raise OSError("No space left on device")

    container = cast(
        Container,
        SimpleNamespace(
            store=FullDisk(),
            clock=SimpleNamespace(now=lambda: NOW),
            settings=SimpleNamespace(backup_dir=tmp_path / "backup", backup_keep=7),
        ),
    )
    with caplog.at_level(logging.ERROR):
        _backup_daily(container)  # must not raise
    assert "daily backup to" in caplog.text and "No space left" in caplog.text
