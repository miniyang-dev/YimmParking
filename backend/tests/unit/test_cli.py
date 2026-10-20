from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from yimmparking.interface.cli import _purge_caches
from yimmparking.interface.container import Container

NOW = datetime(2026, 10, 20, tzinfo=UTC)


class FlakyStore:
    """The geocode purge hits a busy database; the other purges work."""

    def __init__(self) -> None:
        self.purged: list[str] = []

    def purge_expired(self, now: datetime) -> int:
        raise sqlite3.OperationalError("database is locked")

    def purge_expired_places(self, now: datetime) -> int:
        self.purged.append("food")
        return 0

    def purge_expired_routes(self, now: datetime) -> int:
        self.purged.append("route")
        return 0


def _container(store: Any) -> Container:
    return cast(Container, SimpleNamespace(store=store, clock=SimpleNamespace(now=lambda: NOW)))


def test_a_failed_purge_is_logged_and_does_not_stop_the_worker(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = FlakyStore()
    with caplog.at_level(logging.ERROR):
        _purge_caches(_container(store))  # must not raise

    assert store.purged == ["food", "route"]  # the others still ran
    assert "purging the expired geocode cache failed" in caplog.text
