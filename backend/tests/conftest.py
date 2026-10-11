from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail loudly if any code path tries to reach the real network.

    Adapters take an injected `httpx.Client`; tests hand them a MockTransport. This guard sits at
    the outermost layer so that a forgotten injection cannot silently hit a live service.
    """

    def _blocked(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"real network access attempted: {request.method} {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked)
    yield


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 10, 10, 14, 40, tzinfo=UTC)  # 22:40 Taiwan time


@pytest.fixture
def make_client() -> Callable[[Callable[[httpx.Request], httpx.Response]], httpx.Client]:
    def _make(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    return _make
