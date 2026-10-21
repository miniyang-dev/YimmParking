"""Alerts as a plain-text POST to one URL the owner chooses.

Plain text is what the most receivers take as-is. With ntfy (https://ntfy.sh/<a topic only you
know>) it arrives as a phone push with no account; a self-hosted ntfy or any endpoint that reads
the body works the same. Without a URL alerts are only logged.
"""

from __future__ import annotations

import httpx


class WebhookAlerter:
    def __init__(self, http: httpx.Client, url: str) -> None:
        self._http = http
        self._url = url

    def send(self, subject: str, body: str) -> None:
        # Subject and body go in the body: HTTP headers cannot carry Chinese text as-is.
        response = self._http.post(
            self._url,
            content=f"{subject}\n{body}".encode(),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        response.raise_for_status()


class LogOnlyAlerter:
    """No destination configured: `FeedWatch` already logs every alert, so nothing more to do."""

    def send(self, subject: str, body: str) -> None:
        return None
