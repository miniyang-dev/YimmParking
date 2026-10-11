"""Vendors the user can put first, and how many lots of each to show.

Only the large operators are configurable. A small operator cannot be added to the list: its lots
are still listed, after the configured vendors, by distance.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from yimmparking.domain.model import Brand, ParkingLot

DEFAULT_SHOW = 2  # lots of one vendor shown before the rest of the list
MAX_SHOW = 8


class Vendor(StrEnum):
    """Configurable vendors. The declaration order is the default priority order."""

    IPARKING_DODOHOME = "iparking_dodohome"  # 嘟嘟房 that iParking can pay for
    DODOHOME = "dodohome"  # 嘟嘟房 without iParking
    LIANTONG = "liantong"  # 台灣聯通
    TIMES = "times"  # Times 停車場
    USPACE = "uspace"  # USPACE


_BRAND_VENDOR: dict[Brand, Vendor] = {
    Brand.LIANTONG: Vendor.LIANTONG,
    Brand.TIMES: Vendor.TIMES,
    Brand.USPACE: Vendor.USPACE,
}


def vendor_of(lot: ParkingLot) -> Vendor | None:
    """The configurable vendor a lot belongs to, or None for a small operator."""
    if lot.brand is Brand.DODOHOME:
        return Vendor.IPARKING_DODOHOME if lot.has_iparking else Vendor.DODOHOME
    return _BRAND_VENDOR.get(lot.brand)


@dataclass(frozen=True, slots=True)
class VendorPick:
    vendor: Vendor
    show: int  # 0 keeps the vendor in the list but not in the first section

    def __post_init__(self) -> None:
        if not 0 <= self.show <= MAX_SHOW:
            raise ValueError(f"show must be between 0 and {MAX_SHOW}")


@dataclass(frozen=True, slots=True)
class Preference:
    """Every configurable vendor exactly once, in priority order."""

    picks: tuple[VendorPick, ...] = field(
        default_factory=lambda: tuple(VendorPick(v, DEFAULT_SHOW) for v in Vendor)
    )

    def __post_init__(self) -> None:
        vendors = [p.vendor for p in self.picks]
        if sorted(vendors) != sorted(Vendor):
            raise ValueError("each configurable vendor must appear exactly once")

    @classmethod
    def from_picks(cls, given: Iterable[VendorPick]) -> Preference:
        """The given order first; vendors not mentioned follow with nothing shown."""
        listed = list(given)
        seen = {p.vendor for p in listed}
        if len(seen) != len(listed):
            raise ValueError("a vendor is listed more than once")
        rest = tuple(VendorPick(v, 0) for v in Vendor if v not in seen)
        return cls(picks=(*listed, *rest))

    def show_of(self, vendor: Vendor) -> int:
        return next(p.show for p in self.picks if p.vendor is vendor)
