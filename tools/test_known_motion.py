#!/usr/bin/env python3
"""Tests for the known-motion gate: unit checks, fixture self-validation, negative controls.

    python3 tools/test_known_motion.py --binary build/motioncorr

A gate that only ever passes proves nothing. Part 3 injects a known defect into a field that
MotionCorr itself produced, re-runs the checker, and requires it to fail *on the metric that
should notice*. Part 2 is the more fundamental check: it confirms, from the pixels alone, that
the fixture's declared truth is the motion actually present in the movie.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import check_known_motion as ckm  # noqa: E402
import motion_field as mf  # noqa: E402

FAILURES: list[str] = []
PASSES = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSES
    if ok:
        PASSES += 1
        print(f"  PASS  {name}" + (f"   ({detail})" if detail else ""))
    else:
        FAILURES.append(name)
        print(f"  FAIL  {name}   {detail}")


# ----------------------------------------------------------------------- 1. unit checks ----

def reference_get_shift_at(coeff_x, coeff_y, z, u, v):
    """A deliberately literal transcription of ThirdOrderPolynomialModel::getShiftAt.

    Written out term by term rather than vectorised, so it shares no code with the
    implementation under test.
    """
    x2, y2, xy, z2 = u * u, v * v, u * v, z * z
    z3 = z2 * z
    c = coeff_x
    sx = ((c[0] * z + c[1] * z2 + c[2] * z3)
          + (c[3] * z + c[4] * z2 + c[5] * z3) * u
          + (c[6] * z + c[7] * z2 + c[8] * z3) * x2
          + (c[9] * z + c[10] * z2 + c[11] * z3) * v
          + (c[12] * z + c[13] * z2 + c[14] * z3) * y2
          + (c[15] * z + c[16] * z2 + c[17] * z3) * xy)
    c = coeff_y
    sy = ((c[0] * z + c[1] * z2 + c[2] * z3)
          + (c[3] * z + c[4] * z2 + c[5] * z3) * u
          + (c[6] * z + c[7] * z2 + c[8] * z3) * x2
          + (c[9] * z + c[10] * z2 + c[11] * z3) * v
          + (c[12] * z + c[13] * z2 + c[14] * z3) * y2
          + (c[15] * z + c[16] * z2 + c[17] * z3) * xy)
    return sx, sy


def unit_tests() -> None:
    print("\n1. UNIT CHECKS")
    rng = np.random.default_rng(59)
    star = mf.MotionStar(path=Path("synthetic"), nx=768, ny=512, n_frames=9, first_frame=1,
                         pixel_size=0.885, binning=1.0, motion_model_version=1,
                         global_shift_x=rng.normal(0, 2, 9), global_shift_y=rng.normal(0, 2, 9),
                         coeff_x=rng.normal(0, 0.05, 18), coeff_y=rng.normal(0, 0.05, 18))
    worst = 0.0
    for f in range(1, 10):
        for ix, iy in [(0, 0), (767, 511), (383, 255), (12.5, 401.75), (700, 3)]:
            u, v = ix / star.nx - 0.5, iy / star.ny - 0.5
            ex, ey = reference_get_shift_at(star.coeff_x, star.coeff_y, f - star.first_frame, u, v)
            ex += star.global_shift_x[f - 1]
            ey += star.global_shift_y[f - 1]
            got = star.field([f], [ix], [iy])[0, 0]
            worst = max(worst, abs(got[0] - ex), abs(got[1] - ey))
    check("field() reproduces getShiftAt term by term", worst < 1e-12, f"max |d| = {worst:.2e}")

    # nx and ny are not interchangeable: a non-square movie must notice a swap.
    swapped = star.copy()
    swapped.nx, swapped.ny = star.ny, star.nx
    d = np.abs(star.field([9], [700], [3]) - swapped.field([9], [700], [3])).max()
    check("nx/ny normalisation is not interchangeable", d > 1e-6, f"|d| = {d:.4f} px")

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "rt.star"
        star.general = {"rlnImageSizeX": "768", "rlnImageSizeY": "512", "rlnImageSizeZ": "9",
                        "rlnMicrographOriginalPixelSize": "0.885000",
                        "rlnMicrographBinning": "1.000000",
                        "rlnMicrographStartFrame": "1", "rlnMotionModelVersion": "1"}
        mf.write_motion_star(star, out)
        back = mf.read_motion_star(out)
        d = np.abs(star.field([5], [100, 700], [50, 3])
                   - back.field([5], [100, 700], [50, 3])).max()
        check("STAR round-trip preserves the field", d < 1e-12, f"max |d| = {d:.2e} px")

    # The envelope model behind the thresholds.
    check("0.10 A residual costs ~1.1 % amplitude at 3 A",
          abs(ckm.amplitude_loss(0.10) - 0.0109) < 5e-4,
          f"{100 * ckm.amplitude_loss(0.10):.2f} %")
    check("0.20 A residual is equivalent to B = 1.58 A^2",
          abs(ckm.equivalent_bfactor(0.20) - 1.579) < 0.01,
          f"B = {ckm.equivalent_bfactor(0.20):.3f}")


# ------------------------------------------------- 2. the fixture's truth is really true ---

def fixture_self_validation(fixtures: Path) -> None:
    """Confirm from the pixels that the declared field is the motion the movie contains.

    Everything else in this file assumes the ground truth is true. This is the check that earns
    that assumption: an estimator that shares no code with MotionCorr measures the frame-to-frame
    displacement straight out of the pixel data and is required to agree with the declared field.
    """
    print("\n2. FIXTURE SELF-VALIDATION (truth versus the pixels it claims to describe)")
    gt = json.loads((fixtures / "km_global_hisnr_ground_truth.json").read_text())
    movie, _ = mf.read_mrc(fixtures / gt["movie_file"])
    movie = movie.astype(np.float64)
    truth = np.asarray(gt["expected_applied_field"])

    def ncc(a, b, sx, sy):
        bs = mf.shift_frame_fourier(b, sx, sy)
        a0, b0 = a - a.mean(), bs - bs.mean()
        return float((a0 * b0).sum() / np.sqrt((a0 * a0).sum() * (b0 * b0).sum()))

    worst = 0.0
    for f in (3, 7, gt["geometry"]["n_frames"] - 1):
        sx, sy = truth[f, 0, 0], truth[f, 0, 1]
        h = 1e-3
        for _ in range(25):                       # Newton on the exact correlation surface
            for axis in (0, 1):
                p = [sx, sy]
                c0 = ncc(movie[0], movie[f], *p)
                p[axis] += h
                cp = ncc(movie[0], movie[f], *p)
                p[axis] -= 2 * h
                cm = ncc(movie[0], movie[f], *p)
                d1, d2 = (cp - cm) / (2 * h), (cp - 2 * c0 + cm) / (h * h)
                if d2 < 0:
                    step = float(np.clip(-d1 / d2, -0.2, 0.2))
                    if axis == 0:
                        sx += step
                    else:
                        sy += step
        worst = max(worst, abs(sx - truth[f, 0, 0]), abs(sy - truth[f, 0, 1]))
    # 0.01 px is ~30x the estimator's own noise on this fixture and ~100x below the smallest
    # defect the gate must catch; a non-periodic fixture missed by 0.08 px here.
    check("declared field matches the motion measured from the pixels", worst < 0.01,
          f"max |d| = {worst:.2e} px")


# ------------------------------------------------------------------ 3. negative controls ---

def perturb(star: mf.MotionStar, kind: str, amp: float = 1.0) -> mf.MotionStar:
    """Inject a defect of the given kind. ``amp`` is in pixels, scaled per kind as documented."""
    s = star.copy()
    zmax = s.n_frames - s.first_frame
    if kind == "wrong_global_frame":
        # one frame displaced by `amp` px
        s.global_shift_x[len(s.global_shift_x) // 2] += amp
    elif kind == "trajectory_scale":
        # every frame scaled by (1 + amp): the shape of the border artefact this fixture set
        # was found to contain before the base image was made periodic
        s.global_shift_x = s.global_shift_x * (1.0 + amp)
        s.global_shift_y = s.global_shift_y * (1.0 + amp)
    elif kind == "wrong_local_field":
        # `amp` px extra at |u| = 0.5 on the last frame, and nothing at all at the centre:
        # invisible to a global-trajectory check by construction
        s.coeff_x[3] += 2.0 * amp / zmax
    elif kind == "sign_flip":
        s.global_shift_x *= -1; s.global_shift_y *= -1
        if s.coeff_x is not None:
            s.coeff_x = -s.coeff_x; s.coeff_y = -s.coeff_y
    elif kind == "axis_swap":
        s.global_shift_x, s.global_shift_y = s.global_shift_y.copy(), s.global_shift_x.copy()
        if s.coeff_x is not None:
            s.coeff_x, s.coeff_y = s.coeff_y.copy(), s.coeff_x.copy()
    elif kind == "uniform_bias":
        s.global_shift_x[1:] += amp           # constant over every frame but the first
    elif kind == "fft_rounding":
        s.global_shift_x += 1e-6
        if s.coeff_x is not None:
            s.coeff_x[0] += 1e-6 / max(zmax, 1)
    else:
        raise ValueError(kind)
    return s


def negative_controls(gt_path: Path, motion_star: Path, workdir: Path) -> None:
    print("\n3. NEGATIVE CONTROLS (a gate that cannot fail is not a gate)")
    gt = json.loads(gt_path.read_text())
    base = mf.read_motion_star(motion_star)

    baseline = ckm.apply_gates(ckm.evaluate(gt, base))
    check("unperturbed run passes", baseline["status"] == "PASS",
          f"{baseline['n_gated'] - baseline['n_failed']}/{baseline['n_gated']}")

    # Amplitudes are chosen from the declared tolerances, not from what happens to trip the
    # gate. A single frame displaced by d contributes d/sqrt(N) to an RMS over N frames, so
    # catching it at tier B (0.113 px) needs d > 0.113*sqrt(12) = 0.39 px; 0.60 px is that with
    # margin. Requiring rejection of anything smaller would be requiring the gate to violate its
    # own specification. Section 5 measures where the boundary actually falls.
    expectations = {
        # control              amp    must fail                     must still pass
        "wrong_global_frame": (0.60, ["global_component_rms"], []),
        # A uniform scale error is mostly a mean offset, so it is `constant_offset` that
        # catches it -- the very gate tightened in Amendment 2. Before the base image was made
        # periodic these fixtures carried a 1.2 % scale artefact of exactly this shape.
        "trajectory_scale":   (0.05, ["constant_offset"], []),
        "wrong_local_field":  (1.00, ["local_component_rms"], ["global_component_rms"]),
        "sign_flip":          (1.00, ["global_component_rms", "local_component_rms",
                                      "total_rms_interior"], []),
        "axis_swap":          (1.00, ["total_rms_interior"], []),
        "uniform_bias":       (0.25, ["constant_offset"], ["frame_to_frame_rms_interior"]),
        "fft_rounding":       (1.00, [], ["global_component_rms", "local_component_rms",
                                          "total_rms_interior", "constant_offset"]),
    }
    for kind, (amp, must_fail, must_pass) in expectations.items():
        s = perturb(base, kind, amp)
        path = workdir / f"{kind}.star"
        mf.write_motion_star(s, path)
        res = ckm.apply_gates(ckm.evaluate(gt, mf.read_motion_star(path)))
        by = {c["name"]: c for c in res["checks"]}
        if must_fail:
            ok = res["status"] == "FAIL" and all(not by[n]["pass"] for n in must_fail)
            worst = max(by[n]["value_a"] for n in must_fail)
            check(f"{kind} (amp {amp} px): rejected", ok,
                  f"{', '.join(must_fail)} up to {worst:.3f} A; overall {res['status']}")
        else:
            ok = res["status"] == "PASS"
            worst = max(by[n]["value_a"] for n in must_pass)
            check(f"{kind}: accepted as harmless", ok, f"worst gated metric {worst:.2e} A")
        for n in must_pass:
            check(f"{kind}: {n} still passes", by[n]["pass"],
                  f"{by[n]['value_a']:.4f} A vs {by[n]['limit_a']:.4f} A")


# ------------------------------------------ 4. rounding versus a real field defect ----------

def rounding_versus_defect(gt_path: Path, motion_star: Path, fixtures: Path,
                           summed: Path) -> None:
    """Measure the arithmetic noise floor, then show where a field defect leaves it behind.

    The self-consistency witness re-applies the reported field in float64 while the program
    worked in float32. The residual of that comparison has a floor set by rounding. This walks
    the field away from the truth and reports the response, so the separation between
    "harmless rounding" and "wrong field" is measured rather than asserted.
    """
    print("\n4. ARITHMETIC NOISE FLOOR VERSUS FIELD DEFECT (self-consistency response)")
    gt = json.loads(gt_path.read_text())
    star = mf.read_motion_star(motion_star)
    movie = fixtures / gt["movie_file"]
    floor = None
    print(f"   {'injected field error (px)':>26s} {'relative RMSE':>15s} {'classification':>16s}")
    for delta in (0.0, 1e-6, 1e-3, 0.01, 0.1, 0.5):
        s = star.copy()
        s.global_shift_x = s.global_shift_x + delta
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "p.star"
            mf.write_motion_star(s, p)
            res = ckm.self_consistency(movie, mf.read_motion_star(p), summed)
        if delta == 0.0:
            floor = res["relative_rmse"]
        print(f"   {delta:>26g} {res['relative_rmse']:>15.3e} {res['classification']:>16s}")
        if delta == 0.0:
            check("unperturbed field re-applies to the program's own pixels",
                  res["classification"] == "numerical_noise",
                  f"relative RMSE {res['relative_rmse']:.2e}")
        if delta == 1e-6:
            check("rounding-scale field change stays at the noise floor",
                  res["classification"] == "numerical_noise",
                  f"relative RMSE {res['relative_rmse']:.2e}")
        if delta == 0.1:
            check("a 0.1 px field error is not rounding",
                  res["classification"] == "field_defect",
                  f"{res['relative_rmse'] / floor:.0f}x the floor")


def sensitivity(gt_path: Path, motion_star: Path) -> None:
    """Measure the smallest defect of each kind that the gate rejects.

    A pass/fail on one hand-picked amplitude says the gate can fail. This says *when* it fails,
    which is the number a reviewer actually needs in order to judge whether the gate is useful.
    """
    print("\n5. DETECTION SENSITIVITY (smallest rejected defect, by bisection)")
    gt = json.loads(gt_path.read_text())
    base = mf.read_motion_star(motion_star)
    px = gt["geometry"]["pixel_size_angstrom"]

    def rejected(kind, amp):
        return ckm.apply_gates(ckm.evaluate(gt, perturb(base, kind, amp)))["status"] == "FAIL"

    units = {"wrong_global_frame": "px on one frame",
             "trajectory_scale": "fractional scale error on every frame",
             "wrong_local_field": "px at the field corners on the last frame",
             "uniform_bias": "px on every frame but the first"}
    print(f"   {'defect':22s} {'threshold':>12s}  units")
    for kind, unit in units.items():
        lo, hi = 0.0, 1e-4
        while hi < 100 and not rejected(kind, hi):
            hi *= 2
        if hi >= 100:
            print(f"   {kind:22s} {'not reached':>12s}  {unit}")
            continue
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if rejected(kind, mid):
                hi = mid
            else:
                lo = mid
        extra = f" = {hi * px:.3f} A" if "px" in unit else ""
        print(f"   {kind:22s} {hi:12.4f}  {unit}{extra}")
        check(f"{kind}: detection threshold is finite and subpixel-scale", hi < 2.0,
              f"{hi:.4f} {unit}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", type=Path, default=REPO / "build" / "motioncorr")
    ap.add_argument("--fixtures", type=Path, default=REPO / "test-data" / "known_motion")
    ap.add_argument("--case", default="km_local_hisnr")
    ap.add_argument("--keep", type=Path, help="keep the working directory here")
    args = ap.parse_args()

    if not args.binary.exists():
        print(f"ERROR: binary not found: {args.binary}", file=sys.stderr)
        return 2

    gt_path = args.fixtures / f"{args.case}_ground_truth.json"
    if not gt_path.exists():
        print("ERROR: fixture missing; run test-data/generate_known_motion_fixture.py first",
              file=sys.stderr)
        return 2
    gt = json.loads(gt_path.read_text())

    unit_tests()
    fixture_self_validation(args.fixtures)

    tmp = tempfile.TemporaryDirectory()
    work = args.keep or Path(tmp.name)
    work.mkdir(parents=True, exist_ok=True)
    rec = gt["recommended_run"]
    cmd = [str(args.binary), "--i", gt["input_star"], "--o", str(work), "--use_own", "--j", "1",
           "--patch_x", str(rec["patch_x"]), "--patch_y", str(rec["patch_y"]),
           "--seed", "1", "--save_noDW"]
    if rec["skip_defect"]:
        cmd.append("--skip_defect")
    proc = subprocess.run(cmd, cwd=args.fixtures, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout + proc.stderr, file=sys.stderr)
        return 2
    motion_star = work / f"{args.case}.star"

    negative_controls(gt_path, motion_star, work)
    rounding_versus_defect(gt_path, motion_star, args.fixtures, work / f"{args.case}.mrc")
    sensitivity(gt_path, motion_star)

    print(f"\n{PASSES} passed, {len(FAILURES)} failed")
    for f in FAILURES:
        print(f"  failed: {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
