#!/usr/bin/env python3
"""MRC 2014 and RELION STAR I/O for the issue #60 calibration.

Read-only with respect to every other owner's tooling: this module duplicates
the small amount of parsing it needs rather than importing from
``tools/compare_motioncorr.py``, so that the comparator stays untouched.

The displacement-field evaluator reproduces ``Micrograph::getShiftAt``
(``src/micrograph_model.cpp:360``) exactly; see the ADR section 5.1.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

MRC_DTYPES = {
    0: np.dtype("i1"),
    1: np.dtype("<i2"),
    2: np.dtype("<f4"),
    6: np.dtype("<u2"),
    12: np.dtype("<f2"),
}

NUM_COEFFS_PER_DIM = 18  # src/micrograph_model.cpp:29


# ---------------------------------------------------------------------------
# MRC
# ---------------------------------------------------------------------------

def read_mrc(path: Path) -> Tuple[np.ndarray, bytes]:
    """Return (pixels, raw 1024-byte header). Pixels are float64, shape (nz, ny, nx)."""
    raw = Path(path).read_bytes()
    if len(raw) < 1024:
        raise ValueError(f"file too short for an MRC header: {path}")
    header = raw[:1024]
    nx, ny, nz, mode = struct.unpack_from("<4i", header, 0)
    nsymbt = struct.unpack_from("<i", header, 92)[0]
    if min(nx, ny, nz) <= 0 or nsymbt < 0:
        raise ValueError(f"invalid MRC dimensions in {path}")
    if mode not in MRC_DTYPES:
        raise ValueError(f"unsupported MRC mode {mode} in {path}")
    dtype = MRC_DTYPES[mode]
    offset = 1024 + nsymbt
    count = nx * ny * nz
    need = offset + count * dtype.itemsize
    if len(raw) < need:
        raise ValueError(f"truncated MRC payload in {path}: {len(raw)} < {need}")
    data = np.frombuffer(raw, dtype=dtype, count=count, offset=offset)
    return data.reshape(nz, ny, nx).astype(np.float64), header


def read_mrc_2d(path: Path) -> Tuple[np.ndarray, bytes]:
    """Read a single-slice MRC as a 2-D array."""
    vol, header = read_mrc(path)
    if vol.shape[0] != 1:
        raise ValueError(f"expected a single-slice MRC, got nz={vol.shape[0]}: {path}")
    return vol[0], header


def write_mrc_2d(path: Path, image: np.ndarray, template_header: Optional[bytes] = None) -> None:
    """Write a 2-D float32 MRC, reusing a template header where one is supplied.

    Statistics fields (dmin/dmax/dmean/rms) are recomputed so that the written
    header is self-consistent with the perturbed payload.
    """
    img = np.asarray(image, dtype=np.float32)
    ny, nx = img.shape
    if template_header is not None:
        header = bytearray(template_header)
        struct.pack_into("<i", header, 92, 0)  # drop any extended header
    else:
        header = bytearray(1024)
        struct.pack_into("<3i", header, 16, nx, ny, 1)          # mx, my, mz
        struct.pack_into("<3f", header, 28, float(nx), float(ny), 1.0)  # cella
        struct.pack_into("<3f", header, 40, 90.0, 90.0, 90.0)   # cellb
        struct.pack_into("<3i", header, 52, 1, 2, 3)            # mapc, mapr, maps
        header[208:212] = b"MAP "
        struct.pack_into("<i", header, 212, 0x00004144)         # little-endian stamp
    struct.pack_into("<4i", header, 0, nx, ny, 1, 2)
    struct.pack_into("<3f", header, 76, float(img.min()), float(img.max()), float(img.mean()))
    struct.pack_into("<f", header, 216, float(img.std()))
    Path(path).write_bytes(bytes(header) + img.tobytes())


# ---------------------------------------------------------------------------
# STAR
# ---------------------------------------------------------------------------

def parse_star(path: Path) -> Dict[str, Dict[str, Any]]:
    """Parse a RELION STAR file into {block_name: {'pairs': {...}, 'labels': [...], 'rows': [[...]]}}."""
    blocks: Dict[str, Dict[str, Any]] = {}
    current: Optional[str] = None
    labels: List[str] = []
    rows: List[List[str]] = []
    pairs: Dict[str, str] = {}
    in_loop = False
    reading_labels = False

    def flush() -> None:
        if current is not None:
            blocks[current] = {"pairs": dict(pairs), "labels": list(labels), "rows": [list(r) for r in rows]}

    for line in Path(path).read_text(errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("data_"):
            flush()
            current = s[len("data_"):]
            labels, rows, pairs = [], [], {}
            in_loop = reading_labels = False
            continue
        if current is None:
            continue
        if s.startswith("loop_"):
            in_loop = True
            reading_labels = True
            labels, rows = [], []
            continue
        if s.startswith("_"):
            if in_loop and reading_labels:
                labels.append(s.split()[0])
            else:
                parts = s.split(None, 1)
                pairs[parts[0]] = parts[1].strip() if len(parts) > 1 else ""
            continue
        if in_loop:
            reading_labels = False
            rows.append(s.split())
    flush()
    return blocks


def global_shifts(blocks: Dict[str, Dict[str, Any]]) -> np.ndarray:
    """Return an (n_frames, 3) array of [frame, shift_x, shift_y], frame 1-indexed."""
    blk = blocks.get("global_shift")
    if blk is None:
        raise KeyError("no data_global_shift block in STAR file")
    labels = blk["labels"]
    i_f = labels.index("_rlnMicrographFrameNumber")
    i_x = labels.index("_rlnMicrographShiftX")
    i_y = labels.index("_rlnMicrographShiftY")
    out = np.array(
        [[float(r[i_f]), float(r[i_x]), float(r[i_y])] for r in blk["rows"]], dtype=np.float64
    )
    return out[np.argsort(out[:, 0])]


def motion_coeffs(blocks: Dict[str, Dict[str, Any]]) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Return (coeffX, coeffY), each length 18, or None if no local model is present."""
    blk = blocks.get("local_motion_model")
    if blk is None:
        return None
    labels = blk["labels"]
    i_idx = labels.index("_rlnMotionModelCoeffsIdx")
    i_val = labels.index("_rlnMotionModelCoeff")
    coeffs = np.zeros(2 * NUM_COEFFS_PER_DIM, dtype=np.float64)
    seen = np.zeros(2 * NUM_COEFFS_PER_DIM, dtype=bool)
    for row in blk["rows"]:
        idx = int(row[i_idx])
        if 0 <= idx < coeffs.size:
            coeffs[idx] = float(row[i_val])
            seen[idx] = True
    if not seen.all():
        raise ValueError("incomplete third-order polynomial motion model in STAR file")
    return coeffs[:NUM_COEFFS_PER_DIM], coeffs[NUM_COEFFS_PER_DIM:]


def _poly_basis(z: np.ndarray, xn: np.ndarray, yn: np.ndarray) -> np.ndarray:
    """The 18 basis terms of ThirdOrderPolynomialModel, in source order.

    Mirrors src/micrograph_model.cpp:32-50 term for term.
    """
    z2 = z * z
    z3 = z2 * z
    x2 = xn * xn
    y2 = yn * yn
    xy = xn * yn
    ones = np.ones_like(z)
    return np.stack(
        [
            z * ones, z2 * ones, z3 * ones,
            z * xn, z2 * xn, z3 * xn,
            z * x2, z2 * x2, z3 * x2,
            z * yn, z2 * yn, z3 * yn,
            z * y2, z2 * y2, z3 * y2,
            z * xy, z2 * xy, z3 * xy,
        ],
        axis=-1,
    )


def displacement_field(
    star_path: Path,
    grid_nx: int = 9,
    grid_ny: int = 9,
) -> Dict[str, Any]:
    """Evaluate the total applied displacement field on a regular detector grid.

    Returns a dict with ``field`` of shape (n_frames, grid_ny, grid_nx, 2) in
    pixels, plus the frame axis and the grid positions in detector pixels.

    Conventions, copied from src/micrograph_model.cpp:360-405:
      * frame numbers are 1-indexed;
      * the polynomial variable is ``z = frame - first_frame``;
      * normalised coordinates are ``xn = x/width - 0.5``, ``yn = y/height - 0.5``;
      * the total displacement is the global shift plus the polynomial term.
    """
    blocks = parse_star(star_path)
    gen = blocks.get("general", {}).get("pairs", {})
    width = int(float(gen.get("_rlnImageSizeX", 0)))
    height = int(float(gen.get("_rlnImageSizeY", 0)))
    if width <= 0 or height <= 0:
        raise ValueError(f"missing image size in {star_path}")
    first_frame = int(float(gen.get("_rlnMicrographStartFrame", 1)))

    gs = global_shifts(blocks)
    frames = gs[:, 0]
    coeffs = motion_coeffs(blocks)

    xs = np.linspace(0.0, width - 1.0, grid_nx)
    ys = np.linspace(0.0, height - 1.0, grid_ny)
    xg, yg = np.meshgrid(xs, ys, indexing="xy")
    xn = xg / width - 0.5
    yn = yg / height - 0.5

    n_f = frames.size
    field = np.zeros((n_f, grid_ny, grid_nx, 2), dtype=np.float64)
    for i, f in enumerate(frames):
        field[i, :, :, 0] = gs[i, 1]
        field[i, :, :, 1] = gs[i, 2]
        if coeffs is not None:
            z = np.full_like(xn, f - first_frame)
            basis = _poly_basis(z, xn, yn)
            field[i, :, :, 0] += basis @ coeffs[0]
            field[i, :, :, 1] += basis @ coeffs[1]

    return {
        "field": field,
        "frames": frames,
        "grid_x": xs,
        "grid_y": ys,
        "width": width,
        "height": height,
        "first_frame": first_frame,
        "has_local_model": coeffs is not None,
    }
