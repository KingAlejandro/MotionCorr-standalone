#!/usr/bin/env python3
"""Show that each scheduling guard is what makes its test pass.

A test that passes is not evidence unless it would fail when the thing it checks
is broken. This applies one targeted mutation at a time to a scratch copy of the
tree, re-runs the cases that should then fail, and reports any that still pass --
those are checks that cannot observe what they assert.

Usage: python3 docs/multi_gpu/negative_controls.py [--json-out FILE]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (label, file, old, new, cases that must fail once mutated)
MUTATIONS = [
    ("partition preflight disabled",
     "tools/multi_gpu/partition_star.py",
     "    problems = preflight(star, block)",
     "    problems = []  # MUTATED",
     ["case_output_name_collision", "case_duplicate_movie_in_input",
      "case_collapsed_spaces_are_a_collision"]),

    ("empty-shard guard removed",
     "tools/multi_gpu/partition_star.py",
     "    if a.n > len(rows):",
     "    if False:  # MUTATED",
     ["case_empty_shard_rejected"]),

    ("shards re-serialized from parsed values instead of original bytes",
     "tools/multi_gpu/star_io.py",
     "        return prefix + \"\".join(r.raw for r in rows) + suffix",
     "        return prefix + \"\".join(\" \".join(r.values) + \"\\n\" for r in rows) + suffix"
     "  # MUTATED",
     ["case_roundtrip_and_metadata"]),

    ("C++-reader refusals removed from the STAR parser",
     "tools/multi_gpu/star_io.py",
     "    for n, raw in enumerate(lines, start=1):",
     "    for n, raw in []:  # MUTATED",
     ["case_star_parser_refusals"]),

    ("lost-output check removed from the merge",
     "tools/multi_gpu/merge_workers.py",
     "            if rel not in produced:",
     "            if False:  # MUTATED",
     ["case_lost_output"]),

    ("duplicate-output check removed from the merge",
     "tools/multi_gpu/merge_workers.py",
     "            if rel in produced:",
     "            if False:  # MUTATED",
     ["case_duplicate_and_misrouted_output"]),

    ("misrouted / unassigned checks removed from the merge",
     "tools/multi_gpu/merge_workers.py",
     "            assigned = root_owner.get(base)",
     "            assigned = k  # MUTATED",
     ["case_duplicate_and_misrouted_output", "case_unassigned_movie_output"]),

    ("worker exit codes no longer gate the merge",
     "tools/multi_gpu/merge_workers.py",
     "    exits: dict[str, int] = {}\n    if a.status:",
     "    exits: dict[str, int] = {}\n    if False:  # MUTATED",
     ["case_failed_worker_blocks_merge", "case_killed_worker_then_nonprefix_resume"]),

    ("missing --status no longer refuses the merge",
     "tools/multi_gpu/merge_workers.py",
     '        problems.append("no --status given',
     '        _unused = ("no --status given',  # MUTATED
     ["case_missing_status_blocks_merge"]),

    ("distinct-device assertion removed from the GPU witness",
     "tools/multi_gpu/gpu_witness.py",
     "    seen: dict[str, str] = {}\n    for e in chosen:",
     "    seen: dict[str, str] = {}\n    for e in []:  # MUTATED",
     ["case_gpu_witness_logic"]),

    ("unwitnessed PIDs counted as witnessed",
     "tools/multi_gpu/gpu_witness.py",
     "            unwitnessed.append(pid)\n            continue",
     "            continue  # MUTATED",
     ["case_gpu_witness_logic"]),

    ("launcher no longer refuses an existing --out",
     "tools/multi_gpu/run_multi_gpu.py",
     "    if out.exists():",
     "    if False:  # MUTATED",
     ["case_launcher_refuses_cpu_gpu_confusion"]),
]


def run_case(tree: Path, case: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(tree / "tests" / "test_multi_gpu_scheduling.py"),
         "--only", case],
        capture_output=True, text=True, cwd=tree)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args(argv)

    results = []
    survivors = []
    for label, relpath, old, new, cases in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="negctl_") as td:
            tree = Path(td) / "tree"
            for sub in ("tools/multi_gpu", "tests"):
                shutil.copytree(ROOT / sub, tree / sub)
            target = tree / relpath
            text = target.read_text()
            if text.count(old) != 1:
                results.append({"mutation": label, "status": "ANCHOR_NOT_UNIQUE",
                                "occurrences": text.count(old), "file": relpath})
                survivors.append(label)
                continue
            target.write_text(text.replace(old, new))

            per_case = {}
            for case in cases:
                cp = run_case(tree, case)
                # "1/1 passed" means the mutation went unnoticed.
                detected = cp.returncode != 0
                per_case[case] = "detected" if detected else "SURVIVED"
                if not detected:
                    survivors.append(f"{label} -> {case}")
            results.append({"mutation": label, "file": relpath, "cases": per_case,
                            "status": "detected" if all(v == "detected"
                                                        for v in per_case.values())
                                      else "SURVIVED"})

    for r in results:
        print(f"{r['status']:>18}  {r['mutation']}")
        for case, verdict in r.get("cases", {}).items():
            print(f"                    {verdict:>9}  {case}")

    record = {"n_mutations": len(MUTATIONS),
              "n_detected": sum(1 for r in results if r["status"] == "detected"),
              "survivors": survivors, "results": results}
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(record, indent=2) + "\n")
    print(f"\n{record['n_detected']}/{record['n_mutations']} mutations detected")
    if survivors:
        print("SURVIVED (guard does not observe what it asserts):")
        for s in survivors:
            print("  " + s)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
