#!/usr/bin/env python3
"""Known-motion gate: compare the displacement field MotionCorr applied against injected truth.

This is a *separate* check from ``tools/compare_motioncorr.py``. That tool compares a run to a
reference run; this one compares a run to a synthetic ground truth, and it compares the applied
displacement field across positions and frames rather than only corrected pixels.

Design, conventions and threshold derivation:
    agents/designs/issue_59_known_motion_local_field_gates.md

Exit status: 0 if every gated metric passes, 1 otherwise, 2 on a usage or input error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import motion_field as mf  # noqa: E402

# --------------------------------------------------------------------------- thresholds ----
# Declared in the design record before any fixture was generated. Derived from the amplitude
# envelope of a residual displacement error: for an isotropic 2D RMS magnitude sigma, the
# envelope at resolution d is exp(-pi^2 sigma^2 / d^2), i.e. an equivalent B of 4 pi^2 sigma^2.
# Evaluated at a 3 A target:  0.05 A -> 0.27 %,  0.10 A -> 1.1 %,  0.20 A -> 4.3 %,
#                             0.40 A -> 16.1 % amplitude loss.
# No value here was derived from, or tuned against, the 24 tutorial movies.
TARGET_RESOLUTION_A = 3.0

THRESHOLDS_ANGSTROM = {
    "global_component_rms": 0.10,     # tier B
    "local_component_rms": 0.20,      # tier C
    "total_rms": 0.20,                # tier C
    "total_p95": 0.40,                # tier D
    "total_max": 0.80,                # 2 x tier D, outlier alarm
    "frame_to_frame_rms": 0.20,       # tier C
}
# Tightened from the 1.0 px declared in the design record to tier B (Amendment 2). The mean
# error c is not a free gauge: both truth and recovery are anchored at the first summed frame,
# so E(first) == 0 identically and c is algebraically tied to the other frames' errors. An error
# that is constant across frames 1..N-1 shows up as c*(N-1)/N, and removing c before computing
# the scatter shrinks it by a factor of about N/sqrt(N-1) -- for 12 frames, 3.6x. At the old
# 1.0 px limit a genuine 0.25 px per-frame bias could pass every gate. Tightening to the same
# tier as the global component closes that; it is strictly stricter than declared.
CONSTANT_OFFSET_LIMIT_ANGSTROM = 0.10

# The reconstruction residual below this relative RMSE is arithmetic noise (float32 FFT versus
# float64 reference), not a field defect. Measured, not assumed: see the response curve in
# docs/known_motion_validation.md.
NUMERICAL_NOISE_RELATIVE_RMSE = 1.0e-4


def amplitude_loss(sigma_a: float, d: float = TARGET_RESOLUTION_A) -> float:
    """Fractional amplitude loss at resolution d from a residual with 2D RMS magnitude sigma."""
    return 1.0 - math.exp(-(math.pi ** 2) * sigma_a * sigma_a / (d * d))


def equivalent_bfactor(sigma_a: float) -> float:
    return 4.0 * math.pi ** 2 * sigma_a * sigma_a


# ------------------------------------------------------------------------------ metrics ----

def _stats(vec: np.ndarray, pixel_size: float) -> dict:
    """vec: (..., 2) displacement errors in px. Returns RMS / P95 / max of the magnitude."""
    if vec.size == 0:
        return {"n": 0, "rms_px": None, "p95_px": None, "max_px": None,
                "rms_a": None, "p95_a": None, "max_a": None}
    mag = np.linalg.norm(vec.reshape(-1, 2), axis=1)
    rms = float(np.sqrt(np.mean(mag ** 2)))
    p95 = float(np.percentile(mag, 95))
    mx = float(mag.max())
    return {"n": int(mag.size),
            "rms_px": rms, "p95_px": p95, "max_px": mx,
            "rms_a": rms * pixel_size, "p95_a": p95 * pixel_size, "max_a": mx * pixel_size}


def evaluate(gt: dict, star: mf.MotionStar) -> dict:
    """Compute every field metric. No thresholds are applied here."""
    geo = gt["geometry"]
    px = geo["pixel_size_angstrom"]
    grid_x = np.asarray(gt["grid"]["x"], dtype=float)
    grid_y = np.asarray(gt["grid"]["y"], dtype=float)
    truth = np.asarray(gt["expected_applied_field"], dtype=float)   # (F, P, 2) px

    problems = []
    if (star.nx, star.ny) != (geo["nx"], geo["ny"]):
        problems.append(f"output geometry {star.nx}x{star.ny} != fixture {geo['nx']}x{geo['ny']}")
    if star.n_frames != geo["n_frames"]:
        problems.append(f"output has {star.n_frames} frames, fixture has {geo['n_frames']}")
    if abs(star.pixel_size - px) > 1e-9:
        problems.append(f"output pixel size {star.pixel_size} != fixture {px}")
    if not np.isfinite(star.global_shift_x).all():
        problems.append("output global shift table has unobserved frames")

    frames = np.arange(1, star.n_frames + 1)
    recovered = star.field(frames, grid_x, grid_y)                  # (F, P, 2) px

    # Temporal gauge: motion is only defined relative to a reference frame. Both truth and
    # recovery are already anchored at the first summed frame (truth by construction, recovery
    # because MotionCorr zeroes frame 0 and the polynomial has no constant-in-z term), but
    # anchor explicitly so the comparison does not depend on that holding.
    truth_a = truth - truth[0][None, :, :]
    recov_a = recovered - recovered[0][None, :, :]

    err = recov_a - truth_a                                         # (F, P, 2) px

    # 1. constant offset, reported on its own
    offset = err.reshape(-1, 2).mean(axis=0)
    err_c = err - offset[None, None, :]

    # 2/3/4. decomposition
    global_comp = err_c.mean(axis=1)                                # (F, 2)
    local_comp = err_c - global_comp[:, None, :]                    # (F, P, 2)

    # 5. frame-to-frame change
    d_ft = np.diff(err_c, axis=0)

    # interior vs border, from the interpolation-clamped margin of the *recovered* field
    margin = float(np.ceil(np.abs(recovered).max()) + 2.0)
    border_pos = ((grid_x < margin) | (grid_x > star.nx - 1 - margin) |
                  (grid_y < margin) | (grid_y > star.ny - 1 - margin))
    interior_pos = ~border_pos
    n_border_px = (star.nx * star.ny
                   - max(0, star.nx - 2 * int(margin)) * max(0, star.ny - 2 * int(margin)))

    per_frame = []
    for i, f in enumerate(frames):
        per_frame.append({
            "frame": int(f),
            "z": float(f - star.first_frame),
            "global_shift_px": [float(star.global_shift_x[i]), float(star.global_shift_y[i])],
            "truth_mean_field_px": [float(truth_a[i, :, 0].mean()),
                                    float(truth_a[i, :, 1].mean())],
            "recovered_mean_field_px": [float(recov_a[i, :, 0].mean()),
                                        float(recov_a[i, :, 1].mean())],
            "error_all": _stats(err_c[i], px),
            "error_interior": _stats(err_c[i][interior_pos], px),
            "error_border": _stats(err_c[i][border_pos], px),
            "global_component_px": [float(global_comp[i, 0]), float(global_comp[i, 1])],
            "local_component": _stats(local_comp[i][interior_pos], px),
        })

    return {
        "geometry": {"nx": star.nx, "ny": star.ny, "n_frames": star.n_frames,
                     "first_frame": star.first_frame, "pixel_size_angstrom": px,
                     "motion_model_version": star.motion_model_version},
        "problems": problems,
        "grid": {"n_positions": int(grid_x.size),
                 "n_interior": int(interior_pos.sum()), "n_border": int(border_pos.sum())},
        "truth_field_span_px": {
            "max_abs": float(np.abs(truth_a).max()),
            "max_local_deviation": float(np.abs(
                truth_a - truth_a.mean(axis=1)[:, None, :]).max()),
        },
        "constant_offset": {
            "x_px": float(offset[0]), "y_px": float(offset[1]),
            "magnitude_px": float(np.linalg.norm(offset)),
            "magnitude_a": float(np.linalg.norm(offset) * px),
            "note": "a field wrong by a constant in both frame and position is a rigid "
                    "translation of the micrograph; reported separately, never folded in",
        },
        "total_offset_removed": {
            "all": _stats(err_c, px),
            "interior": _stats(err_c[:, interior_pos], px),
            "border": _stats(err_c[:, border_pos], px),
        },
        # Reported, not gated: the same statistics with the mean error left in, so a reader can
        # see the whole error without reconstructing it from the decomposition.
        "total_including_offset": {
            "all": _stats(err, px),
            "interior": _stats(err[:, interior_pos], px),
            "border": _stats(err[:, border_pos], px),
        },
        "global_component": _stats(global_comp, px),
        "local_component": {
            "interior": _stats(local_comp[:, interior_pos], px),
            "border": _stats(local_comp[:, border_pos], px),
        },
        "frame_to_frame": {
            "interior": _stats(d_ft[:, interior_pos], px),
            "all": _stats(d_ft, px),
        },
        "interpolation_boundary": {
            "unfaithful_margin_px": margin,
            "rule": "ceil(max|applied field|) + 2; inside it the corrector clamps to the edge "
                    "pixel instead of interpolating (realSpaceInterpolation_*)",
            "affected_output_pixels": int(n_border_px),
            "affected_fraction": float(n_border_px / (star.nx * star.ny)),
            "cropped": False,
        },
        "per_frame": per_frame,
    }


def apply_gates(metrics: dict) -> dict:
    px = metrics["geometry"]["pixel_size_angstrom"]
    checks = []

    def add(name, value_a, limit_a, gated=True, note=""):
        passed = (value_a is not None) and (value_a <= limit_a)
        checks.append({
            "name": name, "gated": gated,
            "value_a": value_a, "value_px": None if value_a is None else value_a / px,
            "limit_a": limit_a, "limit_px": limit_a / px,
            "amplitude_loss_at_3A": None if value_a is None else amplitude_loss(value_a),
            "equivalent_bfactor_a2": None if value_a is None else equivalent_bfactor(value_a),
            "pass": bool(passed), "note": note,
        })

    t = THRESHOLDS_ANGSTROM
    interior = metrics["total_offset_removed"]["interior"]
    add("global_component_rms", metrics["global_component"]["rms_a"], t["global_component_rms"])
    add("local_component_rms", metrics["local_component"]["interior"]["rms_a"],
        t["local_component_rms"])
    add("total_rms_interior", interior["rms_a"], t["total_rms"])
    add("total_p95_interior", interior["p95_a"], t["total_p95"])
    add("total_max_interior", interior["max_a"], t["total_max"])
    add("frame_to_frame_rms_interior", metrics["frame_to_frame"]["interior"]["rms_a"],
        t["frame_to_frame_rms"])

    offset_a = metrics["constant_offset"]["magnitude_a"]
    add("constant_offset", offset_a, CONSTANT_OFFSET_LIMIT_ANGSTROM,
        note="mean error over frames and positions; reported separately so it never inflates "
             "the scatter statistics, and gated because it is not a free gauge")

    tot_inc = metrics["total_including_offset"]["interior"]
    checks.append({
        "name": "total_rms_interior_with_offset", "gated": False,
        "value_a": tot_inc["rms_a"], "value_px": tot_inc["rms_px"],
        "limit_a": None, "limit_px": None,
        "amplitude_loss_at_3A": None if tot_inc["rms_a"] is None else amplitude_loss(tot_inc["rms_a"]),
        "equivalent_bfactor_a2": None, "pass": True,
        "note": "the same error with the mean left in; reported so nothing is hidden by the "
                "offset/scatter split",
    })

    border = metrics["total_offset_removed"]["border"]
    checks.append({
        "name": "border_rms_reported_not_gated", "gated": False,
        "value_a": border["rms_a"], "value_px": None if border["rms_a"] is None else border["rms_px"],
        "limit_a": None, "limit_px": None,
        "amplitude_loss_at_3A": None, "equivalent_bfactor_a2": None,
        "pass": True,
        "note": "pixels inside the interpolation-clamped margin are knowingly unfaithful; "
                "reported, not gated, and never cropped away",
    })

    gated = [c for c in checks if c["gated"]]
    return {"checks": checks,
            "n_gated": len(gated),
            "n_failed": sum(1 for c in gated if not c["pass"]),
            "status": "PASS" if all(c["pass"] for c in gated) else "FAIL"}


# --------------------------------------------------------------- applied-field witness -----

def self_consistency(movie_path: Path, star: mf.MotionStar, produced_sum: Path) -> dict:
    """Re-apply the reported field to the raw movie and compare with the program's own sum.

    A STAR-only check proves what the program *reported*. This proves what it *applied*.
    """
    movie, _ = mf.read_mrc(movie_path)
    got, _ = mf.read_mrc(produced_sum)
    got = got[0].astype(np.float64)
    recon = mf.reapply_field(movie.astype(np.float64), star)
    diff = recon - got
    ref_rms = float(np.sqrt(np.mean(got ** 2)))
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    return {
        "reference_rms": ref_rms,
        "absolute_rmse": rmse,
        "relative_rmse": rmse / ref_rms if ref_rms > 0 else None,
        "max_abs_error": float(np.abs(diff).max()),
        "noise_floor_relative_rmse": NUMERICAL_NOISE_RELATIVE_RMSE,
        "classification": ("numerical_noise" if ref_rms > 0 and
                           rmse / ref_rms <= NUMERICAL_NOISE_RELATIVE_RMSE else "field_defect"),
        "note": "float32 FFT arithmetic in the program versus float64 here; a disagreement at "
                "or below the measured floor is rounding, not a displacement-field error",
    }


# ---------------------------------------------------------------------------- reporting ----

def _fmt(v, width=11, prec=6):
    return " " * width if v is None else f"{v:{width}.{prec}f}"


def print_report(report: dict) -> None:
    m = report["metrics"]
    g = report["gates"]
    px = m["geometry"]["pixel_size_angstrom"]
    print("=" * 78)
    print(" KNOWN-MOTION AND LOCAL-FIELD GATE")
    print("=" * 78)
    print(f"Case:            {report['case']}")
    print(f"Motion STAR:     {report['motion_star']}")
    print(f"Geometry:        {m['geometry']['nx']} x {m['geometry']['ny']} px, "
          f"{m['geometry']['n_frames']} frames, {px} A/px, "
          f"motion model version {m['geometry']['motion_model_version']}")
    print(f"Grid:            {m['grid']['n_positions']} positions "
          f"({m['grid']['n_interior']} interior, {m['grid']['n_border']} border)")
    print(f"Injected field:  max |field| = {m['truth_field_span_px']['max_abs']:.4f} px, "
          f"max local deviation = {m['truth_field_span_px']['max_local_deviation']:.4f} px")
    if m["problems"]:
        print("\n!! STRUCTURAL PROBLEMS")
        for p in m["problems"]:
            print(f"   - {p}")

    co = m["constant_offset"]
    print("\n1. CONSTANT OFFSET (reported separately from frame-to-frame change)")
    print(f"   dx = {co['x_px']:+.6f} px   dy = {co['y_px']:+.6f} px   "
          f"|d| = {co['magnitude_px']:.6f} px = {co['magnitude_a']:.6f} A")

    print("\n2. APPLIED-FIELD ERROR, constant offset removed")
    print(f"   {'region':10s} {'n':>6s} {'RMS px':>11s} {'P95 px':>11s} {'max px':>11s} "
          f"{'RMS A':>11s} {'P95 A':>11s} {'max A':>11s}")
    for region in ("all", "interior", "border"):
        s = m["total_offset_removed"][region]
        print(f"   {region:10s} {s['n']:6d} {_fmt(s['rms_px'])} {_fmt(s['p95_px'])} "
              f"{_fmt(s['max_px'])} {_fmt(s['rms_a'])} {_fmt(s['p95_a'])} {_fmt(s['max_a'])}")

    print("\n3. DECOMPOSITION")
    gc = m["global_component"]
    lc = m["local_component"]["interior"]
    ff = m["frame_to_frame"]["interior"]
    print(f"   global component (spatial mean per frame)   RMS {_fmt(gc['rms_px'])} px  "
          f"{_fmt(gc['rms_a'])} A   max {_fmt(gc['max_a'])} A")
    print(f"   local component  (spatially varying, int.)  RMS {_fmt(lc['rms_px'])} px  "
          f"{_fmt(lc['rms_a'])} A   max {_fmt(lc['max_a'])} A")
    print(f"   frame-to-frame change        (interior)     RMS {_fmt(ff['rms_px'])} px  "
          f"{_fmt(ff['rms_a'])} A   max {_fmt(ff['max_a'])} A")

    print("\n4. PER-FRAME DISTRIBUTION (offset removed, interior positions)")
    print(f"   {'frame':>5s} {'applied dx':>11s} {'applied dy':>11s} "
          f"{'RMS px':>10s} {'P95 px':>10s} {'max px':>10s} {'RMS A':>10s} {'max A':>10s}")
    for pf in m["per_frame"]:
        s = pf["error_interior"]
        print(f"   {pf['frame']:5d} {pf['recovered_mean_field_px'][0]:11.5f} "
              f"{pf['recovered_mean_field_px'][1]:11.5f} "
              f"{_fmt(s['rms_px'],10,5)} {_fmt(s['p95_px'],10,5)} {_fmt(s['max_px'],10,5)} "
              f"{_fmt(s['rms_a'],10,5)} {_fmt(s['max_a'],10,5)}")

    ib = m["interpolation_boundary"]
    print("\n5. INTERPOLATION BOUNDARY (reported, not cropped)")
    print(f"   unfaithful margin {ib['unfaithful_margin_px']:.0f} px -> "
          f"{ib['affected_output_pixels']} of {m['geometry']['nx'] * m['geometry']['ny']} "
          f"output pixels ({100 * ib['affected_fraction']:.2f} %)")
    print(f"   {ib['rule']}")

    if "dose_weighting_invariance" in report:
        d = report["dose_weighting_invariance"]
        print("\n6. DOSE-WEIGHTING BOUNDARY")
        print(f"   max field difference with/without dose weighting: "
              f"{d['max_field_difference_px']:.3e} px  -> {d['status']}")
        print(f"   {d['note']}")

    if "self_consistency" in report:
        sc = report["self_consistency"]
        print("\n7. APPLIED-FIELD SELF-CONSISTENCY (reported field re-applied independently)")
        print(f"   reference RMS {sc['reference_rms']:.6g}   absolute RMSE {sc['absolute_rmse']:.6g}"
              f"   relative RMSE {sc['relative_rmse']:.6e}")
        print(f"   noise floor {sc['noise_floor_relative_rmse']:.1e} -> "
              f"classified as {sc['classification'].upper()}")

    print("\n8. GATES  (limits from motion-accuracy physics; see the design record)")
    print(f"   {'metric':32s} {'value A':>10s} {'limit A':>10s} {'loss@3A':>9s} "
          f"{'B_eq A^2':>9s}  verdict")
    for c in g["checks"]:
        val = "" if c["value_a"] is None else f"{c['value_a']:10.5f}"
        lim = "" if c["limit_a"] is None else f"{c['limit_a']:10.5f}"
        loss = "" if c["amplitude_loss_at_3A"] is None else f"{100*c['amplitude_loss_at_3A']:8.2f}%"
        beq = "" if c["equivalent_bfactor_a2"] is None else f"{c['equivalent_bfactor_a2']:9.3f}"
        verdict = ("PASS" if c["pass"] else "FAIL") if c["gated"] else "report"
        print(f"   {c['name']:32s} {val:>10s} {lim:>10s} {loss:>9s} {beq:>9s}  {verdict}")
    print(f"\nOVERALL: {report['status']}  "
          f"({g['n_gated'] - g['n_failed']}/{g['n_gated']} gated metrics passed)")
    print("=" * 78)


# --------------------------------------------------------------------------------- main ----

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_motion_star(test_dir: Path, case: str) -> Path:
    cand = test_dir / f"{case}.star"
    if cand.exists():
        return cand
    stars = [p for p in sorted(test_dir.rglob("*.star"))
             if p.name != "corrected_micrographs.star"]
    if len(stars) == 1:
        return stars[0]
    raise FileNotFoundError(f"could not resolve a unique motion STAR in {test_dir}: {stars}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ground-truth", type=Path, required=True,
                    help="fixture ground-truth JSON from generate_known_motion_fixture.py")
    ap.add_argument("--test", type=Path,
                    help="MotionCorr output directory")
    ap.add_argument("--motion-star", type=Path,
                    help="explicit path to the per-micrograph motion STAR (overrides --test)")
    ap.add_argument("--movie", type=Path,
                    help="raw movie MRC stack; enables the applied-field self-consistency check")
    ap.add_argument("--summed-image", type=Path,
                    help="the program's non-dose-weighted sum, for self-consistency")
    ap.add_argument("--compare-star", type=Path,
                    help="a second motion STAR whose field must be identical (used for the "
                         "dose-weighting and thread-count invariance checks)")
    ap.add_argument("--compare-label", default="dose_weighting_invariance")
    ap.add_argument("--json", type=Path, help="write the machine-readable report here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not args.ground_truth.exists():
        print(f"ERROR: ground truth not found: {args.ground_truth}", file=sys.stderr)
        return 2
    gt = json.loads(args.ground_truth.read_text())

    if args.motion_star:
        star_path = args.motion_star
    elif args.test:
        try:
            star_path = resolve_motion_star(args.test, gt["case"])
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    else:
        print("ERROR: one of --test or --motion-star is required", file=sys.stderr)
        return 2
    if not star_path.exists():
        print(f"ERROR: motion STAR not found: {star_path}", file=sys.stderr)
        return 2

    star = mf.read_motion_star(star_path)
    metrics = evaluate(gt, star)
    gates = apply_gates(metrics)

    report = {
        "tool": "check_known_motion.py",
        "design_record": "agents/designs/issue_59_known_motion_local_field_gates.md",
        "case": gt["case"],
        "ground_truth": str(args.ground_truth),
        "ground_truth_sha256": sha256(args.ground_truth),
        "fixture_source_commit": gt.get("source_commit"),
        "fixture_seed": gt.get("seed"),
        "movie_sha256": gt.get("movie_sha256"),
        "motion_star": str(star_path),
        "motion_star_sha256": sha256(star_path),
        "thresholds_angstrom": dict(THRESHOLDS_ANGSTROM,
                                    constant_offset=CONSTANT_OFFSET_LIMIT_ANGSTROM),
        "threshold_basis": {
            "model": "amplitude envelope exp(-pi^2 sigma^2 / d^2); B_equiv = 4 pi^2 sigma^2",
            "target_resolution_a": TARGET_RESOLUTION_A,
            "provenance": "declared in the design record before fixtures were generated; "
                          "not derived from the 24 tutorial movies",
        },
        "metrics": metrics,
        "gates": gates,
    }

    if args.compare_star:
        other = mf.read_motion_star(args.compare_star)
        frames = np.arange(1, star.n_frames + 1)
        gx = np.asarray(gt["grid"]["x"], dtype=float)
        gy = np.asarray(gt["grid"]["y"], dtype=float)
        d = np.abs(star.field(frames, gx, gy) - other.field(frames, gx, gy)).max()
        report[args.compare_label] = {
            "other_star": str(args.compare_star),
            "max_field_difference_px": float(d),
            "status": "IDENTICAL" if d == 0.0 else "DIFFERS",
            "note": "dose weighting is a per-frame radial Fourier weight applied after "
                    "alignment; it cannot change the geometry, so any difference is a defect",
        }
        if d != 0.0:
            gates["checks"].append({
                "name": args.compare_label, "gated": True, "value_a": float(d * star.pixel_size),
                "value_px": float(d), "limit_a": 0.0, "limit_px": 0.0,
                "amplitude_loss_at_3A": None, "equivalent_bfactor_a2": None, "pass": False,
                "note": "field changed by a step that cannot change geometry",
            })
            gates["n_gated"] += 1
            gates["n_failed"] += 1
            gates["status"] = "FAIL"

    if args.movie and args.summed_image:
        report["self_consistency"] = self_consistency(args.movie, star, args.summed_image)

    report["status"] = gates["status"]

    if not args.quiet:
        print_report(report)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
