#!/usr/bin/env python3
"""Generates the placeholder logo/product PNGs served from /static (stdlib only, deterministic)."""
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "backend" / "app" / "static"
IMAGES = {
    "tenant-alpha": "#0B5FFF", "tenant-beta": "#0E7C3A",
    "club-alpha-1": "#0B5FFF", "club-alpha-2": "#C2185B", "club-alpha-3": "#EF6C00", "club-alpha-4": "#455A64",
    "club-beta-1": "#0E7C3A", "club-beta-2": "#6A1B9A",
    "prod-jersey-001": "#1E88E5", "prod-scarf-001": "#3949AB", "prod-cap-001": "#212121",
    "prod-wallpaper-001": "#00897B",
}


def png(color: str, size: int = 192) -> bytes:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    rows = []
    c = size / 2
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
            if d < size * 0.42:
                row += bytes((r, g, b, 255))
            elif d < size * 0.48:
                row += bytes((255, 255, 255, 255))
            else:
                row += bytes((0, 0, 0, 0))
        rows.append(bytes(row))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, color in IMAGES.items():
        (OUT / f"{name}.png").write_bytes(png(color))
    print(f"wrote {len(IMAGES)} images to {OUT}")
