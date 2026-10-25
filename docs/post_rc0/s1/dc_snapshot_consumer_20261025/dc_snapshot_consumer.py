#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Invoke the pinned DC Tier B summary adapter on a copied snapshot.

The wrapper does not parse evaluator metrics or implement adapter grading. It
checks copied-file identities, invokes the unchanged adapter, records its exit
and v2.2 state separately, and joins its coverage to the saved queue/RUN list.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
FORMAT = "motioncorr-dc-tierB-record-errors/2.2"
ADAPTER_SHA = "c2f391822b880fba20b7a9571e4d5150fa3b365bd18afff2e44f90fef939ef45"
BASELINE_SHA = "c2d8d92bbafbc950576c4709309412b4b8b6dfa99a2dabf59e42a09ee9f69e8a"
OLD_371_SHA = "c9956b9f82acb639317d77077961ab0c379844caec4f59aa8c0917dd09331d5b"
EVALUATIONS_SHA = "4ec94412fb98e6b1e4fda26b8b510e8f23c235a22ad162774e448c2a228d988a"
QUEUE_SHA = "7745d453a1033ce61dffe2b9347ea60d7eeb6b7d444e3542c451d0ccfb12a4da"
RUNS_SHA = "8b48deb22688dfda6c842c6238f32f4b01d7aa3e88d156ccfb54dbb882a9b13f"
A_SUMMARY_SHA = "419807ce72c8b4c35b857ed2db4a0f9a422ee951360de1601549083f52392747"
ARCHIVE_SHA = "b787ca32838b7ef9b94f310ebed91883fffdcd97f31132652481626862a401a0"
ATTEMPT1_SHA = "9343c67ff52fbb3e2d1c42b06be6980ed243300e61bf3daec6ca418113777a6d"
ATTEMPT2_SHA = "e8a9ea425041fb271310741063a04fb7f8e40461155f031a46cd63c944091655"
ORPHAN = "C-e12963-03-p3-cuda-both"
ADAPTER_STATES = {"COMPLETE", "IN_PROGRESS", "EVALUATION_ERROR"}


class InputError(ValueError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require_file(path: Path, expected: str, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise InputError(f"{label} is not a regular file: {path}")
    actual = sha256(path)
    if actual != expected:
        raise InputError(f"{label} hash mismatch: expected {expected}, found {actual}")
    return actual


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_run_exits(path: Path) -> dict[str, int]:
    runs: dict[str, int] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if len(fields) != 2:
            raise InputError(f"RUN inventory line {line_no} is not '<id> <exit>'")
        ident, raw_code = fields
        if ident in runs:
            raise InputError(f"duplicate RUN ID: {ident}")
        try:
            runs[ident] = int(raw_code)
        except ValueError as exc:
            raise InputError(f"invalid RUN exit on line {line_no}: {raw_code}") from exc
    return runs


def check_inputs(args: argparse.Namespace) -> dict[str, Any]:
    adapter_hash = require_file(args.adapter, ADAPTER_SHA, "reviewed v2.2 adapter")
    baseline_hash = require_file(args.baseline, BASELINE_SHA, "retained 736-record baseline")
    old_hash = require_file(args.old_371, OLD_371_SHA, "older 371-regression artifact")
    manifest_hash = require_file(args.evaluations, EVALUATIONS_SHA, "EVALUATIONS manifest")
    queue_hash = require_file(args.queue, QUEUE_SHA, "queue")
    runs_hash = require_file(args.run_exits, RUNS_SHA, "RUN inventory")
    a_hash = require_file(args.tier_a_summary, A_SUMMARY_SHA, "Tier A summary")
    archive_hash = require_file(args.archive, ARCHIVE_SHA, "collected byte-only archive") if args.archive else None
    attempt1_hash = require_file(args.collection_attempt1, ATTEMPT1_SHA, "preserved first collection attempt")
    attempt2_hash = require_file(args.collection_attempt2, ATTEMPT2_SHA, "successful corrected-path collection receipt")
    attempt1 = read_json(args.collection_attempt1)
    attempt2 = read_json(args.collection_attempt2)
    if attempt1.get("status") != "FAIL_PATH_NOT_FOUND_BEFORE_ARCHIVE" or attempt1.get("native_jobs") != 0:
        raise InputError("preserved first collection-attempt receipt has unexpected content")
    if (attempt2.get("records") != 736 or attempt2.get("content_bytes") != 43425487
            or attempt2.get("all736_hashes_match") is not True or attempt2.get("archive_sha256") != ARCHIVE_SHA):
        raise InputError("successful corrected-path collection receipt is inconsistent")

    manifest = read_json(args.evaluations)
    expected = manifest.get("sha256", {})
    if manifest.get("count") != 736 or len(expected) != 736:
        raise InputError("retained EVALUATIONS manifest must list exactly 736 record IDs")
    record_dir = args.eval_dir / "B"
    if not record_dir.is_dir() or record_dir.is_symlink():
        raise InputError(f"adapter EVAL_DIR must contain the actual B/ directory: {record_dir}")
    record_files = {p.stem: p for p in record_dir.glob("*.json") if p.is_file() and not p.is_symlink()}
    if set(record_files) != set(expected):
        raise InputError(f"copied record inventory differs: missing={len(set(expected)-set(record_files))}, extra={len(set(record_files)-set(expected))}")
    record_hashes = {}
    for ident, expected_hash in expected.items():
        actual = sha256(record_files[ident])
        if actual != expected_hash:
            raise InputError(f"record hash mismatch: {ident}")
        record_hashes[ident] = actual

    queue = read_json(args.queue)
    if not isinstance(queue, list) or len(queue) != 1700:
        raise InputError("queue must contain the retained 1700 IDs")
    queue_ids = [x["id"] for x in queue]
    if len(set(queue_ids)) != 1700:
        raise InputError("queue IDs are not unique")
    queue_by_id = {x["id"]: x for x in queue}
    runs = read_run_exits(args.run_exits)
    if len(runs) != 1403 or any(i not in queue_by_id for i in runs):
        raise InputError("RUN inventory does not match the retained 1403-in-1700 snapshot")
    if any(code != 0 for code in runs.values()):
        raise InputError("the supplied frozen RUN inventory is expected to contain only exit 0")
    if ORPHAN not in queue_by_id or ORPHAN in runs:
        raise InputError("retained interrupted/orphan identity disagrees with queue/RUN inventory")

    tier_a = read_json(args.tier_a_summary)
    tier_a_ids = {
        f"A-{result['case']}-{entry['backend']}-{entry['arm']}"
        for entry in tier_a for result in entry["results"]
    }
    queue_a = {x["id"] for x in queue if x["tier"] == "A"}
    if tier_a_ids != queue_a or len(tier_a_ids) != 80:
        raise InputError("Tier A identity inventory does not match the 80 queued Tier A jobs")

    return {
        "hashes": {
            "adapter": adapter_hash, "baseline_v2_2": baseline_hash,
            "historical_371": old_hash, "evaluations_manifest": manifest_hash,
            "queue": queue_hash, "run_exits": runs_hash,
            "tier_a_summary": a_hash, "collection_archive": archive_hash,
            "collection_attempt1": attempt1_hash, "collection_attempt2": attempt2_hash,
            "records": record_hashes,
        },
        "queue": queue, "queue_by_id": queue_by_id, "runs": runs,
        "tier_a_ids": tier_a_ids,
    }


def invoke_adapter(adapter: Path, eval_dir: Path, output_dir: Path) -> tuple[list[str], subprocess.CompletedProcess[bytes]]:
    argv = [sys.executable, "-B", str(adapter), str(eval_dir), str(output_dir)]
    env = os.environ.copy()
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    return argv, subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)


def parse_adapter_result(exit_code: int, stdout: bytes, output_dir: Path) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None, str | None]:
    summary_path = output_dir / "tierB-v2.json"
    coverage_path = output_dir / "coverage.md"
    if not summary_path.is_file():
        return "SUMMARY_MISSING", None, None, None
    try:
        summary = read_json(summary_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "SUMMARY_MALFORMED", None, None, None
    if not isinstance(summary, dict) or summary.get("format") != FORMAT or summary.get("state") not in ADAPTER_STATES:
        return "SUMMARY_FORMAT_INVALID", None, summary if isinstance(summary, dict) else None, None
    if any(not isinstance(summary.get(key), list) for key in ("rows", "pairs", "regressions", "record_audit")):
        return "SUMMARY_FORMAT_INVALID", None, summary, None
    try:
        stdout_obj = json.loads(stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return "CONSUMER_CONTRACT_MISMATCH", None, summary, None
    expected_exit = 2 if summary["state"] == "EVALUATION_ERROR" else 0
    if exit_code != expected_exit or not isinstance(stdout_obj, dict):
        return "EXIT_STATE_MISMATCH", stdout_obj if isinstance(stdout_obj, dict) else None, summary, None
    for key in ("format", "state", "global_error_count", "derived_error_count"):
        if stdout_obj.get(key) != summary.get(key):
            return "CONSUMER_CONTRACT_MISMATCH", stdout_obj, summary, None
    if not coverage_path.is_file():
        return "SUMMARY_FORMAT_INVALID", stdout_obj, summary, None
    return "READY_FOR_PARENT_REVIEW", stdout_obj, summary, str(coverage_path)


def join_queue(queue: list[dict[str, Any]], runs: dict[str, int], tier_a_ids: set[str], summary: dict[str, Any]) -> dict[str, Any]:
    evaluation_ids = {x.get("id") for x in summary.get("record_audit", []) if isinstance(x, dict) and isinstance(x.get("id"), str)}
    evaluation_states = {x.get("id"): x.get("state", x.get("status")) for x in summary.get("record_audit", []) if isinstance(x, dict) and isinstance(x.get("id"), str)}
    cell_states = {(r.get("condition"), r.get("backend"), r.get("arm")): r.get("state") for r in summary.get("rows", []) if isinstance(r, dict)}
    joined = []
    counts: Counter[str] = Counter()
    b_missing = 0
    c_run_ungraded = 0
    for item in queue:
        ident, tier = item["id"], item["tier"]
        code = runs.get(ident)
        run_state = f"RUN_EXIT_{code}" if code is not None else ("ORPHAN_NO_RUN" if ident == ORPHAN else "NO_RUN_RECEIPT")
        if tier == "A":
            evaluation_state = "TIER_A_SUMMARY_RECORD" if ident in tier_a_ids else "NO_TIER_A_RECORD"
            cell_state = None
        elif tier == "B":
            evaluation_state = evaluation_states.get(ident, "MISSING_TIER_B_RECORD")
            b_missing += ident not in evaluation_ids
            group = item.get("group", "")
            condition = group.rsplit("-s", 1)[0] if "-s" in group else ""
            cell_state = cell_states.get((condition, item.get("backend"), item.get("arm")), "NO_SUMMARY_ROW")
        else:
            evaluation_state = "TIER_C_UNGRADED_IN_SNAPSHOT"
            cell_state = None
            c_run_ungraded += code is not None
        counts[f"{tier}:{run_state}"] += 1
        counts[f"{tier}:EVALUATION:{evaluation_state}"] += 1
        if tier == "B":
            counts[f"B_CELL:{cell_state}"] += 1
        joined.append({
            "id": ident, "tier": tier, "backend": item["backend"], "arm": item["arm"],
            "run_exit": code, "run_state": run_state,
            "evaluation_state": evaluation_state, "tier_b_summary_cell_state": cell_state,
        })
    return {
        "queue_ids": len(queue), "run_receipts": len(runs),
        "exit0_run_receipts": sum(code == 0 for code in runs.values()),
        "no_run_receipt": sum(ident not in runs for ident in (x["id"] for x in queue)),
        "orphan_ids": [ORPHAN], "counts": dict(sorted(counts.items())),
        "tier_b_missing_evaluation_records": b_missing,
        "tier_b_record_state_counts": dict(sorted(Counter(str(v) for v in evaluation_states.values()).items())),
        "tier_c_completed_ungraded": c_run_ungraded,
        "completed_without_terminal_grade": b_missing + c_run_ungraded,
        "items": joined,
    }


def run(args: argparse.Namespace) -> tuple[str, int]:
    out = args.out.resolve()
    try:
        out.relative_to(ROOT)
    except ValueError as exc:
        raise InputError(f"output directory must be under {ROOT}") from exc
    if out == ROOT or out.exists():
        raise InputError(f"output directory must be new: {out}")
    snap = check_inputs(args)
    baseline = read_json(args.baseline)
    if len(baseline.get("rows", [])) != 80 or len(baseline.get("pairs", [])) != 240 or len(baseline.get("regressions", [])) != 878:
        raise InputError("retained v2.2 baseline no longer has 80 rows, 240 pairs, and 878 regressions")

    out.mkdir(parents=True, exist_ok=False)
    adapter_out = out / "adapter-output"
    argv, proc = invoke_adapter(args.adapter.resolve(), args.eval_dir.resolve(), adapter_out)
    (out / "adapter.stdout").write_bytes(proc.stdout)
    (out / "adapter.stderr").write_bytes(proc.stderr)
    state, stdout_obj, summary, coverage_path = parse_adapter_result(proc.returncode, proc.stdout, adapter_out)

    baseline_compare: dict[str, Any] = {"state": "NOT_COMPARABLE"}
    join: dict[str, Any] = {"state": "NOT_JOINED"}
    summary_has_join_arrays = (
        isinstance(summary, dict)
        and summary.get("format") == FORMAT
        and summary.get("state") in ADAPTER_STATES
        and all(isinstance(summary.get(key), list) for key in ("rows", "pairs", "regressions", "record_audit"))
    )
    if summary_has_join_arrays:
        fields = ("rows", "pairs", "regressions")
        equal = [key for key in fields if summary.get(key) == baseline.get(key)]
        baseline_compare = {
            "state": "MATCH" if len(equal) == len(fields) else "DIFFERENT",
            "equal_fields": equal,
            "counts": {key: len(summary.get(key, [])) for key in fields},
            "expected_counts": {key: len(baseline[key]) for key in fields},
        }
        if baseline_compare["state"] != "MATCH" and state == "READY_FOR_PARENT_REVIEW":
            state = "BASELINE_DIFFERENT"
        join = join_queue(snap["queue"], snap["runs"], snap["tier_a_ids"], summary)

    output_files = [out / "adapter.stdout", out / "adapter.stderr"]
    output_files += [p for p in (adapter_out / "tierB-v2.json", adapter_out / "coverage.md") if p.is_file()]
    receipt = {
        "schema": "motioncorr-dc-snapshot-consumer/1",
        "consumer_state": state,
        "adapter_format": FORMAT,
        "adapter_exit": proc.returncode,
        "adapter_summary_state": summary.get("state") if summary else None,
        "adapter_stdout_state": stdout_obj.get("state") if stdout_obj else None,
        "expected_exit_for_summary_state": 2 if summary and summary.get("state") == "EVALUATION_ERROR" else 0 if summary and summary.get("state") in ("COMPLETE", "IN_PROGRESS") else None,
        "adapter_argv": argv,
        "caller_argv": sys.argv,
        "adapter_sha256": snap["hashes"]["adapter"],
        "input_hashes": snap["hashes"],
        "adapter_output_dir": str(adapter_out),
        "adapter_output_hashes": {p.relative_to(out).as_posix(): sha256(p) for p in output_files},
        "baseline_comparison": baseline_compare,
        "queue_run_evaluation_join": join,
        "scientific_acceptance": "NOT_EVALUATED",
        "campaign_completion": "NOT_COMPLETE",
        "notes": [
            "v2.2 COMPLETE means only all Tier B summary rows have ten evaluated inputs.",
            "v2.2 IN_PROGRESS and EVALUATION_ERROR are retained as adapter states; exit and state are separately recorded.",
            "No exit/state value is a scientific PASS or whole-campaign completion claim.",
            "Null metrics and input/derived errors remain unchanged in adapter-output/tierB-v2.json.",
            "The older 371-regression artifact is separately hashed and never merged with the 878-regression baseline.",
        ],
    }
    receipt_path = out / "dc-join.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (out / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.relative_to(out).as_posix()}\n" for p in files), encoding="ascii")
    return state, 0 if state == "READY_FOR_PARENT_REVIEW" else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--eval-dir", type=Path, required=True, help="copied snapshot root containing B/")
    p.add_argument("--evaluations", type=Path, required=True, help="copied EVALUATIONS.json identity/hash manifest")
    p.add_argument("--queue", type=Path, required=True)
    p.add_argument("--run-exits", type=Path, required=True)
    p.add_argument("--tier-a-summary", type=Path, required=True)
    p.add_argument("--archive", type=Path, help="optional retained byte-only collection tar; hash checked, never extracted")
    p.add_argument("--collection-attempt1", type=Path, default=ROOT / "COLLECTION-ATTEMPT1.json")
    p.add_argument("--collection-attempt2", type=Path, default=ROOT / "COLLECTION-ATTEMPT2.json")
    p.add_argument("--adapter", type=Path, default=ROOT / "adapter/summarize_v2_2.py")
    p.add_argument("--baseline", type=Path, default=ROOT / "expected/tierB-v2.json")
    p.add_argument("--old-371", type=Path, default=ROOT / "expected/tierB-older-371.json")
    p.add_argument("--out", type=Path, required=True, help="new output directory under the owned task directory")
    args = p.parse_args()
    try:
        state, code = run(args)
        print(state)
        return code
    except (InputError, OSError, json.JSONDecodeError) as exc:
        print(f"dc_snapshot_consumer: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
