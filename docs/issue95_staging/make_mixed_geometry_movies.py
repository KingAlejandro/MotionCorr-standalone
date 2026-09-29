#!/usr/bin/env python3
"""Build a dataset of successive uint16 TIFF movies with DIFFERENT geometries.

The compact-ingest staging is sized per movie and released per movie. A run whose
movies all share one geometry cannot tell a correctly re-sized mapping from a
cached one, so this dataset alternates two shapes and two frame counts. It writes
Adobe-Deflate strips with RowsPerStrip=1, the production layout, and needs no
codec or array dependency.

Usage: make_mixed_geometry_movies.py <dataset-root>
"""
import struct, sys, zlib
from pathlib import Path

# (stem, nx, ny, n_frames); the order in movies.star alternates the geometries so
# a movie is always preceded by one of a different size.
MOVIES = [
    ("small_a", 512, 384, 10),
    ("large_b", 1024, 768, 12),
    ("small_c", 512, 384, 10),
    ("large_d", 896, 640, 14),
]


def frame_rows(nx, ny, iframe, stem):
    """Deterministic, frame-dependent, non-constant content with wrapping edges."""
    seed = (sum(ord(c) for c in stem) * 131 + iframe * 7919) & 0xFFFF
    rows = []
    for y in range(ny):
        row = bytearray()
        for x in range(nx):
            v = (seed + (x * 37) % 251 + (y * 91) % 253 + ((x + y + iframe) % 17) * 13) & 0x0FFF
            row += struct.pack("<H", v + 100)
        rows.append(bytes(row))
    return rows


def write_tiff(path, nx, ny, n_frames, stem):
    tags = 12
    ifd_bytes = 2 + 12 * tags + 4
    strips = [[zlib.compress(r, 6) for r in frame_rows(nx, ny, i, stem)] for i in range(n_frames)]
    # Per frame: IFD, then StripOffsets[ny] and StripByteCounts[ny], then the data.
    blocks, cursor = [], 8
    for i in range(n_frames):
        arrays = 2 * 4 * ny
        data = b"".join(strips[i])
        blocks.append({"ifd": cursor, "arr": cursor + ifd_bytes,
                       "data": cursor + ifd_bytes + arrays, "bytes": data})
        cursor += ifd_bytes + arrays + len(data)
    out = bytearray(struct.pack("<2sHI", b"II", 42, 8))
    for i, b in enumerate(blocks):
        offs, counts, at = [], [], b["data"]
        for s in strips[i]:
            offs.append(at); counts.append(len(s)); at += len(s)
        entries = [(256, 4, 1, nx), (257, 4, 1, ny), (258, 3, 1, 16), (259, 3, 1, 8),
                   (262, 3, 1, 1), (273, 4, ny, b["arr"]), (277, 3, 1, 1),
                   (278, 4, 1, 1), (279, 4, ny, b["arr"] + 4 * ny), (284, 3, 1, 1),
                   (339, 3, 1, 1), (317, 3, 1, 1)]
        entries.sort()
        out += struct.pack("<H", len(entries))
        for tag, typ, count, value in entries:
            payload = struct.pack("<HH", value, 0) if (typ == 3 and count == 1) else struct.pack("<I", value)
            out += struct.pack("<HHI", tag, typ, count) + payload
        out += struct.pack("<I", blocks[i + 1]["ifd"] if i + 1 < n_frames else 0)
        out += struct.pack("<%dI" % ny, *offs) + struct.pack("<%dI" % ny, *counts)
        out += b["bytes"]
    path.write_bytes(bytes(out))


def main():
    root = Path(sys.argv[1]).resolve()
    (root / "Movies").mkdir(parents=True, exist_ok=False)
    for stem, nx, ny, nf in MOVIES:
        write_tiff(root / "Movies" / f"{stem}.tif", nx, ny, nf, stem)
    star = ["", "data_movies", "", "loop_", "_rlnMicrographMovieName #1", ""]
    star += [f"Movies/{stem}.tif" for stem, _, _, _ in MOVIES] + [""]
    (root / "movies.star").write_text("\n".join(star) + "\n")
    spec = {"movies": [f"Movies/{s}.tif" for s, _, _, _ in MOVIES],
            "shapes": {s: [nx, ny, 1] for s, nx, ny, _ in MOVIES},
            "frames": {s: nf for s, _, _, nf in MOVIES}}
    import json
    (root / "geometry.json").write_text(json.dumps(spec, indent=2) + "\n")
    for stem, nx, ny, nf in MOVIES:
        print(f"{stem}.tif {nx}x{ny}x{nf} "
              f"{(root / 'Movies' / (stem + '.tif')).stat().st_size} bytes")


if __name__ == "__main__":
    main()
