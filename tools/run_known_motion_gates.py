#!/usr/bin/env python3
"""One command: generate the known-motion fixtures, run MotionCorr, and gate the applied field.

    python3 tools/run_known_motion_gates.py --binary build/motioncorr --outdir /tmp/km59

Per case it runs, in this order:

  1. the declared command for that fixture (patch grid and defect policy come from the
     fixture's own ground-truth JSON, not from this script);
  2. the field gate, ``tools/check_known_motion.py``;
  3. a dose-weighted repeat, asserting the recovered field is bit-identical -- dose weighting
     is a post-alignment Fourier weight and cannot move anything;
  4. a four-thread repeat, asserting the same;
  5. on the defect-free cases, the applied-field self-consistency witness: the reported field is
     re-applied to the raw movie in Python and compared with the program's own summed image.

Exit status is 0 only if every case passes every gated metric.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import check_known_motion as ckm
import motion_field as mf


def run(cmd, cwd=None, log=None):
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if log:
        Path(log).write_text(f"$ {' '.join(map(str, cmd))}\n\n{proc.stdout}\n{proc.stderr}")
    return proc.returncode, time.time() - t0, proc


def motioncorr_cmd(binary, star, out, gt, threads=1, dose_weighting=False, gpu=None):
    rec = gt["recommended_run"]
    cmd = [str(binary), "--i", star, "--o", str(out), "--use_own", "--j", str(threads),
           "--patch_x", str(rec["patch_x"]), "--patch_y", str(rec["patch_y"]),
           "--bin_factor", str(rec["bin_factor"]), "--seed", "1", "--save_noDW"]
    if gpu is not None:
        cmd += ["--gpu", str(gpu)]
    if rec["skip_defect"]:
        cmd.append("--skip_defect")
    if dose_weighting:
        cmd += ["--dose_weighting",
                "--dose_per_frame", str(gt["geometry"]["dose_per_frame"]),
                "--voltage", str(gt["geometry"]["voltage_kv"]),
                "--angpix", str(gt["geometry"]["pixel_size_angstrom"])]
    return cmd


def backend_evidence(stdout: str, movie_log: str, gpu: int | None) -> dict:
    """Observe completion independently of optional detailed CUDA profiling."""
    cuda_startup = "Using CUDA acceleration on GPU device "
    cuda_completed = "[CUDA Global Alignment] completed;"
    if gpu is not None:
        startup = f"{cuda_startup}{gpu} for global alignment." in stdout
        completed = cuda_completed in movie_log
        return {"requested": "cuda", "gpu": gpu, "startup_marker_found": startup,
                "completion_marker_found": completed, "complete": startup and completed}
    unexpected = cuda_startup in stdout or "[CUDA " in movie_log
    movie_completed = re.search(r"^Full movie wall time:\s*([0-9.]+)\s+s\s*$",
                                movie_log, re.MULTILINE)
    completed = bool(movie_completed and math.isfinite(float(movie_completed.group(1))))
    return {"requested": "cpu", "selection": "--use_own without --gpu",
            "unexpected_cuda_marker": unexpected, "movie_completed": completed,
            "complete": completed and not unexpected}


def select_cases(fixtures: Path, requested: list[str] | None, include_heavy: bool) -> list:
    cases = {}
    for path in sorted(fixtures.glob("*_ground_truth.json")):
        gt = json.loads(path.read_text())
        case = gt["case"]
        if requested is not None and case not in requested:
            continue
        if gt["recommended_run"].get("heavy") and not include_heavy and requested is None:
            continue
        if case in cases:
            raise ValueError(f"duplicate fixture case: {case}")
        if gt["recommended_run"].get("role", "gate") not in ("gate", "characterization"):
            raise ValueError(f"invalid fixture role: {case}")
        cases[case] = (path, gt)
    missing = set(requested or []) - cases.keys()
    if missing:
        raise ValueError("requested fixtures missing: " + ", ".join(sorted(missing)))
    if not cases:
        raise ValueError("no fixtures selected; run the generator first")
    return list(cases.values())


def aggregate_status(results: list[dict]) -> str:
    gates = [r for r in results if r.get("role", "gate") == "gate"]
    # Characterization waives estimator-accuracy gates, never execution errors,
    # wrong backend, thread/dose differences or incorrect application of a field.
    valid = all(r["status"] != "ERROR" and r.get("implementation_status") == "PASS"
                for r in results)
    return "PASS" if gates and valid and all(r["status"] == "PASS" for r in gates) else "FAIL"


def run_case(args, gt_path: Path, gt: dict) -> dict:
    case = gt["case"]
    role = gt["recommended_run"].get("role", "gate")
    print(f"\n######## {case}  [{role}]")
    base = args.outdir / case
    if base.exists():
        shutil.rmtree(base)
    runs = {}
    for tag, threads, dw in (("j1", 1, False), ("j1_dw", 1, True), ("j4", 4, False)):
        out = base / tag
        out.mkdir(parents=True)
        cmd = motioncorr_cmd(args.binary, gt["input_star"], out, gt, threads, dw, args.gpu)
        rc, secs, proc = run(cmd, cwd=args.fixtures, log=out / "run.log")
        movie_log_path = out / f"{case}.log"
        movie_log = movie_log_path.read_text() if movie_log_path.exists() else ""
        evidence = backend_evidence(proc.stdout, movie_log, args.gpu)
        runs[tag] = {"command": cmd, "cwd": str(args.fixtures), "exit_code": rc,
                     "seconds": round(secs, 3), "motion_star": str(out / f"{case}.star"),
                     "backend_evidence": evidence}
        expected = [out / f"{case}.star", out / f"{case}.mrc", movie_log_path,
                    out / "corrected_micrographs.star"]
        if dw:
            expected.append(out / f"{case}_noDW.mrc")
        missing = [str(path) for path in expected if not path.is_file() or path.stat().st_size == 0]
        if rc != 0 or missing or not evidence["complete"]:
            return {"case": case, "role": role, "status": "ERROR", "implementation_status": "ERROR",
                    "reason": f"{tag}: exit={rc}, missing={missing}, backend={evidence}", "runs": runs}

    log_text = (base / "j1" / f"{case}.log").read_text()
    detected = None
    for line in log_text.splitlines():
        if "hot pixels to be corrected" in line:
            detected = int(line.split()[1])
    hot = {"expected": gt["recommended_run"]["expected_hot_pixels_detected"],
           "detected": detected if detected is not None else 0,
           "injected": gt["defects"]["n_hot_pixels"],
           "note": "noise pixels may also cross mean + 6 sigma; reported, not gated"}

    check_json = base / "gate.json"
    cmd = [args.python, str(REPO / "tools" / "check_known_motion.py"),
           "--ground-truth", str(gt_path), "--motion-star", runs["j1"]["motion_star"],
           "--compare-star", runs["j1_dw"]["motion_star"],
           "--compare-label", "dose_weighting_invariance", "--json", str(check_json)]
    # Hot-pixel replacement changes the input; the raw-movie witness applies only
    # to defect-free cases, where both correctors receive identical pixels.
    if gt["recommended_run"]["skip_defect"]:
        cmd += ["--movie", str(args.fixtures / gt["movie_file"]),
                "--summed-image", str(base / "j1" / f"{case}.mrc")]
    rc, _, proc = run(cmd, log=base / "gate.log")
    print(proc.stdout)
    if not check_json.is_file():
        raise ValueError(f"{case}: checker produced no JSON (exit {rc})")
    report = json.loads(check_json.read_text())
    status = report.get("status")
    if status not in ("PASS", "FAIL") or rc != (0 if status == "PASS" else 1):
        raise ValueError(f"{case}: invalid checker exit/status: {rc}/{status}: {report.get('error', '')}")

    s1 = mf.read_motion_star(runs["j1"]["motion_star"])
    s4 = mf.read_motion_star(runs["j4"]["motion_star"])
    dthread = ckm.compare_fields(gt, s1, s4)
    thread_inv = {"max_field_difference_px": dthread,
                  "max_field_difference_a": dthread * s1.pixel_size,
                  "limit_px": 0.0, "status": "IDENTICAL" if dthread == 0.0 else "DIFFERS",
                  "note": "the declared thread-invariance contract requires an identical field"}
    ckm.add_check(report["gates"], "thread_invariance", dthread == 0.0,
                  thread_inv["note"], value_a=dthread * s1.pixel_size,
                  value_px=dthread, limit_a=0.0, limit_px=0.0)
    report["thread_invariance"] = thread_inv
    report["status"] = report["gates"]["status"]
    # Keep the detailed case report and aggregate verdict in agreement.
    check_json.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    implementation_names = {"thread_invariance", "dose_weighting_invariance"}
    if gt["recommended_run"]["skip_defect"]:
        implementation_names.add("applied_image_self_consistency")
    by_name = {c["name"]: c for c in report["gates"]["checks"]}
    if not implementation_names <= by_name.keys():
        raise ValueError(f"{case}: missing required implementation checks")
    implementation_pass = all(by_name[name]["pass"] for name in implementation_names)
    print(f"  field difference j1 vs j4: {dthread:.3e} px -> {thread_inv['status']}")
    return {"case": case, "role": role, "status": report["status"], "runs": runs,
            "implementation_status": "PASS" if implementation_pass else "FAIL",
            "hot_pixels": hot, "thread_invariance": thread_inv, "gate_report": str(check_json),
            "summary": {c["name"]: {k: c[k] for k in ("value_a", "limit_a", "pass", "gated")}
                        for c in report["gates"]["checks"]},
            "self_consistency": report.get("self_consistency"),
            "dose_weighting_invariance": report.get("dose_weighting_invariance")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", type=Path, default=REPO / "build" / "motioncorr")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--gpu", type=int, default=None,
                    help="CUDA device index; omitted selects CPU")
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--fixtures", type=Path, default=REPO / "test-data" / "known_motion")
    ap.add_argument("--cases", nargs="+", default=None, help="default: every generated case")
    ap.add_argument("--include-heavy", action="store_true",
                    help="also generate and run the opt-in real-scale case (~400 MB, ~15 s)")
    ap.add_argument("--regenerate", action="store_true", default=True)
    ap.add_argument("--no-regenerate", dest="regenerate", action="store_false")
    ap.add_argument("--json", type=Path, help="aggregate machine-readable report")
    args = ap.parse_args()

    # All child commands may use a fixture cwd; resolve caller-relative paths now.
    args.binary = args.binary.resolve()
    args.outdir = args.outdir.resolve()
    args.fixtures = args.fixtures.resolve()
    if args.gpu is not None and args.gpu < 0:
        ap.error("--gpu must be a nonnegative CUDA device index")
    if not args.binary.is_file():
        print(f"ERROR: binary not found: {args.binary}", file=sys.stderr)
        return 2

    args.outdir.mkdir(parents=True, exist_ok=True)
    gen = REPO / "test-data" / "generate_known_motion_fixture.py"

    if args.regenerate:
        cmd = [args.python, str(gen), "--outdir", str(args.fixtures)]
        if args.include_heavy:
            cmd.append("--include-heavy")
        rc, _, proc = run(cmd, log=args.outdir / "generate.log")
        if rc != 0:
            print(proc.stdout + proc.stderr, file=sys.stderr)
            return 2

    try:
        cases = select_cases(args.fixtures, args.cases, args.include_heavy)
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    results = []
    for gt_path, gt in cases:
        try:
            result = run_case(args, gt_path, gt)
        except (OSError, ValueError, KeyError, IndexError, TypeError, OverflowError) as exc:
            result = {"case": gt["case"], "role": gt["recommended_run"].get("role", "gate"),
                      "status": "ERROR", "implementation_status": "ERROR", "reason": str(exc)}
            print(f"ERROR: {gt['case']}: {exc}", file=sys.stderr)
        results.append(result)

    overall = aggregate_status(results)
    print("\n" + "=" * 86)
    print(f" {'case':22s} {'role':17s} {'status':7s} {'global A':>9s} {'local A':>9s} {'total A':>9s}")
    for r in results:
        s = r.get("summary", {})
        def v(k):
            x = s.get(k, {}).get("value_a")
            return f"{x:9.4f}" if isinstance(x, float) else " " * 9
        print(f" {r['case']:22s} {r.get('role','gate'):17s} {r['status']:7s} "
              f"{v('global_component_rms')} {v('local_component_rms')} {v('total_rms_interior')}")
    print("\n Characterization accuracy failures remain visible. Execution, backend, applied-image")
    print(" and thread/dose-invariance failures always block the aggregate.")
    print(f"\n OVERALL: {overall}")
    print("=" * 86)

    if args.json:
        payload = {"tool": "run_known_motion_gates.py", "overall": overall,
                   "overall_scope": "gate-role accuracy plus execution/backend/invariance/witness "
                                    "checks on every requested case",
                   "binary": str(args.binary), "gpu": args.gpu, "results": results}
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
