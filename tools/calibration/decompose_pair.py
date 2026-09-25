#!/usr/bin/env python3
"""Apply the transfer decomposition to any pair of corrected micrographs.

A small read-only utility so an existing backend comparison can be re-read in
calibrated terms -- scale, translation, envelope loss and incoherent residual
-- without re-running the backend, and without touching the comparator or any
recorded gate result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.calibration import diagnostics as dg   # noqa: E402
from tools.calibration import mrcio               # noqa: E402
from tools.calibration.prespecification import PIXEL_SIZE_A, amplitude_loss  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pair", action="append", required=True,
                    metavar="LABEL=REF_MRC:TEST_MRC")
    ap.add_argument("--ref-star", action="append", default=[], metavar="LABEL=PATH")
    ap.add_argument("--test-star", action="append", default=[], metavar="LABEL=PATH")
    ap.add_argument("--pixel-size", type=float, default=PIXEL_SIZE_A)
    ap.add_argument("--border-px", type=int, default=100)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    ref_stars = dict(s.split("=", 1) for s in args.ref_star)
    test_stars = dict(s.split("=", 1) for s in args.test_star)

    out = []
    for spec in args.pair:
        label, _, paths = spec.partition("=")
        ref_p, _, test_p = paths.partition(":")
        ref, _ = mrcio.read_mrc_2d(Path(ref_p))
        test, _ = mrcio.read_mrc_2d(Path(test_p))
        rec = {"label": label, "ref": ref_p, "test": test_p}
        rec.update(dg.all_image_diagnostics(ref, test, args.pixel_size, args.border_px))
        if label in ref_stars and label in test_stars:
            try:
                rec.update(dg.existing_trajectory_metrics(
                    mrcio.global_shifts(mrcio.parse_star(Path(ref_stars[label]))),
                    mrcio.global_shifts(mrcio.parse_star(Path(test_stars[label])))))
                rec.update(dg.field_metrics(Path(ref_stars[label]), Path(test_stars[label]), grid=9))
            except Exception as exc:
                rec["star_error"] = str(exc)
        rec["amplitude_loss_at_3A"] = amplitude_loss(max(rec["std_delta_b_a2"], 0.0), 3.0)
        out.append(rec)
        print(f"{label}:")
        print(f"  relative RMSE      {rec['image_relative_rmse']:.6f}")
        print(f"  absolute RMSE      {rec['image_rmse']:.6f}")
        print(f"  max pixel error    {rec['image_max_abs_error']:.4f}")
        print(f"  scale deviation    {rec['std_scale_dev']:.3e}")
        print(f"  translation        {rec['std_shift_px']:.5f} px "
              f"({rec['std_shift_a']:.5f} A)")
        print(f"  envelope loss      {rec['std_delta_b_a2']:+.4f} A^2 "
              f"(R2={rec['std_fit_r2']:.4f}) -> "
              f"{100*rec['amplitude_loss_at_3A']:.2f}% amplitude loss at 3 A")
        print(f"  incoherent residual {rec['std_eps_incoherent']:.6f} "
              f"(explains {100*rec['std_eps_explained_fraction']:.1f}% of the raw "
              f"difference {rec['std_eps_undecomposed']:.6f})")
        print(f"  bands  low {rec['rel_rmse_low']:.5f}  mid {rec['rel_rmse_mid']:.5f}  "
              f"high {rec['rel_rmse_high']:.5f}")
        print(f"  regions interior {rec['rel_rmse_interior']:.5f}  "
              f"border {rec['rel_rmse_border']:.5f}  "
              f"ratio {rec['border_interior_ratio']:.3f}")
        if "field_rms_px" in rec:
            print(f"  displacement field rms {rec['field_rms_px']:.5f} px "
                  f"({rec['field_rms_a']:.5f} A), interframe rms "
                  f"{rec['field_interframe_rms_px']:.5f} px, "
                  f"const offset {rec['field_const_offset_px']:.5f} px, "
                  f"max {rec['field_max_px']:.5f} px")
        print()
    if args.out:
        args.out.write_text(json.dumps({"records": out}, indent=2))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
