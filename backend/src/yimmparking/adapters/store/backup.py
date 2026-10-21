"""Daily copies of the database, the newest few kept.

The copy is made with SQLite's online backup, so it is consistent even while the API and the
worker keep writing, and it is checked before it replaces anything. Rotation only ever touches
files named like a daily copy: a backup made by hand in the same folder is never removed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from yimmparking.adapters.store.sqlite import SqliteStore

PREFIX = "yimmparking-daily-"
_DAILY = re.compile(rf"{re.escape(PREFIX)}\d{{8}}\.db")


@dataclass(slots=True)
class BackupResult:
    path: Path
    size: int
    removed: list[Path] = field(default_factory=list)


def daily_path(directory: Path, day: date) -> Path:
    return directory / f"{PREFIX}{day:%Y%m%d}.db"


def backup_daily(store: SqliteStore, directory: Path, day: date, keep: int) -> BackupResult:
    """Write the day's copy (replacing an earlier one that day); keep only the newest `keep`."""
    directory.mkdir(parents=True, exist_ok=True)
    target = daily_path(directory, day)
    store.backup_to(target)
    return BackupResult(path=target, size=target.stat().st_size, removed=rotate(directory, keep))


def rotate(directory: Path, keep: int) -> list[Path]:
    daily = sorted(
        (p for p in directory.iterdir() if p.is_file() and _DAILY.fullmatch(p.name)),
        key=lambda p: p.name,
        reverse=True,
    )
    removed = daily[max(keep, 1) :]
    for path in removed:
        path.unlink()
    return removed
