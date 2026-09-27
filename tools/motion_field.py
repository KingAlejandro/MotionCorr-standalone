#!/usr/bin/env python3
"""Read a MotionCorr per-micrograph motion STAR file and evaluate the displacement field it
describes, plus a faithful Python re-implementation of the corrector that applies it.

This is a port of:
  * ``Micrograph::getShiftAt``                                 (src/micrograph_model.cpp)
  * ``ThirdOrderPolynomialModel::getShiftAt``                  (src/micrograph_model.cpp)
  * ``MotioncorrRunner::shiftNonSquareImageInFourierTransform``(src/motioncorr_runner.cpp)
  * ``MotioncorrRunner::realSpaceInterpolation_ThirdOrderPolynomial``

Conventions (see agents/designs/issue_59_known_motion_local_field_gates.md):
  frame is 1-based in the STAR; z = frame - rlnMicrographStartFrame
  u = ix / nx - 0.5, v = iy / ny - 0.5     (nx for x, ny for y -- not interchangeable)
  field = globalShift[frame] + polynomial(z, u, v), in pixels of the unbinned grid
  the field is the displacement applied to the frame content in order to correct it
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

NUM_COEFFS_PER_DIM = 18

# Spatial factor for each of the 6 coefficient groups, in the order used by the C++ model.
# Within a group the three coefficients multiply z, z^2, z^3.
SPATIAL_BASIS = ["1", "u", "u2", "v", "v2", "uv"]


# ---------------------------------------------------------------------------- STAR parsing --

def _tokenize_blocks(text: str) -> Dict[str, List[str]]:
    """Split a STAR file into ``data_<name> -> list of lines`` (comments stripped)."""
    blocks: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("data_"):
            current = stripped[len("data_"):]
            blocks[current] = []
            continue
        if current is None:
            continue
        blocks[current].append(raw)
    return blocks


def _parse_pairs(lines: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("loop_"):
            continue
        if not s.startswith("_"):
            continue
        parts = s.split()
        if len(parts) >= 2:
            out[parts[0][1:]] = parts[1]
    return out


def _parse_loop(lines: List[str]) -> List[Dict[str, str]]:
    cols: List[str] = []
    rows: List[Dict[str, str]] = []
    in_loop = False
    in_body = False
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("loop_"):
            in_loop, in_body, cols = True, False, []
            continue
        if not in_loop:
            continue
        if s.startswith("_"):
            if in_body:  # a second loop in the same block: not expected here
                break
            cols.append(re.split(r"\s+", s)[0][1:])
            continue
        in_body = True
        vals = re.split(r"\s+", s)
        if len(vals) != len(cols):
            continue
        rows.append(dict(zip(cols, vals)))
    return rows


@dataclass
class MotionStar:
    """The contents of a MotionCorr per-micrograph motion STAR file."""

    path: Path
    nx: int
    ny: int
    n_frames: int
    first_frame: int                 # rlnMicrographStartFrame, 1-based
    pixel_size: float                # rlnMicrographOriginalPixelSize, A/px
    binning: float
    motion_model_version: int
    global_shift_x: np.ndarray       # (n_frames,) px, NaN where not observed
    global_shift_y: np.ndarray
    coeff_x: Optional[np.ndarray] = None   # (18,) or None
    coeff_y: Optional[np.ndarray] = None
    hot_pixels: List = dc_field(default_factory=list)
    local_shifts: List[Dict[str, float]] = dc_field(default_factory=list)
    general: Dict[str, str] = dc_field(default_factory=dict)

    # ------------------------------------------------------------------ field evaluation --
    def local_field(self, frames, ix, iy):
        """Polynomial part only, px. frames: (F,) 1-based. ix, iy: (P,). Returns (F, P, 2)."""
        frames = np.atleast_1d(np.asarray(frames, dtype=np.float64))
        ix = np.atleast_1d(np.asarray(ix, dtype=np.float64))
        iy = np.atleast_1d(np.asarray(iy, dtype=np.float64))
        out = np.zeros((frames.size, ix.size, 2))
        if self.coeff_x is None:
            return out
        u = ix / self.nx - 0.5
        v = iy / self.ny - 0.5
        spatial = np.stack([np.ones_like(u), u, u * u, v, v * v, u * v], axis=0)  # (6, P)
        z = frames - self.first_frame
        temporal = np.stack([z, z * z, z * z * z], axis=0)                        # (3, F)
        for axis, coeff in ((0, self.coeff_x), (1, self.coeff_y)):
            acc = np.zeros((frames.size, ix.size))
            for g in range(6):
                block = coeff[3 * g:3 * g + 3]                                    # (3,)
                acc += np.einsum("t,tf,p->fp", block, temporal, spatial[g])
            out[:, :, axis] = acc
        return out

    def field(self, frames, ix, iy, use_local: bool = True):
        """Total applied field in px: global + local. Returns (F, P, 2)."""
        frames = np.atleast_1d(np.asarray(frames, dtype=np.float64))
        ix = np.atleast_1d(np.asarray(ix, dtype=np.float64))
        out = self.local_field(frames, ix, iy) if use_local else \
            np.zeros((frames.size, np.atleast_1d(ix).size, 2))
        idx = frames.astype(int) - 1
        out[:, :, 0] += self.global_shift_x[idx][:, None]
        out[:, :, 1] += self.global_shift_y[idx][:, None]
        return out

    def field_angstrom(self, frames, ix, iy, use_local: bool = True):
        return self.field(frames, ix, iy, use_local) * self.pixel_size

    @property
    def frames(self) -> np.ndarray:
        """1-based frame numbers present in the global shift table."""
        return np.arange(1, self.n_frames + 1)

    def copy(self) -> "MotionStar":
        import copy as _copy
        return _copy.deepcopy(self)


def read_motion_star(path) -> MotionStar:
    path = Path(path)
    blocks = _tokenize_blocks(path.read_text())
    if "general" not in blocks:
        raise ValueError(f"{path}: no data_general block; is this a MotionCorr motion STAR?")
    gen = _parse_pairs(blocks["general"])

    def _get(name, cast, default=None):
        if name not in gen:
            if default is None:
                raise ValueError(f"{path}: missing {name} in data_general")
            return default
        return cast(gen[name])

    nx = _get("rlnImageSizeX", int)
    ny = _get("rlnImageSizeY", int)
    n_frames = _get("rlnImageSizeZ", int)
    first_frame = _get("rlnMicrographStartFrame", int, 1)
    pixel_size = _get("rlnMicrographOriginalPixelSize", float, -1.0)
    binning = _get("rlnMicrographBinning", float, 1.0)
    version = _get("rlnMotionModelVersion", int, 0)

    gx = np.full(n_frames, np.nan)
    gy = np.full(n_frames, np.nan)
    for row in _parse_loop(blocks.get("global_shift", [])):
        f = int(row["rlnMicrographFrameNumber"])
        gx[f - 1] = float(row["rlnMicrographShiftX"])
        gy[f - 1] = float(row["rlnMicrographShiftY"])

    cx = cy = None
    if version == 1:
        cx = np.zeros(NUM_COEFFS_PER_DIM)
        cy = np.zeros(NUM_COEFFS_PER_DIM)
        seen = 0
        for row in _parse_loop(blocks.get("local_motion_model", [])):
            idx = int(row["rlnMotionModelCoeffsIdx"])
            val = float(row["rlnMotionModelCoeff"])
            if idx < NUM_COEFFS_PER_DIM:
                cx[idx] = val
            else:
                cy[idx - NUM_COEFFS_PER_DIM] = val
            seen += 1
        if seen != 2 * NUM_COEFFS_PER_DIM:
            raise ValueError(f"{path}: motion model version 1 but {seen} coefficients "
                             f"(expected {2 * NUM_COEFFS_PER_DIM})")

    hot = [(float(r["rlnCoordinateX"]), float(r["rlnCoordinateY"]))
           for r in _parse_loop(blocks.get("hot_pixels", []))]
    local = [{k: float(v) for k, v in r.items()} for r in _parse_loop(blocks.get("local_shift", []))]

    return MotionStar(path=path, nx=nx, ny=ny, n_frames=n_frames, first_frame=first_frame,
                      pixel_size=pixel_size, binning=binning, motion_model_version=version,
                      global_shift_x=gx, global_shift_y=gy, coeff_x=cx, coeff_y=cy,
                      hot_pixels=hot, local_shifts=local, general=gen)


def write_motion_star(star: MotionStar, path) -> None:
    """Re-emit a motion STAR with the current shifts/coefficients.

    Used only by the negative-control harness, to inject a known defect into a field that the
    program itself produced.
    """
    path = Path(path)
    lines = ["# version 50001", "", "data_general", ""]
    for key, val in star.general.items():
        lines.append(f"_{key:<40s} {val}")
    lines += [" ", "", "# version 50001", "", "data_global_shift", "", "loop_ ",
              "_rlnMicrographFrameNumber #1 ", "_rlnMicrographShiftX #2 ",
              "_rlnMicrographShiftY #3 "]
    for i in range(star.n_frames):
        # Full precision, unlike MotionCorr's own 6-significant-digit output: this file is read
        # back by the test harness, which injects perturbations as small as 1e-6 px, and a
        # 1e-6 px write granularity would sit on top of exactly the signal being measured.
        lines.append(f"{i + 1:12d} {star.global_shift_x[i]:.15e} {star.global_shift_y[i]:.15e} ")
    lines.append(" ")
    if star.motion_model_version == 1:
        lines += ["", "# version 50001", "", "data_local_motion_model", "", "loop_ ",
                  "_rlnMotionModelCoeffsIdx #1 ", "_rlnMotionModelCoeff #2 "]
        for i, c in enumerate(np.concatenate([star.coeff_x, star.coeff_y])):
            lines.append(f"{i:12d} {c:.12e} ")
        lines.append(" ")
    lines.append("")
    path.write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------------------ MRC I/O ----

def read_mrc(path):
    """Return (data, header_bytes). data is (nz, ny, nx) float32 for mode 0/2."""
    path = Path(path)
    raw = path.read_bytes()
    nx, ny, nz, mode = struct.unpack_from("<4i", raw, 0)
    nsymbt = struct.unpack_from("<i", raw, 92)[0]
    offset = 1024 + nsymbt
    dtype = {0: np.int8, 1: np.int16, 2: np.float32, 6: np.uint16, 12: np.float16}[mode]
    data = np.frombuffer(raw, dtype=dtype, count=nx * ny * nz, offset=offset)
    return data.reshape(nz, ny, nx).astype(np.float32), raw[:1024]


# ------------------------------------------------------- corrector re-implementation --------

def shift_frame_fourier(frame: np.ndarray, shift_x: float, shift_y: float) -> np.ndarray:
    """Displace image content by (+shift_x, +shift_y) px.

    Mirrors ``shiftNonSquareImageInFourierTransform(F, -shift_x/nx, -shift_y/ny)``, including
    its Nyquist-row convention: the C++ maps y -> y - ny only for ``y > ny/2`` (strict), so the
    row at exactly ny/2 keeps a positive index where ``np.fft.fftfreq`` would give a negative
    one. That differs in the sign of the sine term on a single row; it is reproduced here so
    that a comparison against the program measures the program, not this convention.
    """
    ny, nx = frame.shape
    F = np.fft.rfft2(frame.astype(np.float64))
    nfy, nfx = F.shape
    ly = np.arange(nfy)
    ly = np.where(ly > nfy // 2, ly - nfy, ly)
    lx = np.arange(nfx)
    phase = 2.0 * np.pi * (lx[None, :] * (-shift_x / nx) + ly[:, None] * (-shift_y / ny))
    F = F * (np.cos(phase) + 1j * np.sin(phase))
    return np.fft.irfft2(F, s=(ny, nx))


def apply_local_model(frame: np.ndarray, star: MotionStar, z: float) -> np.ndarray:
    """Bilinear resample at (ix - Lx, iy - Ly), matching realSpaceInterpolation_*.

    Border handling is the C++ behaviour: when the source coordinate leaves the array the
    output takes the clamped *source pixel* value with no interpolation.
    """
    ny, nx = frame.shape
    if star.coeff_x is None:
        return frame.copy()
    iy_i, ix_i = np.mgrid[0:ny, 0:nx]
    u = ix_i / nx - 0.5
    v = iy_i / ny - 0.5
    z2, z3 = z * z, z * z * z
    cxs, cys = star.coeff_x, star.coeff_y

    def poly(c):
        t = np.array([z, z2, z3])
        g = [c[3 * k:3 * k + 3] @ t for k in range(6)]
        return g[0] + g[1] * u + g[2] * u * u + g[3] * v + g[4] * v * v + g[5] * u * v

    xf = ix_i - poly(cxs)
    yf = iy_i - poly(cys)

    x0 = np.floor(xf).astype(np.int64)
    y0 = np.floor(yf).astype(np.int64)
    x1, y1 = x0 + 1, y0 + 1
    valid = np.ones(frame.shape, dtype=bool)
    bad = (x0 < 0) | (x1 < 0)
    x0 = np.where(bad, 0, x0); valid &= ~bad
    bad = (y0 < 0) | (y1 < 0)
    y0 = np.where(bad, 0, y0); valid &= ~bad
    bad = (x1 >= nx) | (x0 >= nx - 1)
    x0 = np.where(bad, nx - 1, x0); valid &= ~bad
    bad = (y1 >= ny) | (y0 >= ny - 1)
    y0 = np.where(bad, ny - 1, y0); valid &= ~bad

    x0c = np.clip(x0, 0, nx - 2)
    y0c = np.clip(y0, 0, ny - 2)
    fx = xf - x0c
    fy = yf - y0c
    d00 = frame[y0c, x0c]
    d01 = frame[y0c, x0c + 1]
    d10 = frame[y0c + 1, x0c]
    d11 = frame[y0c + 1, x0c + 1]
    dx0 = d00 + fx * (d01 - d00)
    dx1 = d10 + fx * (d11 - d10)
    interp = dx0 + fy * (dx1 - dx0)
    return np.where(valid, interp, frame[np.clip(y0, 0, ny - 1), np.clip(x0, 0, nx - 1)])


def reapply_field(movie: np.ndarray, star: MotionStar) -> np.ndarray:
    """Correct `movie` (n_frames, ny, nx) with the field in `star` and return the summed image.

    This is the independent witness that ties the reported field to the corrected pixels.
    """
    n = movie.shape[0]
    acc = np.zeros(movie.shape[1:], dtype=np.float64)
    for i in range(n):
        f = i + 1
        g = shift_frame_fourier(movie[i], star.global_shift_x[i], star.global_shift_y[i])
        acc += apply_local_model(g, star, f - star.first_frame)
    return acc
