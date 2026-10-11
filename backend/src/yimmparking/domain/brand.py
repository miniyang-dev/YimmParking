"""Brand classification.

Neither source exposes an operator field, so a lot's operator is inferred from its name and
then from its contact phone. The rules are data, so a new operator is a table row, not a code
change. The evidence used is kept on the lot: a phone-only match is weaker than a name match
and the UI is allowed to say so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from yimmparking.domain.model import Brand, BrandEvidence, ParkingLot


@dataclass(frozen=True, slots=True)
class BrandRule:
    brand: Brand
    name_keywords: tuple[str, ...]
    phone_numbers: tuple[str, ...]  # local numbers without area code, digits only


DEFAULT_RULES: tuple[BrandRule, ...] = (
    BrandRule(Brand.DODOHOME, name_keywords=("嘟嘟房",), phone_numbers=("26550818",)),
    BrandRule(Brand.LIANTONG, name_keywords=("台灣聯通", "聯通"), phone_numbers=("25235000",)),
    BrandRule(Brand.TIMES, name_keywords=("Times", "TIMES"), phone_numbers=()),
    BrandRule(Brand.USPACE, name_keywords=("USPACE", "Uspace", "uspace"), phone_numbers=()),
)

# Taipei / New Taipei area code is 02, so a local number may be written with a leading "2".
_AREA_PREFIXES = ("", "2")


def _normalize_phone(raw: str) -> str:
    return re.sub(r"\D", "", raw).lstrip("0")


def _phone_matches(raw: str, local_number: str) -> bool:
    digits = _normalize_phone(raw)
    if not digits:
        return False
    # `startswith` also covers numbers written with an extension (e.g. 25235000#1138).
    return any(digits.startswith(prefix + local_number) for prefix in _AREA_PREFIXES)


class BrandClassifier:
    def __init__(self, rules: tuple[BrandRule, ...] = DEFAULT_RULES) -> None:
        self._rules = rules

    def classify(self, name: str, phone: str) -> tuple[Brand, BrandEvidence]:
        # Names are checked for every rule before any phone, so a name always outranks a phone.
        for rule in self._rules:
            if any(keyword in name for keyword in rule.name_keywords):
                return rule.brand, BrandEvidence.NAME
        for rule in self._rules:
            if any(_phone_matches(phone, number) for number in rule.phone_numbers):
                return rule.brand, BrandEvidence.PHONE
        return Brand.OTHER, BrandEvidence.NONE

    def apply(self, lot: ParkingLot) -> ParkingLot:
        brand, evidence = self.classify(lot.name, lot.phone)
        return replace(lot, brand=brand, brand_evidence=evidence)
