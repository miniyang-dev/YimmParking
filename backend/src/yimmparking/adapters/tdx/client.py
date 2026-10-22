"""TDX (交通部運輸資料流通服務) access: an OAuth client-credentials token, then paged GETs.

From the official sample code (github.com/tdxmotc/SampleCode): the token comes from
`POST .../openid-connect/token` with `grant_type=client_credentials`, lasts `expires_in` seconds
(one day by default) and should be cached; the token endpoint allows 20 calls a minute per IP,
counted apart from the data endpoints. Data calls carry `Authorization: Bearer <token>`.
`$top` defaults to 30 rows, so every list is paged explicitly.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from yimmparking.application.ports import CurbUnconfigured, SourceError

TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
API_BASE = "https://tdx.transportdata.tw/api/basic"
PAGE_SIZE = 5000
MAX_PAGES = 10
# Renew a little before the stated expiry, so a request never goes out with a dying token.
EXPIRY_MARGIN_S = 300
# After a failed token request, fail fast for this long instead of waiting out another timeout
# (one search reads two cities; both would otherwise wait).
TOKEN_RETRY_S = 60


class TdxClient:
    def __init__(
        self,
        http: httpx.Client,
        client_id: str | None,
        client_secret: str | None,
        *,
        token_url: str = TOKEN_URL,
        api_base: str = API_BASE,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._id = client_id
        self._secret = client_secret
        self._token_url = token_url
        self._api_base = api_base.rstrip("/")
        self._monotonic = monotonic
        self._token: str | None = None
        self._expires = 0.0
        self._failed: tuple[float, SourceError] | None = None
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._id and self._secret)

    def _bearer(self) -> str:
        if not self.configured:
            raise CurbUnconfigured("TDX_CLIENT_ID / TDX_CLIENT_SECRET are not configured")
        with self._lock:
            if self._token is None or self._monotonic() >= self._expires:
                if self._failed and self._monotonic() - self._failed[0] < TOKEN_RETRY_S:
                    raise self._failed[1]
                try:
                    self._token, lifetime = self._fetch_token()
                except SourceError as exc:
                    self._failed = (self._monotonic(), exc)
                    raise
                self._failed = None
                self._expires = self._monotonic() + max(0, lifetime - EXPIRY_MARGIN_S)
            return self._token

    def _fetch_token(self) -> tuple[str, int]:
        try:
            response = self._http.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._id or "",
                    "client_secret": self._secret or "",
                },
            )
            response.raise_for_status()
            body = response.json()
            return str(body["access_token"]), int(body.get("expires_in", 86400))
        except httpx.HTTPStatusError as exc:
            # 400/401 here means the id or secret is wrong; the secret itself is never logged.
            raise SourceError(f"TDX token refused: HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise SourceError(f"TDX token unavailable: {exc}") from exc

    def get_items(self, path: str) -> list[dict[str, Any]]:
        """Every row of a TDX list endpoint, paged. Accepts both the `{"Items": [...]}` wrapper
        and a bare array, as TDX endpoints differ."""
        url = f"{self._api_base}/{path.lstrip('/')}"
        rows: list[dict[str, Any]] = []
        for page in range(MAX_PAGES):
            params: dict[str, str | int] = {
                "$format": "JSON",
                "$top": PAGE_SIZE,
                "$skip": page * PAGE_SIZE,
            }
            try:
                response = self._http.get(
                    url,
                    params=params,
                    headers={
                        "Authorization": f"Bearer {self._bearer()}",
                        "Accept-Encoding": "gzip",
                    },
                )
                if response.status_code == 401:
                    # The token was revoked or expired early: drop it so the next call renews.
                    with self._lock:
                        self._token = None
                response.raise_for_status()
                body = response.json()
            except httpx.HTTPStatusError as exc:
                raise SourceError(f"{path}: HTTP {exc.response.status_code}") from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise SourceError(f"{path}: {exc}") from exc
            chunk = body.get("Items") if isinstance(body, dict) else body
            if not isinstance(chunk, list):
                raise SourceError(f"{path}: unexpected body")
            rows.extend(row for row in chunk if isinstance(row, dict))
            if len(chunk) < PAGE_SIZE:
                return rows
        raise SourceError(f"{path}: more than {MAX_PAGES} pages, refusing to continue")
