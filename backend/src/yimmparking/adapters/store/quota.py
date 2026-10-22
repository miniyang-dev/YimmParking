"""Per-period call counters for paid APIs (QuotaStore)."""

from __future__ import annotations

from yimmparking.adapters.store.database import Database


class SqliteQuota:
    """Durable counters, so a self-imposed limit survives restarts."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def try_consume(self, meter: str, period: str, limit: int, amount: int = 1) -> bool:
        if amount <= 0:
            return True
        if limit <= 0 or amount > limit:
            return False
        with self._db.write() as conn:
            # One statement, so check-and-increment cannot interleave with another caller.
            cur = conn.execute(
                """
                INSERT INTO api_usage (meter, period, count) VALUES (?, ?, ?)
                ON CONFLICT(meter, period) DO UPDATE SET count = count + ?
                WHERE count + ? <= ?
                """,
                (meter, period, amount, amount, amount, limit),
            )
        return cur.rowcount == 1

    def used(self, meter: str, period: str) -> int:
        with self._db.read() as conn:
            row = conn.execute(
                "SELECT count FROM api_usage WHERE meter = ? AND period = ?", (meter, period)
            ).fetchone()
        return int(row["count"]) if row else 0
