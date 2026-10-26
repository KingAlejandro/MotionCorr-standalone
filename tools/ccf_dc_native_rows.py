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

def k267_argv(binary, case, outdir, backend):
    """Native K267 command, 3x3 patches for every ID (the retained run used 1x1 for five of them, which never runs
    the local stage and so cannot exercise the local or both arms). Product log kept (no --skip_logfile)."""
    argv = [str(binary), "--i", f"{case}.star", "--o", str(outdir), "--use_own", "--j", "8", "--patch_x", "3",
            "--patch_y", "3", "--bin_factor", "1", "--seed", "1", "--skip_defect", "--save_noDW",
            "--first_frame_sum", "1", "--last_frame_sum", "5"]
    return argv + (["--gpu", "0"] if backend == "cuda" else [])


def n_argv(binary, name, frames, outdir, backend):
    """Retained N-control command (`--j 2`, 1x1 patches, `--last_frame_sum N`), with the product log kept."""
    argv = [str(binary), "--i", f"{name}.star", "--o", str(outdir), "--use_own", "--j", "2", "--patch_x", "1",
            "--patch_y", "1", "--bin_factor", "1", "--seed", "1", "--skip_defect", "--save_noDW",
            "--first_frame_sum", "1", "--last_frame_sum", str(frames)]
    return argv + (["--gpu", "0"] if backend == "cuda" else [])


def run_env(arm, report, tap=None, cuda_uuid=None):
    """Environment for one producer; arm None means unset (identity rows). Report/tap only on experiment builds."""
    env = {"OMP_NUM_THREADS": "8"}
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
                want_zero = c["frames_eligible"] if sel[stage] else 0
                if c["frames_zeroed"] != want_zero:
                    bad.append(f"{site}.{stage} zeroed {c['frames_zeroed']} != {want_zero}")
            elif c["frames_eligible"] != 0:
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
        if row["witness_status"] == "INVALID":
            return dict(row, row_status="INVALID", reason="; ".join(row["witness_reasons"])), False
    row["convergence"] = convergence_of(run / "out" / f"{movie}.log")
    return row, True


def _finish(row):
    row["row_status"] = "INCONCLUSIVE" if row.get("witness_status") == "INCONCLUSIVE" else "SCORED"
    if row["row_status"] == "INCONCLUSIVE":
        row["reason"] = "; ".join(row["witness_reasons"])
    return row


def grade_k267(run, fixtures, case, backend, arm, iso_expected=False, has_witness=True, stages=("global", "local")):
    run, fixtures = Path(run), Path(fixtures)
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
    if has_witness and (run / "tap.json").exists():
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
            row["tap"] = cmd.check_case(fixtures, case, cand)
        except bridge.TapError as e:
            return dict(row, row_status="INVALID", reason=f"tap: {e}")
        except Exception as e:
            row["tap"] = dict(checker_error=f"{type(e).__name__}: {e}")
    return _finish(row)


def n_score(global_shifts, truth_px):
    """Field metrics for a spatially constant field: ROI is immaterial, gauge is frame 0 (shift 0 by construction)."""
    err = (np.asarray(global_shifts, dtype=float) - np.asarray(truth_px, dtype=float)) * PIXEL_SIZE
    m = cmd.vector_metrics(err)
    ok = m["rms"] <= LIMITS_A[0] and m["p95"] <= LIMITS_A[1] and m["max"] <= LIMITS_A[2]
    return dict(rms=m["rms"], p95=m["p95"], max=m["max"], verdict="PASS" if ok else "FAIL")


def grade_n(run, controls, name, backend, arm, iso_expected=False, has_witness=True):
    run, controls = Path(run), Path(controls)
    man = json.loads((controls / "MANIFEST.json").read_text())["cases"][name]
    row, ok = _head(run, name, backend, arm, {"global"}, iso_expected, has_witness)
    row["tier"] = "N"
    if not ok:
        return row
    truth = np.load(controls / f"{name}_truth.npy", allow_pickle=False)   # scoring stage only
    s = read_motion_star(run / "out" / f"{name}.star")
    star_g = np.stack((s.global_shift_x, s.global_shift_y), axis=-1)
    row["STAR"] = n_score(star_g, truth)
    row["traj_rms_px_STAR"] = float(np.sqrt(np.mean((star_g - truth) ** 2) * 2))
    if has_witness and (run / "tap.json").exists():
        try:
            tap = bridge.load_tap(run / "tap.json", man["frames"])
        except bridge.TapError as e:
            return dict(row, row_status="INVALID", reason=f"tap: {e}")
        g = np.array(tap["global"])
        row["runtime"] = n_score(g, truth)
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
    rep["identical"] = rep["same_exit"] and all(rep[k] for k in rep if k not in ("exit", "same_exit"))
    return rep

