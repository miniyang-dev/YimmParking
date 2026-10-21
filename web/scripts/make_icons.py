"""Draw the app icons: the start triangle, the course line and a control circle on white paper.

The same symbols as the course diagram in the lot view (DESIGN.md: Course Purple is the route).
Pure standard library, so it runs anywhere:

    python web/scripts/make_icons.py

Writes web/public/icons/*.png. "maskable" keeps everything inside the 80% safe zone that Android
may crop to a circle or a squircle.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

PAPER = (255, 255, 255)
COURSE = (178, 26, 143)  # #b21a8f
SUPERSAMPLE = 4
OUT = Path(__file__).resolve().parents[1] / "public" / "icons"


def _segment_distance(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _ink(x: float, y: float, scale: float) -> bool:
    """Whether the point (in a 0..1 square, already shrunk by `scale` about the centre) is ink."""
    u = (x - 0.5) / scale + 0.5
    v = (y - 0.5) / scale + 0.5
    stroke = 0.055

    # Start triangle, pointing up, lower left.
    cx, cy, side = 0.33, 0.66, 0.36
    h = side * math.sqrt(3) / 2
    tri = [(cx, cy - 2 * h / 3), (cx + side / 2, cy + h / 3), (cx - side / 2, cy + h / 3)]
    if any(_segment_distance(u, v, tri[i], tri[(i + 1) % 3]) < stroke / 2 for i in range(3)):
        return True

    # Control circle, upper right.
    ox, oy, r = 0.68, 0.32, 0.15
    if abs(math.hypot(u - ox, v - oy) - r) < stroke / 2:
        return True

    # Course line between them, with a gap at each symbol as on a printed course.
    dx, dy = ox - cx, oy - cy
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    inradius = side / (2 * math.sqrt(3))
    start = (cx + ux * (inradius + 0.06), cy + uy * (inradius + 0.06))
    end = (ox - ux * (r + 0.05), oy - uy * (r + 0.05))
    return _segment_distance(u, v, start, end) < stroke * 0.42


def render(size: int, scale: float) -> bytes:
    rows = []
    n = SUPERSAMPLE
    for py in range(size):
        row = bytearray([0])  # PNG filter: none
        for px in range(size):
            hits = sum(
                _ink((px + (i + 0.5) / n) / size, (py + (j + 0.5) / n) / size, scale)
                for i in range(n)
                for j in range(n)
            )
            a = hits / (n * n)
            row.extend(round(p * (1 - a) + c * a) for p, c in zip(PAPER, COURSE, strict=True))
        rows.append(bytes(row))
    return _png(size, b"".join(rows))


def _png(size: int, raw: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size, scale in (
        ("icon-192.png", 192, 1.0),
        ("icon-512.png", 512, 1.0),
        ("maskable-512.png", 512, 0.72),
        ("apple-touch-icon.png", 180, 0.9),
    ):
        (OUT / name).write_bytes(render(size, scale))
        print(f"wrote {OUT / name}")


if __name__ == "__main__":
    main()
