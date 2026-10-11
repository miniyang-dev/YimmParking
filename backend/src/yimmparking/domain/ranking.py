"""Choosing and ordering nearby parking lots.

Real walking time costs a billed lookup per lot, so it is spent on a shortlist while every lot in
range stays in the list:

1. `shortlist` picks the lots worth a walking-time lookup, using only free straight-line distance:
   the nearest lots of each configured vendor in the user's order, then the nearest of the rest,
   up to `routed_limit` lots in total.
2. `arrange` builds the list. The first section holds the nearest lots of each configured vendor
   (`show` per vendor) in the user's order. Everything else follows in one section: lots with a
   walking time first, by that time, then the rest by straight-line distance. A time is never
   invented for a lot that was not routed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from yimmparking.domain.model import ParkingLot, RouteTime
from yimmparking.domain.vendor import Preference, Vendor, vendor_of


class SortMode(StrEnum):
    TIERED = "tiered"  # vendor sections first
    DISTANCE = "distance"  # no vendors: ordered by walking time alone


class Block(StrEnum):
    PRIORITY = "priority"  # one of the configured vendors' first lots
    OTHER = "other"
    DISTANCE = "distance"  # walking-only mode: a single list


@dataclass(frozen=True, slots=True)
class RankingPolicy:
    radius_steps_m: tuple[int, ...] = (1500, 3000, 5000)
    min_results: int = 5
    preference: Preference = field(default_factory=Preference)
    routed_limit: int = 8  # most lots that get a walking time
    preferred_limit: int = 12  # most lots in the vendor sections
    other_limit: int = 8  # most lots in the section after them
    mode: SortMode = SortMode.TIERED

    @property
    def max_radius_m(self) -> int:
        return self.radius_steps_m[-1]


@dataclass(frozen=True, slots=True)
class Candidate:
    lot: ParkingLot
    distance_m: float


@dataclass(frozen=True, slots=True)
class Pool:
    candidates: tuple[Candidate, ...]
    radius_m: int  # the radius step that was actually used


@dataclass(frozen=True, slots=True)
class RankedLot:
    lot: ParkingLot
    distance_m: float
    vendor: Vendor | None
    block: Block
    walking: RouteTime | None = None


def pool_within_radius(candidates: list[Candidate], policy: RankingPolicy) -> Pool:
    """Smallest radius step that yields `min_results` lots (or the largest step)."""
    chosen = policy.radius_steps_m[-1]
    within: list[Candidate] = []
    for radius in policy.radius_steps_m:
        within = [c for c in candidates if c.distance_m <= radius]
        chosen = radius
        if len(within) >= policy.min_results:
            break
    return Pool(candidates=tuple(within), radius_m=chosen)


def shortlist(pool: Pool, policy: RankingPolicy) -> list[Candidate]:
    """The lots worth a billed walking-time lookup, at most `policy.routed_limit` of them."""
    nearest = sorted(pool.candidates, key=lambda c: c.distance_m)
    if policy.mode is SortMode.DISTANCE:
        return nearest[: policy.routed_limit]

    chosen: list[Candidate] = []
    for pick in policy.preference.picks:
        if pick.show:
            chosen.extend([c for c in nearest if vendor_of(c.lot) is pick.vendor][: pick.show])
    chosen = chosen[: policy.routed_limit]
    taken = {c.lot.id for c in chosen}
    for c in nearest:
        if len(chosen) >= policy.routed_limit:
            break
        if c.lot.id not in taken:
            chosen.append(c)
            taken.add(c.lot.id)
    return chosen


def _time_key(walking: RouteTime | None, distance_m: float) -> tuple[float, float]:
    # Lots with a time sort before lots without one; each kind keeps its own natural order.
    return (walking.seconds if walking is not None else math.inf, distance_m)


def arrange(
    items: list[tuple[Candidate, RouteTime | None]], policy: RankingPolicy
) -> list[RankedLot]:
    """Order and section the lots, applying the display limits."""

    def ranked(c: Candidate, w: RouteTime | None, block: Block, vendor: Vendor | None) -> RankedLot:
        return RankedLot(lot=c.lot, distance_m=c.distance_m, vendor=vendor, block=block, walking=w)

    if policy.mode is SortMode.DISTANCE:
        single = [ranked(c, w, Block.DISTANCE, vendor_of(c.lot)) for c, w in items]
        single.sort(key=lambda r: _time_key(r.walking, r.distance_m))
        return single[: policy.preferred_limit + policy.other_limit]

    priority: list[RankedLot] = []
    other: list[RankedLot] = []
    for pick in policy.preference.picks:
        mine = sorted(
            (item for item in items if vendor_of(item[0].lot) is pick.vendor),
            key=lambda item: _time_key(item[1], item[0].distance_m),
        )
        for index, (c, w) in enumerate(mine):
            if index < pick.show and len(priority) < policy.preferred_limit:
                priority.append(ranked(c, w, Block.PRIORITY, pick.vendor))
            else:
                other.append(ranked(c, w, Block.OTHER, pick.vendor))
    other.extend(ranked(c, w, Block.OTHER, None) for c, w in items if vendor_of(c.lot) is None)
    other.sort(key=lambda r: _time_key(r.walking, r.distance_m))
    return priority + other[: policy.other_limit]
