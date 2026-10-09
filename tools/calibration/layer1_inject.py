#!/usr/bin/env python3
"""Layer 1: inject exactly parameterised faults into real corrected micrographs.

Takes a reference corrected MRC produced by the real pipeline, applies each
prespecified fault at each prespecified severity, and scores every diagnostic.

What this layer establishes: how each diagnostic responds to a fault of known
physical magnitude, on realistic micrograph statistics, with no pipeline noise
at all -- the reference and the perturbed image differ by exactly the injected
fault and nothing else.

What it cannot establish: the shift-averaging faults (X2, X3, X4) here blur the
already-summed noise as well as the signal, which the real pipeline does not
do. Layer 2 measures that bias.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.calibration import diagnostics as dg           # noqa: E402
from tools.calibration import mrcio                        # noqa: E402
from tools.calibration import perturbations as pt          # noqa: E402
from tools.calibration.prespecification import (           # noqa: E402
    N_FRAMES,
    PIXEL_SIZE_A,
    SEVERITY_GRIDS,
    X4_CORRELATION_LENGTHS,
    split_grid,
)

#: Per-cell RNG seed base. Fixed so every cell is reproducible from its id.
SEED_BASE = 20260925


def cells(movie: str) -> Iterator[Dict[str, Any]]:
    """Enumerate every layer-1 cell for one movie, tagged selection or hold-out."""
    yield {"fault": "H4_null", "severity": 0.0, "split": "control", "extra": {}}
    for fault in ("X1_translation_px", "X2_jitter_sigma_px", "X3_drift_total_px",
                  "X5_applied_delta_b_a2", "X7_hot_pixel_count"):
        parts = split_grid(fault)
        for split, values in parts.items():
            for s in values:
                yield {"fault": fault, "severity": float(s), "split": split, "extra": {}}
    parts = split_grid("X4_localfield_rms_px")
    for split, values in parts.items():
        for s in values:
            for cl in X4_CORRELATION_LENGTHS:
                yield {"fault": "X4_localfield_rms_px", "severity": float(s),
                       "split": split, "extra": {"correlation_fraction": cl}}


def run_movie(movie: str, mrc_path: Path, pixel_size_a: float, border_px: int) -> List[Dict[str, Any]]:
    ref, _ = mrcio.read_mrc_2d(mrc_path)
    out: List[Dict[str, Any]] = []
    for i, cell in enumerate(cells(movie)):
        rng = np.random.default_rng(SEED_BASE + 1009 * i + sum(map(ord, movie)))
        ctx = {
            "n_frames": N_FRAMES,
            "rng": rng,
            "pixel_size_a": pixel_size_a,
            **cell["extra"],
        }
        if cell["fault"] == "H4_null":
            test = ref.copy()
        else:
            test = pt.LAYER1_OPERATORS[cell["fault"]](ref, cell["severity"], ctx)
        rec: Dict[str, Any] = {
            "layer": "L1",
            "movie": movie,
            "fault": cell["fault"],
            "severity": cell["severity"],
            "split": cell["split"],
            "unit": pt.UNITS.get(cell["fault"], ""),
            **cell["extra"],
        }
        rec.update(dg.all_image_diagnostics(ref, test, pixel_size_a, border_px))
        out.append(rec)
        print(f"  {movie} {cell['fault']}={cell['severity']:g} "
              f"{cell['extra'] or ''} relRMSE={rec['image_relative_rmse']:.4e} "
              f"dB={rec['std_delta_b_a2']:+.3f} shift={rec['std_shift_px']:.4f} "
              f"eps={rec['std_eps_incoherent']:.3e}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference", action="append", required=True,
                    metavar="MOVIE=PATH", help="reference corrected MRC per movie")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pixel-size", type=float, default=PIXEL_SIZE_A)
    ap.add_argument("--border-px", type=int, default=100)
    args = ap.parse_args()

    records: List[Dict[str, Any]] = []
    for spec in args.reference:
        movie, _, path = spec.partition("=")
        print(f"[layer1] {movie}", flush=True)
        records.extend(run_movie(movie, Path(path), args.pixel_size, args.border_px))
    args.out.write_text(json.dumps({"records": records,
                                    "grids": {k: list(v) for k, v in SEVERITY_GRIDS.items()}},
                                   indent=2))
    print(f"wrote {args.out} with {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
