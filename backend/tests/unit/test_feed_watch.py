"""A real-time feed that stops moving is reported once, and its recovery once."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from yimmparking.adapters.alert.webhook import WebhookAlerter
from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.application.feed_watch import FeedWatch, source_statuses, stale_cities
from yimmparking.domain.model import AvailabilityBatch, AvailabilityReading, City

T0 = datetime(2026, 10, 19, 2, 26, tzinfo=UTC)  # 10:26 Taipei time


class Clock:
    def __init__(self) -> None:
        self.at = T0

    def now(self) -> datetime:
        return self.at


class Alerts:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.fail = fail

    def send(self, subject: str, body: str) -> None:
        if self.fail:
            raise httpx.ConnectError("no route")
        self.sent.append(f"{subject} | {body}")


def read(store: SqliteStore, city: City, at: datetime) -> None:
    store.record_availability(
        AvailabilityBatch(city, at, (AvailabilityReading(f"{city.value}:1", 5),))
    )


@pytest.fixture
def store() -> SqliteStore:
    s = SqliteStore(":memory:")
    read(s, City.TAIPEI, T0)
    read(s, City.NEW_TAIPEI, T0)
    yield s  # type: ignore[misc]
    s.close()


def test_a_feed_is_stale_after_an_hour_without_a_newer_reading(store: SqliteStore) -> None:
    fresh = source_statuses(store, T0 + timedelta(minutes=59))
    assert [s.stale for s in fresh] == [False, False]
    later = T0 + timedelta(minutes=61)
    assert [s.stale for s in source_statuses(store, later)] == [True, True]
    assert stale_cities(store, later) == {City.TAIPEI: T0, City.NEW_TAIPEI: T0}


def test_a_city_with_no_reading_at_all_is_stale() -> None:
    empty = SqliteStore(":memory:")
    assert stale_cities(empty, T0) == {City.TAIPEI: None, City.NEW_TAIPEI: None}
    empty.close()


def test_stopping_and_recovering_are_each_said_once(store: SqliteStore) -> None:
    clock, alerts = Clock(), Alerts()
    watch = FeedWatch(store, clock, alerts)

    clock.at = T0 + timedelta(minutes=30)
    read(store, City.NEW_TAIPEI, clock.at)  # New Taipei keeps moving; Taipei does not
    watch.check()
    assert alerts.sent == []

    clock.at = T0 + timedelta(hours=2)
    read(store, City.NEW_TAIPEI, clock.at)
    watch.check()
    watch.check()  # still stale: not repeated
    assert alerts.sent == [
        "YimmParking：臺北市即時空位資料停止更新 | 最後一筆資料時間：10/19 10:26（臺北時間）。"
        "這段期間該市停車場都會顯示「無資料」。"
    ]

    clock.at = T0 + timedelta(hours=3)
    read(store, City.TAIPEI, clock.at)
    read(store, City.NEW_TAIPEI, clock.at)
    watch.check()
    assert alerts.sent[-1] == "YimmParking：臺北市即時空位資料已恢復 | 最新資料時間：10/19 13:26（臺北時間）。"
    assert len(alerts.sent) == 2


def test_an_alert_that_cannot_be_delivered_does_not_stop_the_check(
    store: SqliteStore, caplog: pytest.LogCaptureFixture
) -> None:
    clock = Clock()
    clock.at = T0 + timedelta(hours=2)
    statuses = FeedWatch(store, clock, Alerts(fail=True)).check()  # must not raise
    assert all(s.stale for s in statuses)
    assert "停止更新" in caplog.text  # still in the log
    assert "could not deliver the alert" in caplog.text


def test_webhook_posts_the_alert_as_utf8_text() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    WebhookAlerter(http, "https://ntfy.example/topic").send("標題", "內容")
    [request] = sent
    assert request.method == "POST" and str(request.url) == "https://ntfy.example/topic"
    assert request.content.decode("utf-8") == "標題\n內容"
    assert request.headers["content-type"].startswith("text/plain")


def test_webhook_failure_is_an_error_for_the_caller_to_log() -> None:
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(httpx.HTTPStatusError):
        WebhookAlerter(http, "https://ntfy.example/topic").send("s", "b")
