"""iParking (俥酷) station directory, read from the public lot list page.

The page is server-rendered; each station is a `div.lot-item` carrying data-* attributes and a
Google Maps link with the coordinates. There is no API. The page's terms of use have not been
reviewed, so the caller is expected to fetch it rarely and cache the result.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import httpx

from yimmparking.application.ports import SourceError
from yimmparking.domain.geo import GeoPoint
from yimmparking.domain.model import IParkingStation

LOTS_URL = "https://www.findata.com.tw/iparking/lots"
_COORD = re.compile(r"/maps/dir//(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")


class _LotListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stations: list[IParkingStation] = []
        self._current: dict[str, str] | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "div" and "lot-item" in a.get("class", "").split() and a.get("data-code"):
            self._flush()
            self._current = {
                "code": a["data-code"],
                "name": a.get("data-name", ""),
                "address": a.get("data-address", ""),
                "city": a.get("data-city", ""),
            }
            self._depth = 1
            return
        if self._current is None:
            return
        if tag == "div":
            self._depth += 1
        if tag == "a" and "lot-icon-map" in a.get("class", "").split():
            match = _COORD.search(a.get("href", ""))
            if match:
                self._current["lat"], self._current["lng"] = match.group(1), match.group(2)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None or tag != "div":
            return
        self._depth -= 1
        if self._depth <= 0:
            self._flush()

    def _flush(self) -> None:
        item, self._current = self._current, None
        if not item or "lat" not in item:
            return
        try:
            point = GeoPoint(float(item["lat"]), float(item["lng"]))
        except ValueError:
            return
        self.stations.append(
            IParkingStation(
                code=item["code"],
                # Names occasionally carry a non-breaking space.
                name=item["name"].replace("\xa0", " ").strip(),
                address=item["address"].replace("\xa0", " ").strip(),
                city_code=item["city"],
                location=point,
            )
        )

    def close(self) -> None:
        super().close()
        self._flush()


def parse_stations(html: str) -> list[IParkingStation]:
    parser = _LotListParser()
    parser.feed(html)
    parser.close()
    return parser.stations


class FindataDirectory:
    def __init__(self, http: httpx.Client, url: str = LOTS_URL) -> None:
        self._http = http
        self._url = url

    def fetch_stations(self) -> list[IParkingStation]:
        try:
            response = self._http.get(self._url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceError(f"{self._url}: {exc}") from exc
        stations = parse_stations(response.text)
        if not stations:
            # A page that parses to nothing means the markup changed, not that there are no
            # stations; fail loudly rather than silently dropping every iParking flag.
            raise SourceError(f"{self._url}: no stations found, page structure may have changed")
        return stations
