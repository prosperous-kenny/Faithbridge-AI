"""Generate the PWA icons for apps/web (run from apps/web: python scripts/generate_icons.py).

Stdlib-only PNG writer so the icons are reproducible without Pillow or a
design tool: a 5x7 bitmap of "F" (matching the header logo) rendered white
on amber-600, the brand colour. Output: public/icons/icon-192.png and
public/icons/icon-512.png — both committed, this script exists so a colour
or glyph change can be re-applied consistently.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

# 5x7 bitmap, "#" = foreground pixel.
GLYPH = [
    "#####",
    "#....",
    "#....",
    "####.",
    "#....",
    "#....",
    "#....",
]

BG = (217, 119, 6)  # tailwind amber-600
FG = (255, 255, 255)
ROWS = len(GLYPH)
COLS = len(GLYPH[0])

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "public" / "icons"


def render(size: int) -> bytes:
    """RGB rows for a ``size``x``size`` icon with the glyph centered."""
    cell = size // 11  # glyph occupies ~7/11 of the canvas, margins rest
    glyph_w, glyph_h = COLS * cell, ROWS * cell
    x0 = (size - glyph_w) // 2
    y0 = (size - glyph_h) // 2

    rows: list[bytes] = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            on_glyph = (
                x0 <= x < x0 + glyph_w and y0 <= y < y0 + glyph_h
            )
            if on_glyph:
                gx, gy = (x - x0) // cell, (y - y0) // cell
                colour = FG if GLYPH[gy][gx] == "#" else BG
            else:
                colour = BG
            row.extend(colour)
        rows.append(bytes(row))
    return b"".join(b"\x00" + row for row in rows)  # filter byte: None


def write_png(path: Path, size: int) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # RGB, 8-bit
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(render(size), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)
    print(f"wrote {path.name} ({size}x{size}, {len(png)} bytes)")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        write_png(OUTPUT_DIR / f"icon-{size}.png", size)


if __name__ == "__main__":
    main()
