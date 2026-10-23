"""TDX use is counted in its own points and stops at a ceiling under the free allowance."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from yimmparking.adapters.store.sqlite import SqliteStore
from yimmparking.adapters.tdx.client import TdxClient
from yimmparking.application.tdx_budget import TdxBudget, TdxBudgetSpent


class Clock:
    def __init__(self) -> None:
        self.at = datetime(2026, 10, 23, 8, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.at


@pytest.fixture
def store() -> SqliteStore:
    s = SqliteStore(":memory:")
    yield s  # type: ignore[misc]
    s.close()


def test_points_follow_tdx_pricing_calls_plus_data(store: SqliteStore) -> None:
    budget = TdxBudget(store, Clock(), limit_millipoints=2700)
    for _ in range(1500):
        budget.record(0)
    assert budget.used_millipoints() == 1000  # 1,500 calls = 1 point
    budget.record(150 * 1024 * 1024)  # 150 MB = 1 more point (and one more call)
    assert budget.used_millipoints() == 2000


def test_calls_stop_at_the_ceiling(store: SqliteStore) -> None:
    budget = TdxBudget(store, Clock(), limit_millipoints=10)
    for _ in range(15):  # 15 calls = 0.010 points
        budget.record(0)
    with pytest.raises(TdxBudgetSpent, match="0.01 of 0.01 points"):
        budget.check()


def test_a_new_month_starts_from_zero(store: SqliteStore) -> None:
    clock = Clock()
    budget = TdxBudget(store, clock, limit_millipoints=10)
    for _ in range(15):
        budget.record(0)
    clock.at = datetime(2026, 11, 1, 0, 5, tzinfo=UTC)
    budget.check()  # no longer spent
    assert budget.used_millipoints() == 0


def test_the_client_counts_each_answered_call_with_its_size(store: SqliteStore) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 86400})
        return httpx.Response(200, json={"ParkingSegments": [{"x": "y" * 3000}]})

    budget = TdxBudget(store, Clock(), limit_millipoints=2700)
    client = TdxClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "id",
        "secret",
        token_url="https://tdx.example/token",
        api_base="https://tdx.example/api",
        budget=budget,
    )
    client.get_items("v1/x")
    client.get_items("v1/x")
    period = budget.period
    assert store.used("tdx_calls", period) == 2  # the token request is not a data call
    assert store.used("tdx_kb", period) == 2 * 3  # ~3 KB each, rounded up


def test_the_client_makes_no_call_once_the_budget_is_spent(store: SqliteStore) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"access_token": "t", "expires_in": 86400})

    budget = TdxBudget(store, Clock(), limit_millipoints=1)
    for _ in range(2):
        budget.record(0)
    client = TdxClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "id",
        "secret",
        token_url="https://tdx.example/token",
        api_base="https://tdx.example/api",
        budget=budget,
    )
    with pytest.raises(TdxBudgetSpent):
        client.get_items("v1/x")
    assert sent == []
