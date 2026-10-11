"""Best-effort extraction of a headline hourly car rate from free-text fee descriptions.

Both feeds describe fees as prose. This only ever produces a *headline*: the first hourly rate
quoted for cars. The full text always stays available, and `None` means "could not tell", never
"free".
"""

from __future__ import annotations

import re

_SENTENCE_SPLIT = re.compile(r"[；;。\n]")
_HOURLY = re.compile(r"(\d{1,4}(?:,\d{3})?)\s*元\s*[/／]\s*(?:小)?時")
# New Taipei writes "小型車計時60元" with no "/時": the number right after 計時 is the hourly rate.
_TIMED = re.compile(r"計時\s*[：:]?\s*(?:小型車)?\s*(\d{1,4}(?:,\d{3})?)\s*元")
# A sentence about motorcycles or bicycles must not be mistaken for the car rate.
# "機車20元/時" (price directly after the word); "(含大型重型機車)30元/時" is a car-rate qualifier.
_MOTO_CLAUSE = re.compile(r"(?<!重型)機車\s*[：:]?\s*\d[^，,、]*")
_NOT_CAR = re.compile(r"^\s*(?:機車|重機|大型重型機車|自行車|腳踏車|大客車|大型車)")


def hourly_car_rate(fee_text: str) -> int | None:
    for sentence in _SENTENCE_SPLIT.split(fee_text):
        if not sentence.strip() or _NOT_CAR.match(sentence):
            continue
        # Drop any "機車20元/時" clause inside a mixed sentence before looking for the car rate.
        cleaned = _MOTO_CLAUSE.sub("", sentence)
        match = _HOURLY.search(cleaned) or _TIMED.search(cleaned)
        if match:
            return int(match.group(1).replace(",", ""))
    return None
