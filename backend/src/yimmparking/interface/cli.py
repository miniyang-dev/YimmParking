"""Command line: ingestion, the scheduler loop and the HTTP server.

Anything that writes defaults to dry-run and says which database it targets first.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from yimmparking.adapters.store import backup, history
from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.interface.container import Container, build_container
from yimmparking.interface.settings import Settings

log = logging.getLogger("yimmparking")
TAIPEI = timezone(timedelta(hours=8))  # a daily copy is named by the local date


def _print(report: Any) -> None:
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, default=str))


def _announce(container: Container, *, dry_run: bool) -> None:
    mode = "DRY-RUN (nothing will be written)" if dry_run else "WRITE"
    print(f"target database: {container.settings.db_path}\nmode: {mode}", file=sys.stderr)


def cmd_refresh_lots(args: argparse.Namespace) -> int:
    container = build_container(Settings.from_env())
    try:
        _announce(container, dry_run=not args.yes)
        report = container.refresh_lots.run(dry_run=not args.yes)
        _print(report)
        return 1 if any(c.error for c in report.cities) else 0
    finally:
        container.close()


def cmd_refresh_availability(args: argparse.Namespace) -> int:
    container = build_container(Settings.from_env())
    try:
        _announce(container, dry_run=not args.yes)
        report = container.refresh_availability.run(dry_run=not args.yes)
        _print(report)
        return 1 if any(c.error for c in report.cities) else 0
    finally:
        container.close()


def cmd_purge_geocache(_: argparse.Namespace) -> int:
    container = build_container(Settings.from_env())
    try:
        removed = container.store.purge_expired(container.clock.now())
        print(f"removed {removed} expired geocode cache entries")
        return 0
    finally:
        container.close()


def cmd_worker(_: argparse.Namespace) -> int:
    """Long-running ingestion loop: availability often, static lots rarely."""
    settings = Settings.from_env()
    container = build_container(settings)
    print(f"worker started, writing to {settings.db_path}", file=sys.stderr)
    next_lots = 0.0
    next_availability = 0.0
    try:
        while True:
            now = time.monotonic()
            if now >= next_lots:
                _run_safely("lots", lambda: container.refresh_lots.run(dry_run=False))
                _purge_expired(container)
                _backup_daily(container)
                next_lots = now + settings.lots_interval_s
            if now >= next_availability:
                _run_safely(
                    "availability", lambda: container.refresh_availability.run(dry_run=False)
                )
                _watch_feeds(container)
                next_availability = now + settings.availability_interval_s
            time.sleep(5)
    except KeyboardInterrupt:
        return 0
    finally:
        container.close()


def _backup_daily(container: Container) -> None:
    """Today's copy of the database; a failure is logged and tried again tomorrow."""
    settings = container.settings
    try:
        today = container.clock.now().astimezone(TAIPEI).date()
        result = backup.backup_daily(
            container.store, settings.backup_dir, today, settings.backup_keep
        )
    except Exception:
        log.exception("daily backup to %s failed", settings.backup_dir)
        return
    log.info(
        "backup written: %s (%.1f MB), removed %d old copies",
        result.path,
        result.size / 1e6,
        len(result.removed),
    )


def cmd_backup_db(_: argparse.Namespace) -> int:
    """Make today's copy now (the worker does this once a day)."""
    settings = Settings.from_env()
    container = build_container(settings)
    try:
        print(
            f"database: {settings.db_path}\n"
            f"backup folder: {settings.backup_dir} "
            f"(newest {settings.backup_keep} daily copies kept)",
            file=sys.stderr,
        )
        today = container.clock.now().astimezone(TAIPEI).date()
        result = backup.backup_daily(
            container.store, settings.backup_dir, today, settings.backup_keep
        )
        _print(result)
        return 0
    finally:
        container.close()


def _watch_feeds(container: Container) -> None:
    """Report a city whose real-time data has stopped moving; never stops the scheduler."""
    try:
        container.feed_watch.check()
    except Exception:
        log.exception("checking feed freshness failed")


def _purge_expired(container: Container) -> None:
    """Expired rows only cost disk space, so a failed purge (say, the database is busy) is logged
    and tried again next time instead of stopping the scheduler."""
    now = container.clock.now()
    store = container.store
    keep = timedelta(days=container.settings.history_days)
    purges: tuple[tuple[str, Callable[[datetime], int]], ...] = (
        ("geocode", store.purge_expired),
        ("food", store.purge_expired_places),
        ("route", store.purge_expired_routes),
        ("history", lambda at: store.purge_history(at, keep)),
    )
    for name, purge in purges:
        try:
            purge(now)
        except Exception:
            log.exception("purging the expired %s rows failed", name)


def cmd_convert_history(args: argparse.Namespace) -> int:
    """One-off: turn the old per-poll availability table into the change-only history.

    Dry-run by default: the database is opened read-only and only the plan is printed. With
    `--yes` the history is converted, every old reading is checked against it, the old table is
    dropped (all or nothing), and the file is compacted. Stop the API and the worker first.
    """
    settings = Settings.from_env()
    path = settings.db_path
    print(f"target database: {path}", file=sys.stderr)
    if not path.is_file():
        print("no such file", file=sys.stderr)
        return 1
    print(f"size before: {_size_mb(path)}", file=sys.stderr)

    if not args.yes:
        print("mode: DRY-RUN (opened read-only, nothing will be written)", file=sys.stderr)
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            _print(history.convert(conn, write=False))
        finally:
            conn.close()
        return 0

    print("mode: WRITE (convert, verify, drop the old table, compact)", file=sys.stderr)
    store = SqliteStore(path)
    try:
        report = store.convert_history()
        _print(report)
        if report.written:
            store.vacuum()
    except history.ConversionMismatch as exc:
        print(f"verification failed, nothing was changed: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
    print(f"size after: {_size_mb(path)}", file=sys.stderr)
    return 0


def _size_mb(path: Path) -> str:
    files = [path, path.with_name(path.name + "-wal")]
    return f"{sum(f.stat().st_size for f in files if f.exists()) / 1e6:.1f} MB (with -wal)"


def _run_safely(name: str, job: Any) -> None:
    try:
        report = job()
    except Exception:  # a scheduler must survive any single failed run
        log.exception("%s refresh crashed", name)
        return
    failed = [c for c in report.cities if c.error]
    for c in failed:
        log.warning("%s refresh for %s failed: %s", name, c.city.value, c.error)
    log.info(
        "%s refresh done (%d/%d cities ok)",
        name,
        len(report.cities) - len(failed),
        len(report.cities),
    )


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "yimmparking.interface.api:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(prog="yimmparking")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, fn, help_ in (
        ("refresh-lots", cmd_refresh_lots, "fetch static lot data + iParking directory"),
        ("refresh-availability", cmd_refresh_availability, "fetch real-time availability"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--yes", action="store_true", help="actually write (default is dry-run)")
        p.set_defaults(func=fn)

    sub.add_parser("purge-geocache", help="delete expired geocode cache rows").set_defaults(
        func=cmd_purge_geocache
    )
    convert = sub.add_parser(
        "convert-history", help="one-off: move the old availability table to change-only history"
    )
    convert.add_argument("--yes", action="store_true", help="actually write (default is dry-run)")
    convert.set_defaults(func=cmd_convert_history)
    sub.add_parser("backup-db", help="write today's database copy now").set_defaults(
        func=cmd_backup_db
    )
    sub.add_parser("worker", help="run the ingestion loop").set_defaults(func=cmd_worker)
    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
