"""Command line: ingestion, the scheduler loop and the HTTP server.

Anything that writes defaults to dry-run and says which database it targets first.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from typing import Any

from yimmparking.interface.container import Container, build_container
from yimmparking.interface.settings import Settings

log = logging.getLogger("yimmparking")


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
                _purge_caches(container)
                next_lots = now + settings.lots_interval_s
            if now >= next_availability:
                _run_safely(
                    "availability", lambda: container.refresh_availability.run(dry_run=False)
                )
                next_availability = now + settings.availability_interval_s
            time.sleep(5)
    except KeyboardInterrupt:
        return 0
    finally:
        container.close()


def _purge_caches(container: Container) -> None:
    """Expired cache rows only cost disk space, so a failed purge (say, the database is busy) is
    logged and tried again next time instead of stopping the scheduler."""
    now = container.clock.now()
    store = container.store
    for name, purge in (
        ("geocode", store.purge_expired),
        ("food", store.purge_expired_places),
        ("route", store.purge_expired_routes),
    ):
        try:
            purge(now)
        except Exception:
            log.exception("purging the expired %s cache failed", name)


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
    sub.add_parser("worker", help="run the ingestion loop").set_defaults(func=cmd_worker)
    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
