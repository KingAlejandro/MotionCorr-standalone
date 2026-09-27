#!/usr/bin/env python3
"""Render the compact issue #83 support table from raw per-case reports.

Implementation coverage and numerical gates are printed as separate tables and
separate verdicts. A declared row with no raw result is printed as ``unrun``;
it is never folded into a pass, and the presence of any unrun row suppresses
the aggregate "supported" claim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matrix as declared  # noqa: E402

STATUS_CELL = {"pass": "pass", "fail": "**FAIL**", "error": "**ERROR**",
               "unrun": "_unrun_"}


def load(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text())


def schedule_cell(entry: Dict[str, Any], schedule: str) -> str:
    sched = entry.get("schedules", {}).get(schedule)
    if sched is None:
        return "_unrun_"
    if sched.get("passed") is True:
        moved = sched.get("movies_passed")
        total = sched.get("movies_compared")
        return f"exact {moved}/{total}" if total else "exact"
    if "passed" not in sched:
        return "n/a"
    return "**FAIL**"


def render_matrix(report: Optional[Dict[str, Any]]) -> List[str]:
    # On a CPU run the absence of a CUDA marker is the required result, not a
    # failure, so the witness column is labelled by the backend that was used.
    device = (report or {}).get("provenance", {}).get("gpu")
    on_gpu = device is not None
    heading = (f"### Implementation coverage (native CUDA, device {device})" if on_gpu
               else "### Implementation coverage (CPU backend — separate diagnostic)")
    witness_column = "Native witness" if on_gpu else "CUDA marker absent"
    lines = [heading, "",
             "Exact = every movie identical to the uninterrupted run under "
             "`compare_motioncorr.py --gate exact`.", ""]
    if not on_gpu:
        lines += ["This run used the CPU backend. A CUDA marker here would mean "
                  "a masquerading run, so the column below requires its "
                  "**absence**.", ""]
    lines += [f"| Row | Axes | {witness_column} | Products | Repeat | Batch "
              "| Resume (non-prefix) | Verdict |",
              "|---|---|---|---|---|---|---|---|"]
    by_id: Dict[str, Dict[str, Any]] = {}
    if report:
        by_id = {r["row_id"]: r for r in report.get("results", [])}

    for row in declared.ROWS:
        entry = by_id.get(row.row_id)
        axes = ", ".join(f"{k}={v}" for k, v in row.axes.items())
        if entry is None:
            lines.append(f"| `{row.row_id}` | {axes} | _unrun_ | _unrun_ | _unrun_ "
                         f"| _unrun_ | _unrun_ | {STATUS_CELL['unrun']} |")
            continue
        base = entry.get("schedules", {}).get("base", {})
        witness = base.get("backend_evidence", {})
        if row.expect_reject:
            reject = entry.get("schedules", {}).get("reject", {})
            native = "n/a (rejected)"
            productcell = (f"rc={reject.get('returncode')}, "
                           f"named={reject.get('option_named')}")
            repeat = batch = resume = "n/a"
        else:
            if on_gpu:
                native = "yes" if witness.get("native_cuda_proven") else "**no**"
            else:
                native = ("**masquerade**" if witness.get("unexpected_cuda_marker")
                          else "confirmed absent")
            inventory = base.get("inventory", {})
            productcell = ("complete" if inventory.get("inventory_complete")
                           else "**incomplete**")
            repeat = schedule_cell(entry, "repeat")
            batch = schedule_cell(entry, "batch")
            resume = schedule_cell(entry, "resume")
        lines.append(f"| `{row.row_id}` | {axes} | {native} | {productcell} | "
                     f"{repeat} | {batch} | {resume} | "
                     f"{STATUS_CELL.get(entry.get('status'), entry.get('status'))} |")
    return lines


def render_all24(report: Optional[Dict[str, Any]]) -> List[str]:
    lines = ["", "### Integrated candidate: all 24 tutorial movies", ""]
    if report is None:
        lines += ["_unrun_: no all-24 schedule-equality report was produced.", ""]
        return lines
    lines += [f"- Movies in STAR: {report.get('movies_in_star')} "
              f"(expected {report.get('expected_movies')})",
              f"- Aggregate equality: "
              f"{'pass' if report.get('all24_equal') else '**FAIL**'}", "",
              "| Schedule | Runs | Movies exact | Missing pairs | Verdict |",
              "|---|---:|---|---|---|"]
    for name, entry in report.get("schedules", {}).items():
        if name == "base":
            witness = entry.get("backend_evidence", {})
            lines.append(f"| base (uninterrupted) | 1 | "
                         f"{entry.get('movies_present')} present | "
                         f"{'0' if not entry.get('inventory_errors') else 'see raw'} | "
                         f"native witness: "
                         f"{'yes' if witness.get('native_cuda_proven') else '**no**'} |")
            continue
        missing = entry.get("missing_pairs") or []
        lines.append(f"| {name} | {len(entry.get('runs', []))} | "
                     f"{entry.get('movies_passed')}/{entry.get('movies_compared')} | "
                     f"{len(missing)} | "
                     f"{'pass' if entry.get('passed') else '**FAIL**'} |")
    if report.get("errors"):
        lines += ["", "Errors:"] + [f"- {e}" for e in report["errors"][:20]]
    return lines


def render_capacity(capacity: Optional[Dict[str, Any]]) -> List[str]:
    """One measured capacity datapoint, stated only for what was measured."""
    lines = ["", "### Memory capacity (measured, single datapoint)", ""]
    if capacity is None:
        lines += ["_unrun_: no capacity measurement was taken. No capacity "
                  "claim is made.", ""]
        return lines
    lines += [f"- Configuration: `{capacity.get('row_id')}` — "
              f"{capacity.get('geometry')}, {capacity.get('frames')} frames, "
              f"{capacity.get('patches')}",
              f"- Device: {capacity.get('device')} "
              f"({capacity.get('device_total_mib')} MiB total)",
              f"- **Peak device memory observed: "
              f"{capacity.get('peak_used_mib')} MiB**, sampled every "
              f"{capacity.get('sample_interval_sec')} s over "
              f"{capacity.get('samples')} samples",
              f"- Run exit status: {capacity.get('returncode')}",
              "",
              "This is a measurement of one configuration on one device, not a "
              "capacity claim for other geometries, frame counts or devices. "
              "No universal CPU-fallback behaviour is claimed, and no fallback "
              "is inferred from any exit status.", ""]
    return lines


def render_deferred() -> List[str]:
    lines = ["", "### Deliberately not attempted here", "",
             "Named rather than implied, so the table is not read as broader "
             "than it is.", "",
             "| Coverage | Owner | Why |", "|---|---|---|"]
    for title, owner, why in declared.DEFERRED:
        lines.append(f"| {title} | {owner} | {why} |")
    return lines


def render_numerical(truth: Optional[Dict[str, Any]],
                     cpu_diag: Optional[Dict[str, Any]]) -> List[str]:
    lines = ["", "### Numerical gates (separate verdicts)", "",
             "These are not implied by any implementation row above.", ""]
    if truth is None:
        lines.append("- Motion truth (`run_known_motion_gates.py`): _unrun_.")
    else:
        results = truth.get("results", {})
        items = results.items() if isinstance(results, dict) else \
            ((r.get("case"), r) for r in results)
        for case, entry in items:
            verdict = entry.get("verdict") or entry.get("status") or entry.get("result")
            role = entry.get("role", "")
            lines.append(f"- Motion truth `{case}` ({role}): **{verdict}**")
    if cpu_diag is None:
        lines.append("- CPU-backend diagnostic: _unrun_ in this report.")
    else:
        counts = cpu_diag.get("counts", {})
        unrun = cpu_diag.get("unrun_rows", [])
        host = cpu_diag.get("provenance", {}).get("hostname", "unknown host")
        lines.append(
            f"- CPU-backend diagnostic (`{host}`): {counts.get('pass')} pass, "
            f"{counts.get('fail')} fail, {counts.get('error')} error of "
            f"{counts.get('attempted')} attempted"
            + (f"; unrun: {', '.join(unrun)}" if unrun else "")
            + ". This is a separate verdict: it neither establishes nor "
              "overrides any native CUDA result above.")
    lines += ["",
              "Historical CPU/RELION Gate 2 failures remain failures. An exact "
              "schedule comparison never converts one into a pass."]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-json", type=Path)
    parser.add_argument("--all24-json", type=Path)
    parser.add_argument("--truth-json", type=Path)
    parser.add_argument("--cpu-diagnostic-json", type=Path)
    parser.add_argument("--capacity-json", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    opts = parser.parse_args()

    matrix_report = load(opts.matrix_json)
    all24 = load(opts.all24_json)
    truth = load(opts.truth_json)
    cpu_diag = load(opts.cpu_diagnostic_json)
    capacity = load(opts.capacity_json)

    lines = ["# Issue 83 support report", "",
             "Generated by `tools/validation_issue83/report.py` from raw per-case "
             "reports. Rows without a raw result are named `unrun`.", ""]
    if matrix_report:
        prov = matrix_report.get("provenance", {})
        lines += ["## Provenance", "",
                  f"- Host: `{prov.get('hostname')}`, device `{prov.get('gpu')}`",
                  f"- Binary: `{prov.get('binary')}`",
                  f"- Binary SHA256: `{prov.get('binary_sha256')}`",
                  f"- Comparator SHA256: `{prov.get('comparator_sha256')}`",
                  f"- Harness SHA256: matrix `{prov.get('matrix_sha256')}`, "
                  f"runner `{prov.get('runner_sha256')}`",
                  f"- Run: {prov.get('started_utc')} to "
                  f"{matrix_report.get('finished_utc')}", ""]
        counts = matrix_report.get("counts", {})
        unrun = matrix_report.get("unrun_rows", [])
        lines += [f"- Declared rows {counts.get('declared')}; attempted "
                  f"{counts.get('attempted')}; pass {counts.get('pass')}; "
                  f"fail {counts.get('fail')}; error {counts.get('error')}",
                  f"- Unrun rows: {', '.join(unrun) if unrun else 'none'}", ""]

    lines += render_matrix(matrix_report)
    lines += render_all24(all24)
    lines += render_capacity(capacity)
    lines += render_numerical(truth, cpu_diag)
    lines += render_deferred()

    complete = bool(matrix_report and matrix_report.get("matrix_complete")
                    and all24 and all24.get("all24_equal"))
    lines += ["", "## Aggregate", "",
              ("The declared matrix is complete and every attempted row passed."
               if complete else
               "**The declared matrix is not complete.** Unrun and failing rows "
               "are named above; this report does not claim the broad matrix "
               "passed."), ""]

    opts.out.parent.mkdir(parents=True, exist_ok=True)
    opts.out.write_text("\n".join(lines) + "\n")
    print(f"wrote {opts.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
