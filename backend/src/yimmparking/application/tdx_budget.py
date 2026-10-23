"""A ceiling on TDX use, in TDX's own currency: points per month.

TDX bills its basic services by calls and by data transferred, added together: 1 point per
1,500 calls plus 1 point per 150 MB. A free (基礎) member gets 3 points a month; at 105% the
account is cut off until the next month, for every service. So every call is counted (its size
after compression, which is what TDX counts) and calls stop at a self-imposed ceiling under the
allowance, as with the Google limits.
"""

from __future__ import annotations

from yimmparking.application.limits import period_of
from yimmparking.application.ports import Clock, QuotaStore, SourceError

CALLS_PER_POINT = 1500
KB_PER_POINT = 150 * 1024
CALLS_METER = "tdx_calls"
KB_METER = "tdx_kb"
_NO_LIMIT = 10**12  # the counters only add up; the ceiling is checked in points


class TdxBudgetSpent(SourceError):
    """This month's self-imposed TDX ceiling is reached; no call was made."""


class TdxBudget:
    def __init__(self, store: QuotaStore, clock: Clock, limit_millipoints: int) -> None:
        self._store = store
        self._clock = clock
        self.limit_millipoints = limit_millipoints

    @property
    def period(self) -> str:
        return period_of(self._clock)

    def used_millipoints(self) -> int:
        period = self.period
        calls = self._store.used(CALLS_METER, period)
        kb = self._store.used(KB_METER, period)
        return (calls * 1000) // CALLS_PER_POINT + (kb * 1000) // KB_PER_POINT

    def check(self) -> None:
        """Refuse a call once this month's ceiling is reached."""
        used = self.used_millipoints()
        if used >= self.limit_millipoints:
            raise TdxBudgetSpent(
                f"TDX budget for {self.period} reached: "
                f"{used / 1000:.2f} of {self.limit_millipoints / 1000:.2f} points"
            )

    def record(self, wire_bytes: int) -> None:
        """Count one call that got an answer, with the bytes it transferred (rounded up)."""
        period = self.period
        self._store.try_consume(CALLS_METER, period, _NO_LIMIT, 1)
        kb = -(-wire_bytes // 1024)
        if kb:
            self._store.try_consume(KB_METER, period, _NO_LIMIT, kb)
