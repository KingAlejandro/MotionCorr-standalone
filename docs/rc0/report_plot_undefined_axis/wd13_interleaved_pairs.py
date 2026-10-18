#!/usr/bin/env python3
"""W-D13 interleaved paired CPU timing driver for Issue #229 (D13 / D14).

DECLARED DESIGN (written to rule.txt and design.json before the first timed run):
  Venue & Lock:
    - Host: cpu64 (small-refmac-machine, 2x AMD EPYC 7763 64-Core, THP madvise,
      GLIBC_TUNABLES unset).
    - Mutex lock: /tmp/motioncorr-cpu64-bench.lock held via flock for the entire window.
  Arms & Binaries (matched Release builds, -O3 -DNDEBUG -std=gnu++17 -fopenmp, -DCUDA=OFF):
    - A  (main 1afa03b57afbae42138ee30c3545b57b5a74c321):
        /home/ubuntu/mc-w-d13/build-main/motioncorr
        sha256 307a030b03785201342a57c4d8adae14120d87676fa6bec7e62f8959d5b03a35
    - B  (fix  b82d25f4dda6bca746e4206fed1272851cc6a5ce):
        /home/ubuntu/mc-w-d13/build-fix/motioncorr
        sha256 68dc7ac11049bb15be3caa90af10adb6c7bb7e44b752d797080b9ca1a79d96f9
    - A2 (representing A', the identical main binary under a shell/gs-safe directory label):
        /home/ubuntu/mc-w-d13/build-main/motioncorr
        sha256 307a030b03785201342a57c4d8adae14120d87676fa6bec7e62f8959d5b03a35
  Affinity & Threads:
    - Payload pinned to CPUs 48-55 (single 8-core CCD on NUMA node 1, --j 8, OMP_NUM_THREADS=8).
    - Driver/sampler pinned to CPUs 56-59.
  Workload & Options (sized from the separate recorded pilot raw/cpu64_pilot/pilot_summary.json):
    - Input: 2-movie tutorial subset (movies2.star: 20170629_00021_frameImage.tiff,
      20170629_00022_frameImage.tiff + gain.mrc, staged in /dev/shm tmpfs).
    - Options: --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
      --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8
      (report generation ON: no --skip_report_pdf; generates logfile.pdf and all EPS plots).
  Pilot Sizing (from recorded pilot raw/cpu64_pilot/pilot_summary.json, not rerun):
    - Pilot 2-movie median(main) M = 17.5711 s, target T = 0.005 * M = 0.087856 s (+0.5%).
    - Pilot paired-difference spread: SD = 0.0477 s (0.271%), robust SD (1.4826*MAD) = 0.0544 s
      (0.310%). At N = 32 pairs, stats.median_ci uses order statistics [d(10), d(23)] (97.99%
      coverage, normal quantile z = 0.516), giving expected CI half-width 0.160% <= 0.50%
      (and normal-approximation 1.96 * 1.2533 * s / sqrt(32) = 0.0236 s = 0.134% <= 0.50%).
  Definitive Interleaved Schedule (run once, never extended):
    1. Warm-up: 1 run of A, 1 run of B (discarded from analysis, recorded in runs.jsonl).
    2. Definitive: N = 32 comparison pairs (16 AB / 16 BA) interleaved with N_null = 16 null
       pairs (8 AA' / 8 A'A), k = 2 (48 pairs = 96 runs total):
       - 16 comparison blocks blk = 1..16, each block is [AB, BA].
       - After every k = 2-nd comparison block (blk in {2, 4, 6, 8, 10, 12, 14, 16}),
         run one null block [AA', A'A].
       - The last null block (blk = 16, positions 47-48) follows the last comparison block
         (blk = 16, positions 45-46).
       - Per-pair differences:
           comparison pair (AB or BA): d  = wall(B)  - wall(A)
           null pair       (AA' or A'A): d0 = wall(A') - wall(A)
  Exclusion & Immediate Same-Position Retry Rule:
    - Before each run, wait up to 300 s for foreign CPU on lane 48-55 <= 0.25 cores.
    - A pair is discarded only if either run in the pair has:
        * non-zero exit status (rc != 0),
        * fewer than 2 MRC products or missing/empty logfile.pdf,
        * unverified executable path (/proc/<pid>/exe != realpath(binary)),
        * payload CPU affinity mismatch (/proc/<pid>/status != [48,49,50,51,52,53,54,55]), or
        * recorded foreign CPU > 0.25 cores on lane 48-55 during the run.
    - A discarded pair is rerun immediately in the exact same position and order, up to
      MAX_ATTEMPTS = 3 attempts; if all 3 attempts fail, the run stops and is reported incomplete.
  D14 Decision Rule:
    - PASS:       no resolved slowdown, and upper >=95% CI bound of median(d) <= +0.5% of median(wall A).
    - UNRESOLVED: no resolved slowdown, and upper >=95% CI bound of median(d) > +0.5% of median(wall A).
    - FAIL:       resolved slowdown (CI lower bound > 0 and |median(d)| > noise).
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TARGET_FRAC = 0.005
N_COMP = 32
N_NULL = 16
K_BLOCKS = 2
MAX_ATTEMPTS = 3
FOREIGN_LANE_CORES_LIMIT = 0.25


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", default="tutorial_2mov")
    ap.add_argument("--a", required=True, help="main binary path")
    ap.add_argument("--b", required=True, help="fix binary path")
    ap.add_argument("--data", required=True, help="staged data directory")
    ap.add_argument("--star", default="movies2.star")
    ap.add_argument("--cpus", default="48-55")
    ap.add_argument("--runner-cpus", default="56-59")
    ap.add_argument("--src", required=True, help="source tree containing tools/profiling")
    ap.add_argument("--pilot-summary", required=True, help="path to recorded pilot_summary.json")
    ap.add_argument("--out", required=True, help="output directory for records")
    ap.add_argument("--scratch", required=True, help="tmpfs scratch directory for run outputs")
    ap.add_argument("args", nargs=argparse.REMAINDER)
    o = ap.parse_args()

    mc_args = [x for x in o.args if x != "--"]
    sys.path.insert(0, str(Path(o.src) / "tools" / "profiling"))
    from lib import identity, provenance as prov, runner, stats  # noqa: E402

    lane = prov.cpu_list(o.cpus)
    runner_lane = prov.cpu_list(o.runner_cpus)
    if runner_lane and hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, runner_lane)

    out = Path(o.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    scratch = Path(o.scratch).resolve()
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True, exist_ok=True)

    # 1. Write rule.txt and design.json BEFORE the first timed run and record timestamps.
    rule_path = out / "rule.txt"
    rule_path.write_text(__doc__.strip() + "\n")

    pilot_data = json.loads(Path(o.pilot_summary).read_text())["pilot_2mov"]
    pilot_s = float(pilot_data["robust_sd_mad_s"])
    pilot_sd = float(pilot_data["sd_diff_s"])
    pilot_m = float(pilot_data["main_median_s"])
    target_s = TARGET_FRAC * pilot_m

    # Build the exact 48-pair interleaved plan:
    # 16 comparison blocks [AB, BA]; after every k=2 blocks, 1 null block [AA', A'A].
    # Use safe directory token "A2" for A' so no path ever contains a single quote.
    A = ("A", "A", os.path.abspath(o.a))
    B = ("B", "B", os.path.abspath(o.b))
    A_prime = ("A'", "A2", os.path.abspath(o.a))

    plan = []
    nulls_scheduled = 0
    for blk in range(1, N_COMP // 2 + 1):
        plan.append((A, B, "comp", "AB", blk))
        plan.append((B, A, "comp", "BA", blk))
        if blk % K_BLOCKS == 0 and nulls_scheduled < N_NULL // 2:
            nulls_scheduled += 1
            plan.append((A, A_prime, "null", "AA'", blk))
            plan.append((A_prime, A, "null", "A'A", blk))

    assert len(plan) == N_COMP + N_NULL == 48, f"unexpected plan length {len(plan)}"
    assert sum(1 for _, _, k, ord_, _ in plan if k == "comp" and ord_ == "AB") == 16
    assert sum(1 for _, _, k, ord_, _ in plan if k == "comp" and ord_ == "BA") == 16
    assert sum(1 for _, _, k, ord_, _ in plan if k == "null" and ord_ == "AA'") == 8
    assert sum(1 for _, _, k, ord_, _ in plan if k == "null" and ord_ == "A'A") == 8
    assert plan[-2][2] == "null" and plan[-1][2] == "null", "last block must be null block"

    design = {
        "declared_at_utc": utc_now(),
        "workload": o.name,
        "star": o.star,
        "cpus_payload": lane,
        "cpus_runner": runner_lane,
        "binary_A_main": {"path": A[2], "sha256": prov.sha256_file(A[2])},
        "binary_B_fix": {"path": B[2], "sha256": prov.sha256_file(B[2])},
        "binary_A_prime": {"label": "A'", "dir_tag": "A2", "path": A_prime[2], "sha256": prov.sha256_file(A_prime[2])},
        "pilot_reference": {
            "source_file": str(Path(o.pilot_summary).resolve()),
            "pilot_pairs": pilot_data["n_pairs"],
            "pilot_main_median_s": pilot_m,
            "pilot_sd_diff_s": pilot_sd,
            "pilot_robust_sd_mad_s": pilot_s,
            "pilot_rel_sigma_per_sqrt_min_pct": pilot_data["rel_sigma_per_sqrt_min_pct"],
        },
        "d14_margin_pct": TARGET_FRAC * 100.0,
        "pilot_target_s": round(target_s, 6),
        "N_comparison_pairs": N_COMP,
        "N_AB": 16,
        "N_BA": 16,
        "N_null_pairs": N_NULL,
        "N_AA_prime": 8,
        "N_A_prime_A": 8,
        "interleaving_k_blocks": K_BLOCKS,
        "total_definitive_pairs": len(plan),
        "max_attempts_per_pair": MAX_ATTEMPTS,
        "foreign_lane_cores_limit": FOREIGN_LANE_CORES_LIMIT,
        "plan_orders": [
            {"position": idx + 1, "kind": kind, "order": order_lbl, "after_comp_block": blk}
            for idx, (_, _, kind, order_lbl, blk) in enumerate(plan)
        ],
    }
    design_path = out / "design.json"
    design_path.write_text(json.dumps(design, indent=2) + "\n")

    script_path = Path(__file__).resolve()
    timestamps = {
        "recorded_before_first_run_utc": utc_now(),
        "script_path": str(script_path),
        "script_mtime_utc": datetime.datetime.fromtimestamp(
            script_path.stat().st_mtime, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "rule_txt_path": str(rule_path),
        "rule_txt_mtime_utc": datetime.datetime.fromtimestamp(
            rule_path.stat().st_mtime, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "design_json_path": str(design_path),
        "design_json_mtime_utc": datetime.datetime.fromtimestamp(
            design_path.stat().st_mtime, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    (out / "declared_timestamps.json").write_text(json.dumps(timestamps, indent=2) + "\n")
    print("DECLARED_TIMESTAMPS", json.dumps(timestamps), flush=True)

    runs_log = open(out / "runs.jsonl", "w")
    pairs_log = open(out / "pairs.jsonl", "w")
    seq = [0]

    def emit_run(rec: dict) -> None:
        runs_log.write(json.dumps(rec) + "\n")
        runs_log.flush()

    def emit_pair(rec: dict) -> None:
        pairs_log.write(json.dumps(rec) + "\n")
        pairs_log.flush()

    def run_single(phase: str, arm_spec: tuple[str, str, str], pos: int, attempt: int, keep: bool = False):
        label, dir_tag, binary = arm_spec
        seq[0] += 1
        run_id = f"{seq[0]:04d}-p{pos:02d}-a{attempt}-{dir_tag}"
        dst = scratch / run_id / "out"
        dst.mkdir(parents=True, exist_ok=True)
        log_file = scratch / run_id / "run.log"

        quiet = runner.wait_quiet_lane(lane, 300.0, FOREIGN_LANE_CORES_LIMIT)
        load_before = os.getloadavg()[0]
        comp_before = prov.compilers_running()
        j0 = prov.lane_jiffies(lane)
        t_start_utc = utc_now()
        t0 = time.monotonic()

        argv = [
            "taskset", "-c", ",".join(map(str, lane)),
            binary, "--i", o.star, "--o", str(dst) + "/",
        ] + mc_args

        with open(log_file, "w") as lf:
            p = subprocess.Popen(argv, cwd=o.data, stdout=lf, stderr=subprocess.STDOUT)
            exe = None
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    exe = os.path.realpath(f"/proc/{p.pid}/exe") if os.path.exists(f"/proc/{p.pid}") else None
                except OSError:
                    exe = None
                if exe is None or exe == os.path.realpath(binary):
                    break
                time.sleep(0.002)
            try:
                affinity = sorted(os.sched_getaffinity(p.pid))
            except (AttributeError, OSError):
                affinity = None
            _, status, ru = os.wait4(p.pid, 0)

        wall = time.monotonic() - t0
        t_end_utc = utc_now()
        j1 = prov.lane_jiffies(lane)
        rc = os.waitstatus_to_exitcode(status)
        user_s = float(ru.ru_utime)
        sys_s = float(ru.ru_stime)
        cpu_s = user_s + sys_s
        hz = prov.clock_ticks()
        busy_s = (j1["busy"] - j0["busy"]) / hz if (j0 and j1) else cpu_s
        foreign_s = max(0.0, busy_s - cpu_s)
        foreign_cores = foreign_s / wall if wall > 0 else 0.0

        mrc_count = runner.count_mrc(str(dst)) if rc == 0 else 0
        pdf_path = dst / "logfile.pdf"
        pdf_bytes = pdf_path.stat().st_size if pdf_path.is_file() else 0
        exe_ok = (exe == os.path.realpath(binary)) if exe is not None else False
        aff_ok = (affinity == sorted(lane)) if affinity is not None else False

        violations = []
        if rc != 0:
            violations.append(f"rc={rc}")
        if mrc_count < 2:
            violations.append(f"mrc_products={mrc_count}<2")
        if pdf_bytes <= 0:
            violations.append("missing_or_empty_logfile_pdf")
        if not exe_ok:
            violations.append(f"exe_mismatch:{exe}")
        if not aff_ok:
            violations.append(f"affinity_mismatch:{affinity}")
        if foreign_cores > FOREIGN_LANE_CORES_LIMIT:
            violations.append(f"foreign_lane_cores={foreign_cores:.4f}>{FOREIGN_LANE_CORES_LIMIT}")
        if quiet.get("timed_out"):
            violations.append("lane_wait_timed_out")

        rec = {
            "seq": seq[0],
            "phase": phase,
            "position": pos,
            "attempt": attempt,
            "arm": label,
            "dir_tag": dir_tag,
            "start_utc": t_start_utc,
            "end_utc": t_end_utc,
            "rc": rc,
            "wall_s": wall,
            "user_s": user_s,
            "sys_s": sys_s,
            "cpu_s": cpu_s,
            "peak_rss_bytes": int(ru.ru_maxrss) * 1024,
            "minflt": int(ru.ru_minflt),
            "majflt": int(ru.ru_majflt),
            "lane_busy_s": busy_s,
            "lane_foreign_s": foreign_s,
            "lane_foreign_cores": foreign_cores,
            "lane_before": quiet,
            "load1_before": load_before,
            "load1_after": os.getloadavg()[0],
            "compilers_before": comp_before,
            "compilers_after": prov.compilers_running(),
            "payload_exe_verified": exe_ok,
            "payload_affinity": affinity,
            "mrc_products": mrc_count,
            "logfile_pdf_bytes": pdf_bytes,
            "violations": violations,
        }
        emit_run(rec)
        print(
            f"wd13: seq={seq[0]:03d} {phase:<10} pos={pos:02d} att={attempt} arm={label:<2} "
            f"wall={wall:.3f}s foreign={foreign_cores:.3f}c violations={violations}",
            flush=True,
        )
        if not keep:
            shutil.rmtree(scratch / run_id, ignore_errors=True)
        return rec, dst, scratch / run_id

    # 2. Warmup runs (1 of A, 1 of B), discarded from analysis.
    run_single("warmup", A, 0, 1, keep=False)
    run_single("warmup", B, 0, 1, keep=False)

    # 3. Definitive interleaved schedule (48 pairs: 32 comp + 16 null).
    comp_pairs = []
    null_pairs = []
    walls_a_comp = []
    walls_b_comp = []
    walls_a_null = []
    walls_a2_null = []
    ident = None
    incomplete = None
    discarded_attempts = 0

    for idx, (first, second, kind, order_lbl, blk) in enumerate(plan):
        pos = idx + 1
        keep_for_ident = (ident is None and kind == "comp" and order_lbl == "AB")
        retained = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            r1, d1, root1 = run_single("definitive", first, pos, attempt, keep=keep_for_ident)
            r2, d2, root2 = run_single("definitive", second, pos, attempt, keep=keep_for_ident)
            ok = (not r1["violations"]) and (not r2["violations"])
            pair_rec = {
                "position": pos,
                "after_comp_block": blk,
                "kind": kind,
                "order": order_lbl,
                "attempt": attempt,
                "retained": ok,
                "first_seq": r1["seq"],
                "second_seq": r2["seq"],
                "first_arm": first[0],
                "second_arm": second[0],
                "first_wall_s": r1["wall_s"],
                "second_wall_s": r2["wall_s"],
                "violations_first": r1["violations"],
                "violations_second": r2["violations"],
            }
            if ok:
                w_map = {first[0]: r1["wall_s"], second[0]: r2["wall_s"]}
                if kind == "comp":
                    d_val = w_map["B"] - w_map["A"]
                    pair_rec["d_s"] = d_val
                    comp_pairs.append({
                        "position": pos,
                        "block": blk,
                        "order": order_lbl,
                        "attempt": attempt,
                        "A_s": w_map["A"],
                        "B_s": w_map["B"],
                        "d_s": d_val,
                    })
                    walls_a_comp.append(w_map["A"])
                    walls_b_comp.append(w_map["B"])
                else:
                    d0_val = w_map["A'"] - w_map["A"]
                    pair_rec["d0_s"] = d0_val
                    null_pairs.append({
                        "position": pos,
                        "after_comp_block": blk,
                        "order": order_lbl,
                        "attempt": attempt,
                        "A_s": w_map["A"],
                        "A_prime_s": w_map["A'"],
                        "d0_s": d0_val,
                    })
                    walls_a_null.append(w_map["A"])
                    walls_a2_null.append(w_map["A'"])

                if keep_for_ident:
                    ident = identity.compare_trees(str(d1), str(d2))
                    (out / "identity.json").write_text(json.dumps(ident, indent=2) + "\n")
                    shutil.rmtree(root1, ignore_errors=True)
                    shutil.rmtree(root2, ignore_errors=True)
                    if not ident.get("identical"):
                        incomplete = f"identity failure at position {pos}: {ident.get('problems')}"
                emit_pair(pair_rec)
                retained = True
                break
            else:
                discarded_attempts += 1
                emit_pair(pair_rec)
                if keep_for_ident:
                    shutil.rmtree(root1, ignore_errors=True)
                    shutil.rmtree(root2, ignore_errors=True)

        if not retained or incomplete:
            if not incomplete:
                incomplete = f"position {pos} ({kind} {order_lbl}) failed {MAX_ATTEMPTS} attempts"
            break

    runs_log.close()
    pairs_log.close()
    shutil.rmtree(scratch, ignore_errors=True)

    d = [c["d_s"] for c in comp_pairs]
    d0 = [x["d0_s"] for x in null_pairs]
    ci = stats.median_ci(d) if len(d) >= stats.MIN_PAIRS else None
    ci0 = stats.median_ci(d0) if len(d0) >= stats.MIN_PAIRS else None

    med_a = stats.median(walls_a_comp) if walls_a_comp else None
    med_b = stats.median(walls_b_comp) if walls_b_comp else None
    iqr_a = stats.iqr(walls_a_comp) if len(walls_a_comp) >= 4 else None
    iqr_b = stats.iqr(walls_b_comp) if len(walls_b_comp) >= 4 else None

    med_a_null = stats.median(walls_a_null) if walls_a_null else None
    med_a2_null = stats.median(walls_a2_null) if walls_a2_null else None
    iqr_a_null = stats.iqr(walls_a_null) if len(walls_a_null) >= 4 else None
    iqr_a2_null = stats.iqr(walls_a2_null) if len(walls_a2_null) >= 4 else None

    med_d = stats.median(d) if d else None
    noise_d = stats.robust_sd(d) if len(d) >= 2 else None
    sign_d = stats.sign_test(d) if d else None
    q1_d, _, q3_d = stats.quartiles(d) if len(d) >= 4 else (None, None, None)

    med_d0 = stats.median(d0) if d0 else None
    noise_d0 = stats.robust_sd(d0) if len(d0) >= 2 else None
    sign_d0 = stats.sign_test(d0) if d0 else None
    q1_d0, _, q3_d0 = stats.quartiles(d0) if len(d0) >= 4 else (None, None, None)

    ci_lo_pct = (100.0 * ci[0] / med_a) if (ci and med_a) else None
    ci_hi_pct = (100.0 * ci[1] / med_a) if (ci and med_a) else None
    med_d_pct = (100.0 * med_d / med_a) if (med_d is not None and med_a) else None
    d14_threshold_s = TARGET_FRAC * med_a if med_a else None

    if incomplete is not None or ci is None or med_a is None:
        d14_label = "UNRESOLVED"
    elif ci[0] > 0.0 and abs(med_d) > noise_d:
        d14_label = "FAIL"
    elif ci_hi_pct <= TARGET_FRAC * 100.0:
        d14_label = "PASS"
    else:
        d14_label = "UNRESOLVED"

    result = {
        "completed_at_utc": utc_now(),
        "workload": o.name,
        "incomplete": incomplete,
        "discarded_pair_attempts": discarded_attempts,
        "d14_margin_pct": TARGET_FRAC * 100.0,
        "d14_threshold_s": d14_threshold_s,
        "d14_label": d14_label,
        "comparison": {
            "n_pairs": len(d),
            "n_AB": sum(1 for c in comp_pairs if c["order"] == "AB"),
            "n_BA": sum(1 for c in comp_pairs if c["order"] == "BA"),
            "arm_A_main": {
                "n": len(walls_a_comp),
                "median_s": med_a,
                "iqr_s": iqr_a,
                "min_s": min(walls_a_comp) if walls_a_comp else None,
                "max_s": max(walls_a_comp) if walls_a_comp else None,
            },
            "arm_B_fix": {
                "n": len(walls_b_comp),
                "median_s": med_b,
                "iqr_s": iqr_b,
                "min_s": min(walls_b_comp) if walls_b_comp else None,
                "max_s": max(walls_b_comp) if walls_b_comp else None,
            },
            "median_d_s": med_d,
            "median_d_pct": med_d_pct,
            "ci_s": [ci[0], ci[1]] if ci else None,
            "ci_pct": [ci_lo_pct, ci_hi_pct] if ci else None,
            "ci_confidence": ci[2] if ci else None,
            "q1_d_s": q1_d,
            "q3_d_s": q3_d,
            "iqr_d_s": (q3_d - q1_d) if (q1_d is not None and q3_d is not None) else None,
            "range_d_s": [min(d), max(d)] if d else None,
            "noise_mad_sd_s": noise_d,
            "noise_mad_sd_pct": (100.0 * noise_d / med_a) if (noise_d is not None and med_a) else None,
            "sign_test": sign_d,
            "diffs_s": d,
        },
        "interleaved_null": {
            "n_pairs": len(d0),
            "n_AA_prime": sum(1 for x in null_pairs if x["order"] == "AA'"),
            "n_A_prime_A": sum(1 for x in null_pairs if x["order"] == "A'A"),
            "arm_A_main": {
                "n": len(walls_a_null),
                "median_s": med_a_null,
                "iqr_s": iqr_a_null,
                "min_s": min(walls_a_null) if walls_a_null else None,
                "max_s": max(walls_a_null) if walls_a_null else None,
            },
            "arm_A_prime_main": {
                "n": len(walls_a2_null),
                "median_s": med_a2_null,
                "iqr_s": iqr_a2_null,
                "min_s": min(walls_a2_null) if walls_a2_null else None,
                "max_s": max(walls_a2_null) if walls_a2_null else None,
            },
            "median_d0_s": med_d0,
            "median_d0_pct": (100.0 * med_d0 / med_a_null) if (med_d0 is not None and med_a_null) else None,
            "ci_s": [ci0[0], ci0[1]] if ci0 else None,
            "ci_pct": [100.0 * ci0[0] / med_a_null, 100.0 * ci0[1] / med_a_null] if (ci0 and med_a_null) else None,
            "ci_confidence": ci0[2] if ci0 else None,
            "q1_d0_s": q1_d0,
            "q3_d0_s": q3_d0,
            "iqr_d0_s": (q3_d0 - q1_d0) if (q1_d0 is not None and q3_d0 is not None) else None,
            "range_d0_s": [min(d0), max(d0)] if d0 else None,
            "max_abs_d0_s": max(abs(x) for x in d0) if d0 else None,
            "max_abs_d0_pct": (100.0 * max(abs(x) for x in d0) / med_a_null) if (d0 and med_a_null) else None,
            "noise_mad_sd_s": noise_d0,
            "sign_test": sign_d0,
            "diffs_s": d0,
        },
        "identity_first_AB": {
            "identical": (ident or {}).get("identical"),
            "compared": (ident or {}).get("compared"),
            "mrc_compared": (ident or {}).get("mrc_compared"),
            "problems": (ident or {}).get("problems"),
        },
        "comparison_pairs": comp_pairs,
        "null_pairs": null_pairs,
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("INTERLEAVED_RESULT", json.dumps({
        "d14_label": d14_label,
        "comp_pairs": len(d),
        "null_pairs": len(d0),
        "main_median_s": med_a,
        "fix_median_s": med_b,
        "median_d_s": med_d,
        "median_d_pct": med_d_pct,
        "ci_s": [ci[0], ci[1]] if ci else None,
        "ci_pct": [ci_lo_pct, ci_hi_pct] if ci else None,
        "ci_confidence": ci[2] if ci else None,
        "null_median_s": med_d0,
        "null_ci_s": [ci0[0], ci0[1]] if ci0 else None,
        "null_range_s": [min(d0), max(d0)] if d0 else None,
        "identity_identical": (ident or {}).get("identical"),
    }, indent=2), flush=True)
    return 0 if incomplete is None else 1


if __name__ == "__main__":
    sys.exit(main())
