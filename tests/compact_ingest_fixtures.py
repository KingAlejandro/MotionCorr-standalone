#!/usr/bin/env python3
"""Fixtures for the compact uint16 ingest support matrix.

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

import importlib.util
import struct
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

_TIFF_READ = Path(__file__).resolve().parent / "test_tiff_read.py"
_SPEC = importlib.util.spec_from_file_location("compact_ingest_tiff_writer", _TIFF_READ)
_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
write_tiff_pages = _MODULE.write_tiff

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
