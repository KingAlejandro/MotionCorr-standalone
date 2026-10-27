#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Truth-free bridge: runtime-model tap (MC_DIAG_MODEL_OUT) -> dense F,Y,X,2 field in detector px.

The tap is the JSON written by the experiment build after local fitting: runtime global shifts,
the 18+18 third-order polynomial coefficients and ``local_enabled``. The bridge needs the movie
geometry (nx, ny, frames) from the pinned fixture/config and nothing else: no truth, no fit and no
receipt. The field equation is the existing ``check_realistic_motion.runtime_field`` (spatial groups
[1,u,u^2,v,v^2,uv], each multiplying [z,z^2,z^3], z = frame index, u = x/nx-.5, v = y/ny-.5, plus
the global shift), the same equation as ``ThirdOrderPolynomialModel::getShiftAt`` and
``motion_field.MotionStar``. The result feeds the unchanged ``check_motion_diagnostics`` ``--candidate``.

    python3 ccf_dc_tap_field.py --tap tap.json --nx 128 --ny 96 --frames 5 --out field.npy
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_realistic_motion import runtime_field  # existing field equation, no receipt wrapper

TAP_KEYS = {"global", "coeff_x", "coeff_y", "local_enabled"}


class TapError(ValueError):
    """The tap is missing, incomplete, malformed, non-finite or inconsistent."""


def load_tap(path, frames):
    """Strict schema. A placeholder (``{"status":"incomplete"}``) or any extra/missing key is refused."""
    try:
        tap = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise TapError(f"unreadable tap: {e}")
    if not isinstance(tap, dict) or set(tap) != TAP_KEYS:
        raise TapError(f"tap keys {sorted(tap) if isinstance(tap, dict) else type(tap).__name__} != {sorted(TAP_KEYS)}")
    if not isinstance(tap["local_enabled"], bool):
        raise TapError("local_enabled is not a boolean")
    g = tap["global"]
    if (not isinstance(g, list) or len(g) != frames or
            any(not isinstance(p, list) or len(p) != 2 for p in g)):
        raise TapError(f"global is not {frames} x 2")
    for key in ("coeff_x", "coeff_y"):
        if not isinstance(tap[key], list) or len(tap[key]) != 18:
            raise TapError(f"{key} does not have 18 entries")
    for v in [x for p in g for x in p] + tap["coeff_x"] + tap["coeff_y"]:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise TapError("non-finite or non-numeric tap value")
    if not tap["local_enabled"] and any(v != 0 for v in tap["coeff_x"] + tap["coeff_y"]):
        raise TapError("local_enabled is false but local coefficients are nonzero")
    return tap


def dense_field(tap, nx, ny, frames):
    """(frames, ny, nx, 2) float64 displacement field in px, grid as ``generate_motion_diagnostics.grid``."""
    if nx <= 0 or ny <= 0 or frames <= 0:
        raise TapError("nonpositive geometry")
    yy, xx = np.mgrid[:ny, :nx]
    field = runtime_field(tap, dict(nx=nx, ny=ny, frames=frames), xx.ravel().astype(float), yy.ravel().astype(float))
    return field.reshape(frames, ny, nx, 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tap", type=Path, required=True)
    ap.add_argument("--nx", type=int, required=True)
    ap.add_argument("--ny", type=int, required=True)
    ap.add_argument("--frames", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"refusing to overwrite {a.out}")
    np.save(a.out, dense_field(load_tap(a.tap, a.frames), a.nx, a.ny, a.frames), allow_pickle=False)


if __name__ == "__main__":
    main()
