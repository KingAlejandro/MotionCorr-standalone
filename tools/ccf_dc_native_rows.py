#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Pinned commands, run-directory grading and scoring for the native CCF DC tiny tiers (K267, N controls).

Nothing here launches a producer. It defines (1) the exact argv/env pins, (2) how a finished run
directory is graded, and (3) scoring through the existing checkers. Truth enters only inside the
scoring stage (``check_motion_diagnostics.check_case`` for K267, the retained truth file for the N
controls). The tap bridge and the witness grading never see truth.

Run-directory contract (written by the harness, one producer per directory):
    argv.json  rc.txt  stdout.txt  stderr.txt  witness.json (experiment builds)  tap.json (experiment builds)
    out/<movie>.mrc  out/<movie>.star  out/<movie>.log  out/corrected_micrographs.star

Row status, in order of precedence:
    FAILED_RUN             actual exit status != 0 (a complete-looking tap or witness does not rescue it)
    INCOMPLETE_PUBLICATION a published product is missing or empty
    INVALID                witness/tap/bridge inconsistent with the declared run
    INCONCLUSIVE           a declared (site, stage) was never reached (eligible == 0): a vacuous arm
    SCORED                 everything above holds; field verdicts are reported as the checkers emit them
A field FAIL is a result, not a harness failure. Missing convergence markers are reported MISSING or
AMBIGUOUS, never as a pass.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_motion_diagnostics as cmd
import check_realistic_motion as crm
import ccf_dc_tap_field as bridge
from motion_field import read_mrc, read_motion_star

ARMS = {"none": (0, 0), "global": (1, 0), "local": (0, 1), "both": (1, 1)}   # (global, local) selected
SITES = ("cpu", "cuda_single", "cuda_batched")
# Declared (site) per backend and stage. CUDA local is the batched path (default MOTIONCORR_PATCH_BATCH).
DECLARED = {"cpu": {"global": "cpu", "local": "cpu"}, "cuda": {"global": "cuda_single", "local": "cuda_batched"}}
PIXEL_SIZE = 0.885
LIMITS_A = (0.20, 0.40, 0.80)   # rms, p95, max in Angstrom, unchanged


# ------------------------------------------------------------------------------------ pins --

# Original per-case patch grid of the retained native K267 run (`run_v2.py`): 3x3 for the three cases that exercise
# the local stage, 1x1 (global alignment only) for the other five.
K267_PATCHES = {"zero": 1, "integer": 1, "fractional": 1, "affine": 3, "pedestal": 3, "noisy": 3, "flat": 1, "repeated": 1}


def k267_stages(case, patches=None):
    """Stages this row is expected to execute: global always, local only when more than one patch is requested."""
    return ("global", "local") if (patches or K267_PATCHES[case]) > 1 else ("global",)


def k267_argv(binary, case, outdir, backend, patches=None):
    """Original native K267 command per case (`K267_PATCHES`). The retained command also had --skip_logfile; it is
    dropped here so the product log (the convergence markers) exists, which must not change numerics (checked by
    `CcfDcRowsNative.test_skip_logfile_does_not_change_the_products`). `patches` overrides the grid only for the
    separately labelled, held all-3x3 configurations; it never replaces the original rows."""
    n = patches or K267_PATCHES[case]
    argv = [str(binary), "--i", f"{case}.star", "--o", str(outdir), "--use_own", "--j", "8", "--patch_x", str(n),
            "--patch_y", str(n), "--bin_factor", "1", "--seed", "1", "--skip_defect", "--save_noDW",
            "--first_frame_sum", "1", "--last_frame_sum", "5"]
    return argv + (["--gpu", "0"] if backend == "cuda" else [])


def n_argv(binary, name, frames, outdir, backend):
    """Retained N-control command (`--j 2`, 1x1 patches, `--last_frame_sum N`; run with `OMP_NUM_THREADS=N_OMP`), with
    the product log kept (the retained command had --skip_logfile; same declared deviation as K267)."""
    argv = [str(binary), "--i", f"{name}.star", "--o", str(outdir), "--use_own", "--j", "2", "--patch_x", "1",
            "--patch_y", "1", "--bin_factor", "1", "--seed", "1", "--skip_defect", "--save_noDW",
            "--first_frame_sum", "1", "--last_frame_sum", str(frames)]
    return argv + (["--gpu", "0"] if backend == "cuda" else [])


K267_OMP, N_OMP = 8, 2   # as the retained runs: K267 `run_v2.py` OMP 8 (--j 8); N controls `run_ncontrols.py` OMP 2 (--j 2)


def run_env(arm, report, tap=None, cuda_uuid=None, omp=K267_OMP):
    """Environment for one producer; arm None means unset (identity rows). Report/tap only on experiment builds.
    N controls pass omp=N_OMP."""
    env = {"OMP_NUM_THREADS": str(omp)}
    if arm is not None:
        env["MC_EXPERIMENT_CCF_DC_ARM"] = arm
    if report:
        env["MC_EXPERIMENT_CCF_DC_REPORT"] = str(report)
    if tap:
        env["MC_DIAG_MODEL_OUT"] = str(tap)
    if cuda_uuid:
        env["CUDA_VISIBLE_DEVICES"] = cuda_uuid
        env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    return env


# ------------------------------------------------------------------------ progress clock --

# The progress bar prints elapsed/remaining wall-clock seconds on a line of exactly this shape.
CLOCK_LINE = re.compile(r'(?m)^ *\d+/ *\d+ sec \.{60}~~\(,_,"> yum!$')


# The only product-log line that differs between two identical runs (measured on repeated identical runs).
LOG_WALL_LINE = re.compile(r"(?m)^Full movie wall time: [0-9.]+ s$")


def normalise_console(text, outdir=None):
    """Replace the output directory, the anchored progress-clock line and the anchored wall-time log line; nothing else."""
    if outdir is not None:
        text = text.replace(str(outdir), "OUT")
    return LOG_WALL_LINE.sub("Full movie wall time: T s", CLOCK_LINE.sub("T/T sec CLOCK", text))


# ------------------------------------------------------------------------------- witness --

def grade_witness(w, backend, arm, stages, iso_expected):
    """Return ('VALID'|'INVALID'|'INCONCLUSIVE', reasons). `stages` are the stages the run is declared to reach."""
    bad, vacuous = [], []
    if not isinstance(w, dict) or w.get("schema") != "mc-ccf-dc-witness-v1":
        return "INVALID", ["witness schema"]
    if w.get("status") != "atexit":
        bad.append(f"witness status {w.get('status')!r} (not atexit)")
    if w.get("arm") != arm:
        bad.append(f"witness arm {w.get('arm')!r} != requested {arm!r}")
    if w.get("test_only_isotropic_global_weight") is not iso_expected:
        bad.append("binary identity: isotropic flag differs from the declared build")
    try:
        sites = w["sites"]
        for site in SITES:
            for stage in ("global", "local"):
                c = sites[site][stage]
                if not (0 <= c["calls_zeroed"] <= c["calls_eligible"] and 0 <= c["frames_zeroed"] <= c["frames_eligible"]):
                    bad.append(f"{site}.{stage} counters inconsistent")
        sel = dict(zip(("global", "local"), ARMS[arm]))
        declared = DECLARED[backend]
        for stage in ("global", "local"):
            site = declared[stage]
            c = sites[site][stage]
            if stage in stages:
                if c["frames_eligible"] <= 0 or c["calls_eligible"] <= 0:
                    vacuous.append(f"{site}.{stage} never reached (eligible 0)")
        # Selectivity on EVERY reached (site, stage), including the CUDA retry site cuda_single.local: a reached call
        # of a selected stage is zeroed, of an unselected stage never; a stage that is not requested is never reached.
        for site in SITES:
            for stage in ("global", "local"):
                c = sites[site][stage]
                if c["frames_eligible"] > 0 or c["calls_eligible"] > 0:
                    if c["frames_zeroed"] != (c["frames_eligible"] if sel[stage] else 0):
                        bad.append(f"{site}.{stage} zeroed {c['frames_zeroed']} of {c['frames_eligible']} with that stage {'selected' if sel[stage] else 'unselected'}")
                    if stage not in stages:
                        bad.append(f"{site}.{stage} reached but the run declares only {sorted(stages)}")
        # A run must not leave its backend: a cpu run touches no CUDA site and a cuda run touches no cpu site
        # (a fallback to the host path is a different route and must not be graded as the declared one).
        # cuda_single.local is allowed on CUDA (retry), cuda_batched.global never occurs.
        forbidden = [("cuda_single", "global"), ("cuda_single", "local"), ("cuda_batched", "global"), ("cuda_batched", "local")] \
            if backend == "cpu" else [("cpu", "global"), ("cpu", "local"), ("cuda_batched", "global")]
        for site, stage in forbidden:
            if any(sites[site][stage].values()):
                bad.append(f"{site}.{stage} touched by a {backend} run")
    except (KeyError, TypeError) as e:
        return "INVALID", [f"witness structure: {e!r}"]
    return ("INVALID", bad) if bad else (("INCONCLUSIVE", vacuous) if vacuous else ("VALID", []))


# ----------------------------------------------------------------------------- scoring --

STAR_FIELD_TOL_PX = 1e-9   # double-precision evaluation order only; the writer rounding is replicated exactly


def star_format(v):
    """The value the STAR writer stores for a double (src/metadata_table.cpp): fixed point with 5 (negative) or
    6 (positive) decimals when 0.001 <= |v| <= 1e5, otherwise exponent form with 5 or 6 digits."""
    if (0.0 < abs(v) < 0.001) or abs(v) > 100000.0:
        return float(("%12.5e" if v < 0.0 else "%12.6e") % v)
    return float(("%12.5f" if v < 0.0 else "%12.6f") % v)


def star_rounded_tap(tap):
    """The tap as it would read back from the serialized STAR: every number passed through the writer's format."""
    return dict(tap, **{"global": [[star_format(x) for x in p] for p in tap["global"]],
                        "coeff_x": [star_format(x) for x in tap["coeff_x"]],
                        "coeff_y": [star_format(x) for x in tap["coeff_y"]]})


def stage_coverage(w, backend, arm, stages):
    """Per stage: COVERED (expected and reached), INCONCLUSIVE (expected, never reached), NOT_APPLICABLE (not requested).
    A selected arm on a stage that is not requested is a no-op selectivity observation, never local coverage."""
    sel = dict(zip(("global", "local"), ARMS[arm]))
    out = {}
    for stage in ("global", "local"):
        c = w["sites"][DECLARED[backend][stage]][stage]
        if stage in stages:
            out[stage] = "COVERED" if c["frames_eligible"] > 0 and c["calls_eligible"] > 0 else "INCONCLUSIVE"
        else:
            out[stage] = "NOT_APPLICABLE" + (" (arm selects it: no-op selectivity)" if sel[stage] and c["frames_eligible"] == 0 else "")
    return out


def convergence_of(log_path):
    """Convergence markers from the existing product log (unchanged parser). Never a silent pass."""
    p = Path(log_path)
    if not p.is_file() or "Global alignment:" not in p.read_text(errors="replace"):
        return dict(status="MISSING", reason="no product log or no global-alignment section")
    c = crm.convergence(p)
    g = c["global_converged"]
    patches = c["patches"]
    return dict(status={True: "CONVERGED", False: "NOT_CONVERGED", None: "AMBIGUOUS"}[g], global_iterations=c["global_iterations"],
                patches_total=len(patches), patches_converged=sum(q["converged"] is True for q in patches),
                patches_not_converged=sum(q["converged"] is False for q in patches),
                patches_ambiguous=sum(q["converged"] is None for q in patches))


def _publication(run, movie):
    out = run / "out"
    need = [out / f"{movie}.mrc", out / f"{movie}.star", out / "corrected_micrographs.star", out / f"{movie}.log"]
    return [str(p.name) for p in need if not p.is_file() or p.stat().st_size == 0]


def _head(run, movie, backend, arm, stages, iso_expected, has_witness):
    """Everything up to scoring. Returns (row, ok_to_score)."""
    row = dict(run=str(run), movie=movie, backend=backend, arm=arm)
    rc_path = run / "rc.txt"
    row["exit"] = int(rc_path.read_text()) if rc_path.is_file() else None
    if row["exit"] != 0:
        return dict(row, row_status="FAILED_RUN", reason=f"exit status {row['exit']}"), False
    missing = _publication(run, movie)
    if missing:
        return dict(row, row_status="INCOMPLETE_PUBLICATION", reason=f"missing or empty: {missing}"), False
    if has_witness:
        wp = run / "witness.json"
        if not wp.is_file():
            return dict(row, row_status="INVALID", reason="witness.json absent"), False
        try:
            w = json.loads(wp.read_text())
        except ValueError as e:
            return dict(row, row_status="INVALID", reason=f"witness unreadable: {e}"), False
        row["witness_status"], row["witness_reasons"] = grade_witness(w, backend, arm, stages, iso_expected)
        row["counters"] = w.get("sites")
        row["expected_stages"] = sorted(stages)
        if row["witness_status"] != "INVALID":
            row["stage_coverage"] = stage_coverage(w, backend, arm, stages)
        if row["witness_status"] == "INVALID":
            return dict(row, row_status="INVALID", reason="; ".join(row["witness_reasons"])), False
    row["convergence"] = convergence_of(run / "out" / f"{movie}.log")
    return row, True


def _finish(row):
    row["row_status"] = "INCONCLUSIVE" if row.get("witness_status") == "INCONCLUSIVE" else "SCORED"
    if row["row_status"] == "INCONCLUSIVE":
        row["reason"] = "; ".join(row["witness_reasons"])
    return row


def _tap_state(run, has_witness, tap_expected):
    """Runtime-tap handling. An experiment-build row (has_witness) expects its tap by default; an expected tap that is
    absent fails closed. A build that cannot write a tap (def) is declared with has_witness=False and is reported as
    NOT_REQUESTED, never as a scored runtime representation."""
    expected = has_witness if tap_expected is None else tap_expected
    if expected and not has_witness:
        raise ValueError("a tap cannot be expected from a build without the experiment hooks")
    if expected and not (run / "tap.json").is_file():
        return None, "INVALID", "runtime tap requested but absent (no runtime fallback to STAR)"
    return expected, None, None


def grade_k267(run, fixtures, case, backend, arm, iso_expected=False, has_witness=True, stages=None, tap_expected=None):
    """`stages` defaults to the stages the original CLI of this case executes (`k267_stages`); a caller that asked
    for more (e.g. a held all-3x3 configuration) passes them explicitly."""
    run, fixtures = Path(run), Path(fixtures)
    stages = k267_stages(case) if stages is None else tuple(stages)
    row, ok = _head(run, case, backend, arm, set(stages), iso_expected, has_witness)
    row["tier"] = "K"
    if not ok:
        return row
    r = json.loads((fixtures / "MANIFEST.json").read_text())["cases"][case]["recipe"]
    star = run / "out" / f"{case}.star"
    try:
        row["star"] = cmd.check_case(fixtures, case, star)
    except Exception as e:   # the unchanged checker's own refusals are results, not harness failures
        row["star"] = dict(checker_error=f"{type(e).__name__}: {e}")
    expect_tap, status, why = _tap_state(run, has_witness, tap_expected)
    if status:
        return dict(row, row_status=status, reason=why)
    row["runtime_representation"] = "SCORED" if expect_tap else "NOT_REQUESTED"
    if expect_tap:
        try:
            tap = bridge.load_tap(run / "tap.json", r["frames"])
            field = bridge.dense_field(tap, r["nx"], r["ny"], r["frames"])
            cand = run / "tap_field.npy"
            np.save(cand, field, allow_pickle=False)
            s = read_motion_star(star)
            q = cmd.gen.grid(r)
            sf = s.field(s.frames, q[..., 0].ravel(), q[..., 1].ravel()).reshape(field.shape)
            expected = bridge.dense_field(star_rounded_tap(tap), r["nx"], r["ny"], r["frames"])
            diff = np.abs(expected - sf).max(axis=(0, 1, 2))
            row["tap_rounded_vs_star_max_px"] = diff.tolist()
            row["tap_vs_star_max_px"] = np.abs(field - sf).max(axis=(0, 1, 2)).tolist()   # the writer's own rounding loss
            if diff.max() > STAR_FIELD_TOL_PX:
                return dict(row, row_status="INVALID", reason="tap field (rounded as the STAR writer rounds) and the serialized STAR field disagree")
            row["local_enabled"] = tap["local_enabled"]
        except bridge.TapError as e:
            return dict(row, row_status="INVALID", reason=f"tap: {e}")
        except Exception as e:   # bridge or STAR read-back failed: fail closed, not a checker result
            return dict(row, row_status="INVALID", reason=f"tap bridge or STAR read-back: {type(e).__name__}: {e}")
        try:
            row["tap"] = cmd.check_case(fixtures, case, cand)
        except Exception as e:   # the unchanged checker's own refusals are results, not harness failures
            row["tap"] = dict(checker_error=f"{type(e).__name__}: {e}")
    return _finish(row)


def n_score(global_shifts, truth_px, roi=(12, 84, 12, 116)):
    """Field metrics of the retained W5 convention: the per-frame error vector is repeated over the dense ROI
    (y0:y1, x0:x1) before the unchanged `vector_metrics`, so rms, p95 and max are taken over frames x ROI pixels. The
    p95 interpolates differently over N frame vectors alone (up to 0.12 A in 12 of 16 retained rows), so the ROI
    broadcast is part of the metric. Frame-zero gauge, 0.885 A/px, no offset or floor subtracted."""
    y0, y1, x0, x1 = roi
    err = (np.asarray(global_shifts, dtype=float) - np.asarray(truth_px, dtype=float)) * PIXEL_SIZE
    dense = np.broadcast_to(err[:, None, None, :], (err.shape[0], y1 - y0, x1 - x0, 2))
    m = cmd.vector_metrics(dense)
    ok = m["rms"] <= LIMITS_A[0] and m["p95"] <= LIMITS_A[1] and m["max"] <= LIMITS_A[2]
    return dict(rms=m["rms"], p95=m["p95"], max=m["max"], verdict="PASS" if ok else "FAIL")


def grade_n(run, controls, name, backend, arm, iso_expected=False, has_witness=True, tap_expected=None):
    run, controls = Path(run), Path(controls)
    man = json.loads((controls / "MANIFEST.json").read_text())["cases"][name]
    row, ok = _head(run, name, backend, arm, {"global"}, iso_expected, has_witness)
    row["tier"] = "N"
    if not ok:
        return row
    truth = np.load(controls / f"{name}_truth.npy", allow_pickle=False)   # scoring stage only
    s = read_motion_star(run / "out" / f"{name}.star")
    star_g = np.stack((s.global_shift_x, s.global_shift_y), axis=-1)
    roi = tuple(man["roi"])
    row["STAR"] = n_score(star_g, truth, roi)
    row["traj_rms_px_STAR"] = float(np.sqrt(np.mean((star_g - truth) ** 2) * 2))
    expect_tap, status, why = _tap_state(run, has_witness, tap_expected)
    if status:
        return dict(row, row_status=status, reason=why)
    row["runtime_representation"] = "SCORED" if expect_tap else "NOT_REQUESTED"
    if expect_tap:
        try:
            tap = bridge.load_tap(run / "tap.json", man["frames"])
        except bridge.TapError as e:
            return dict(row, row_status="INVALID", reason=f"tap: {e}")
        g = np.array(tap["global"])
        row["runtime"] = n_score(g, truth, roi)
        row["traj_rms_px_runtime"] = float(np.sqrt(np.mean((g - truth) ** 2) * 2))
        row["runtime_minus_STAR_max_px"] = float(np.abs(g - star_g).max())
        row["rounded_runtime_minus_STAR_max_px"] = float(np.abs(np.vectorize(star_format)(g) - star_g).max())
        if row["rounded_runtime_minus_STAR_max_px"] > STAR_FIELD_TOL_PX:
            return dict(row, row_status="INVALID", reason="tap global shifts (rounded as the STAR writer rounds) and STAR disagree")
    return _finish(row)


def identity_report(run_a, run_b, movie):
    """B3 identity between two producers (e.g. def and exp unset): exit, publication, pixels, STAR, log, console."""
    a, b = Path(run_a), Path(run_b)
    rep = dict(exit=[(x / "rc.txt").read_text().strip() for x in (a, b)])
    rep["same_exit"] = rep["exit"][0] == rep["exit"][1]
    for name in (f"{movie}.star", "corrected_micrographs.star", f"{movie}.log"):
        ta, tb = [(x / "out" / name).read_text() for x in (a, b)]
        rep[name] = normalise_console(ta, a / "out") == normalise_console(tb, b / "out")
    pa, pb = [read_mrc(x / "out" / f"{movie}.mrc")[0] for x in (a, b)]
    rep["pixels"] = bool(pa.shape == pb.shape and np.array_equal(pa, pb))
    # stdout is compared in order. stderr is compared as a multiset of lines: its lines come from the program and
    # from shell children (the PDF step) whose relative order is not deterministic; content must still match.
    n = lambda x, d: normalise_console((d / x).read_text(), d / "out")
    rep["stdout"] = n("stdout.txt", a) == n("stdout.txt", b)
    rep["stderr"] = sorted(n("stderr.txt", a).splitlines()) == sorted(n("stderr.txt", b).splitlines())
    rep["both_succeeded"] = rep["exit"] == ["0", "0"]   # two failures with the same status are not an identity
    rep["identical"] = rep["same_exit"] and rep["both_succeeded"] and all(
        rep[k] for k in rep if k not in ("exit", "same_exit", "both_succeeded"))
    return rep

