#!/usr/bin/env python3
"""Fixtures for the compact uint16 ingest support matrix.

Ported from #123 (cfa331eb, tests/compact_ingest_fixtures.py) for the RC0 QF;
see docs/rc0/qf/README.md for the adaptation record.

The point of the pair produced here is that the two movies differ in exactly
one property: the TIFF SampleFormat. uint16 selects the native compact ingest
(motioncorr_runner.cpp:1465-1469 requires a .tif* name and UShort data), float32
does not, and (float)uint16 is exact, so every downstream stage sees the same
values. That makes the float32 twin both the ineligible-format control and the
same-backend reference the uint16 products must reproduce byte for byte.

No numpy: the values have to be reproducible as exact integers, and the whole
point is that the two encodings carry the same ones.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


# QF adaptation: #123 imported this writer from tests/test_tiff_read.py at
# cfa331eb. Main's copy has since changed signature (no sample_format), so the
# cfa331eb function is inlined here verbatim. The fixture bytes are therefore
# the ones #123's runs of record used; run_compact_ingest_support_matrix.py
# checks every generated input against those recorded hashes.
def write_tiff(path, frame_rows, bits, compression, rows_per_strip, logical_width,
               sample_format=1):
    """Minimal little-endian classic TIFF writer, one IFD per frame.

    sample_format is the TIFF SampleFormat tag: 1 unsigned integer (the reader's
    UShort branch at 16 bits), 3 IEEE float. The compact-ingest support matrix
    needs both from one writer, because its uint16/float32 arms must differ in
    nothing but the sample type.
    """
    height = len(frame_rows[0])
    with open(path, "wb") as fh:
        fh.write(b"II" + struct.pack("<HI", 42, 0))
        strip_tables = []
        for rows in frame_rows:
            offs, counts = [], []
            for start in range(0, height, rows_per_strip):
                raw = b"".join(rows[start:start + rows_per_strip])
                blob = zlib.compress(raw) if compression == 8 else raw
                offs.append(fh.tell())
                counts.append(len(blob))
                fh.write(blob)
            strip_tables.append((offs, counts))

        prev_next_field = 4
        for offs, counts in strip_tables:
            n = len(offs)
            if n > 1:
                off_pos = fh.tell(); fh.write(struct.pack("<%dI" % n, *offs))
                cnt_pos = fh.tell(); fh.write(struct.pack("<%dI" % n, *counts))
            else:
                off_pos, cnt_pos = offs[0], counts[0]
            entries = sorted([
                (256, 4, 1, logical_width if bits != 4 else logical_width // 2),
                (257, 4, 1, height),
                (258, 3, 1, 8 if bits == 4 else bits),
                (259, 3, 1, compression),
                (262, 3, 1, 1),
                (273, 4, n, off_pos),
                (277, 3, 1, 1),
                (278, 4, 1, rows_per_strip),
                (279, 4, n, cnt_pos),
                (284, 3, 1, 1),
                (339, 3, 1, sample_format),
            ])
            ifd_pos = fh.tell()
            fh.write(struct.pack("<H", len(entries)))
            for tag, typ, count, value in entries:
                payload = struct.pack("<HH", value, 0) if (typ == 3 and count == 1) \
                    else struct.pack("<I", value)
                fh.write(struct.pack("<HHI", tag, typ, count) + payload)
            next_field = fh.tell()
            fh.write(struct.pack("<I", 0))
            here = fh.tell()
            fh.seek(prev_next_field); fh.write(struct.pack("<I", ifd_pos)); fh.seek(here)
            prev_next_field = next_field


write_tiff_pages = write_tiff

SAMPLEFORMAT_UINT = 1
SAMPLEFORMAT_IEEEFP = 3


def synthetic_movie(nx: int, ny: int, n_frames: int, seed: int = 11) -> List[List[int]]:
    """A drifting Gaussian-ish blob on textured background, as uint16 counts.

    Integer-valued so the uint16 and float32 encodings are the same numbers, and
    bright enough that patch alignment has something to lock onto.
    """
    state = seed & 0x7FFFFFFF or 1

    def rnd() -> float:
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    base = [int(200.0 + rnd() * 120.0) for _ in range(nx * ny)]
    frames = []
    for n in range(n_frames):
        frame = list(base)
        cx = nx // 2 + n
        cy = ny // 2 + (n % 3)
        radius = max(3, min(nx, ny) // 8)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x, y = cx + dx, cy + dy
                if not (0 <= x < nx and 0 <= y < ny):
                    continue
                falloff = max(0, radius * radius - dx * dx - dy * dy)
                frame[y * nx + x] = min(65535, frame[y * nx + x] + 40 * falloff)
        frames.append(frame)
    return frames


def _rows(frame: Sequence[int], nx: int, ny: int, fmt: str) -> List[bytes]:
    packer = struct.Struct("<" + fmt * nx)
    if fmt == "f":
        return [packer.pack(*[float(v) for v in frame[y * nx:(y + 1) * nx]]) for y in range(ny)]
    return [packer.pack(*frame[y * nx:(y + 1) * nx]) for y in range(ny)]


def write_movie(path: Path, frames: Sequence[Sequence[int]], nx: int, ny: int,
                *, floating: bool = False, compression: int = 8,
                rows_per_strip: int = 0) -> None:
    """Write one movie. compression 8 is Adobe Deflate, as the tutorial data uses."""
    fmt = "f" if floating else "H"
    bits = 32 if floating else 16
    sample_format = SAMPLEFORMAT_IEEEFP if floating else SAMPLEFORMAT_UINT
    pages = [_rows(frame, nx, ny, fmt) for frame in frames]
    path.parent.mkdir(parents=True, exist_ok=True)
    write_tiff_pages(str(path), pages, bits, compression,
                     rows_per_strip or ny, nx, sample_format=sample_format)


def write_gain(path: Path, nx: int, ny: int, value: float = 1.0) -> None:
    """A float32 mode-2 MRC gain reference of the movie's geometry.

    A non-unit but exactly representable multiplier keeps the gain observable
    while staying bit-exact through both the device and the host kernels.
    """
    count = nx * ny
    header = bytearray(1024)
    struct.pack_into("<3i", header, 0, nx, ny, 1)
    struct.pack_into("<i", header, 12, 2)
    struct.pack_into("<3i", header, 28, nx, ny, 1)
    struct.pack_into("<3f", header, 40, float(nx), float(ny), 1.0)
    struct.pack_into("<3f", header, 52, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", header, 64, 1, 2, 3)
    struct.pack_into("<3f", header, 76, value, value, value)
    header[208:212] = b"MAP "
    struct.pack_into("<i", header, 212, 0x00004144)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(bytes(header))
        fh.write(struct.pack(f"<{count}f", *([value] * count)))


def write_star(path: Path, movies: Sequence[str], *, angpix: float,
               voltage: float = 300.0, cs: float = 2.7, q0: float = 0.1,
               optics_group: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# version 30001\n\ndata_optics\n\nloop_\n"
        "_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
        "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n"
        "_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n"
        f"opticsGroup{optics_group} {optics_group} {angpix:.3f} {voltage} {cs} {q0}\n\n"
        "# version 30001\n\ndata_movies\n\nloop_\n"
        "_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n"
        + "\n".join(f"{m} {optics_group}" for m in movies) + "\n"
    )


def truncate_after_frame(source: Path, target: Path, keep_frames: int) -> Dict[str, int]:
    """Cut a movie mid-strip so the reader fails on a real short read.

    Distinct from a cleanly shortened valid TIFF: the directory still advertises
    every frame, so this is a damaged movie and not a smaller legal one.
    """
    raw = source.read_bytes()
    offsets = _ifd_strip_offsets(raw)
    if keep_frames >= len(offsets):
        raise ValueError(f"movie has {len(offsets)} frames; cannot keep {keep_frames}")
    cut = offsets[keep_frames] + 16
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw[:cut])
    return {"original_bytes": len(raw), "truncated_bytes": cut, "frames_declared": len(offsets)}


def _ifd_strip_offsets(raw: bytes) -> List[int]:
    if raw[:2] != b"II":
        raise ValueError("only little-endian classic TIFF fixtures are supported")
    offsets: List[int] = []
    next_ifd = struct.unpack_from("<I", raw, 4)[0]
    while next_ifd:
        count = struct.unpack_from("<H", raw, next_ifd)[0]
        first: Tuple[int, ...] = ()
        for i in range(count):
            tag, typ, n, value = struct.unpack_from("<HHII", raw, next_ifd + 2 + 12 * i)
            if tag == 273:
                first = (value,) if n == 1 else struct.unpack_from("<I", raw, value)
        if not first:
            raise ValueError("TIFF directory has no StripOffsets")
        offsets.append(first[0])
        next_ifd = struct.unpack_from("<I", raw, next_ifd + 2 + 12 * count)[0]
    return sorted(offsets)
