"""Whether each city's real-time feed is still moving, and saying so when it stops.

A feed can keep answering while its data stands still: 臺北市 once served the same UPDATETIME for
days. Every fetch "succeeded", so nothing failed loudly, and every lot of the city quietly read as
"no data". The age of the newest reading is what tells, so that is what is watched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from yimmparking.application.ports import Alerter, Clock, LotRepository
from yimmparking.domain.model import City, FreshnessPolicy

log = logging.getLogger(__name__)

# A reading older than this is already hidden from the list (see FreshnessPolicy), so from here on
# the whole city shows "no data": that is the moment worth knowing about.
STALE_AFTER = timedelta(seconds=FreshnessPolicy().expire_s)

CITY_NAME = {City.TAIPEI: "臺北市", City.NEW_TAIPEI: "新北市"}
_TAIPEI = timezone(timedelta(hours=8))


@dataclass(frozen=True, slots=True)
class SourceStatus:
    city: City
    lots: int
    as_of: datetime | None  # newest real-time reading held for the city
    stale: bool  # no reading, or the newest is older than STALE_AFTER


def source_statuses(
    repo: LotRepository, now: datetime, stale_after: timedelta = STALE_AFTER
) -> list[SourceStatus]:
    as_of = repo.last_availability_at()
    return [
        SourceStatus(
            city=city,
            lots=repo.lot_count(city),
            as_of=as_of.get(city),
            stale=city not in as_of or now - as_of[city] > stale_after,
        )
        for city in City
    ]


def stale_cities(
    repo: LotRepository, now: datetime, stale_after: timedelta = STALE_AFTER
) -> dict[City, datetime | None]:
    """`{city: newest reading}` for every city whose feed has stopped moving."""
    as_of = repo.last_availability_at()
    return {
        city: as_of.get(city)
        for city in City
        if city not in as_of or now - as_of[city] > stale_after
    }


def _local(moment: datetime | None) -> str:
    if moment is None:
        return "沒有任何資料"
    return moment.astimezone(_TAIPEI).strftime("%m/%d %H:%M")


class FeedWatch:
    """Alerts once when a city's feed goes stale and once when it recovers.

    State is kept in memory: after a restart a feed that is still stale is reported again, once.
    """

    def __init__(
        self,
        repo: LotRepository,
        clock: Clock,
        alerter: Alerter,
        stale_after: timedelta = STALE_AFTER,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._alerter = alerter
        self._stale_after = stale_after
        self._stale: set[City] = set()

    def check(self) -> list[SourceStatus]:
        statuses = source_statuses(self._repo, self._clock.now(), self._stale_after)
        now_stale = {s.city for s in statuses if s.stale}
        for s in statuses:
            if s.city in now_stale and s.city not in self._stale:
                self._send(
                    f"YimmParking：{CITY_NAME[s.city]}即時空位資料停止更新",
                    f"最後一筆資料時間：{_local(s.as_of)}（臺北時間）。"
                    f"這段期間該市停車場都會顯示「無資料」。",
                )
            elif s.city not in now_stale and s.city in self._stale:
                self._send(
                    f"YimmParking：{CITY_NAME[s.city]}即時空位資料已恢復",
                    f"最新資料時間：{_local(s.as_of)}（臺北時間）。",
                )
        self._stale = now_stale
        return statuses

    def _send(self, subject: str, body: str) -> None:
        log.warning("%s %s", subject, body)
        try:
            self._alerter.send(subject, body)
        except Exception:  # an alert that cannot be delivered must not stop ingestion
            log.exception("could not deliver the alert: %s", subject)
