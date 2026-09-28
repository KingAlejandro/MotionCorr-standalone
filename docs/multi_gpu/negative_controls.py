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

# (label, file, old, new, cases that must fail once mutated[, requires-binary])
# A trailing 6th element names an executable the case needs. If it is absent the
# mutation is reported SKIPPED, never "detected" -- a mutation whose case cannot
# run in this environment has not been shown to be caught anywhere.
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
     ["case_roundtrip_and_metadata", "case_clean_merge"]),

    ("C++-reader refusals removed from the STAR parser",
     "tools/multi_gpu/star_io.py",
     "    for n, raw in enumerate(lines, start=1):",
     "    for n, raw in []:  # MUTATED",
     ["case_star_parser_refusals"]),

    ("decorated-output collision preflight removed",
     "tools/multi_gpu/partition_star.py",
     "            other = roots.get(root + decoration)",
     "            other = None  # MUTATED",
     ["case_decorated_output_collision"]),

    ("output attribution falls back to naive suffix stripping",
     "tools/multi_gpu/merge_workers.py",
     "            attribution = star_io.split_output_path(str(rel), root_owner)",
     "            attribution = (str(rel).rsplit('.', 1)[0], '', '')  # MUTATED",
     ["case_real_output_suffixes_attributed"]),

    ("per-worker aggregates published into the merged tree",
     "tools/multi_gpu/merge_workers.py",
     '                dst = out / "_workers" / f"w{k}" / rel',
     "                dst = out / rel  # MUTATED",
     ["case_clean_merge"]),

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

    ("misrouted check removed from the merge",
     "tools/multi_gpu/merge_workers.py",
     "                if assigned != k:",
     "                if False:  # MUTATED",
     ["case_duplicate_and_misrouted_output", "case_real_output_suffixes_attributed"]),

    ("unassigned-output check removed from the merge",
     "tools/multi_gpu/merge_workers.py",
     '                problems.append(f"worker {k}: produced {rel}, which belongs to no movie "',
     '                _unused = (f"worker {k}: produced {rel}, which belongs to no movie "  # MUTATED',
     ["case_unassigned_movie_output"]),

    ("worker exit codes no longer gate the merge",
     "tools/multi_gpu/merge_workers.py",
     "        for k in range(len(shards)):\n            rc = exits.get(str(k))",
     "        for k in []:  # MUTATED\n            rc = exits.get(str(k))",
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

    ("aggregate row-order check removed from the merge",
     "tools/multi_gpu/merge_workers.py",
     "                if got != want:",
     "                if False:  # MUTATED",
     ["case_aggregate_wrong_order_rejected"]),

    ("aggregate extra arguments dropped instead of forwarded",
     "tools/multi_gpu/merge_workers.py",
     "        extra = shlex.split(a.aggregate_args)",
     "        extra = []  # MUTATED",
     ["case_aggregate_star_canonical_order"]),

    ("launcher verdict no longer gates the merge",
     "tools/multi_gpu/merge_workers.py",
     '        elif launcher_verdict != "PASS":',
     "        elif False:  # MUTATED",
     ["case_failed_device_witness_blocks_merge"]),

    ("aggregate-name match moved back ahead of attribution",
     "tools/multi_gpu/merge_workers.py",
     "            attribution = star_io.split_output_path(str(rel), root_owner)\n"
     "            if attribution is None:\n"
     "                if is_aggregate(rel):",
     "            attribution = None if is_aggregate(rel) else "
     "star_io.split_output_path(str(rel), root_owner)  # MUTATED\n"
     "            if attribution is None:\n"
     "                if is_aggregate(rel):",
     ["case_aggregate_name_shadowing"]),

    ("reserved-name preflight removed",
     "tools/multi_gpu/partition_star.py",
     "            if (root + decoration) in reserved:",
     "            if False:  # MUTATED",
     ["case_reserved_name_collision"]),

    ("short rows silently accepted",
     "tools/multi_gpu/star_io.py",
     "            if len(values) < len(labels):",
     "            if False:  # MUTATED",
     ["case_short_row_refused"]),

    ("output_root strips the extension only within the basename",
     "tools/multi_gpu/star_io.py",
     '    dot = movie_name.rfind(".")',
     '    dot = movie_name.rfind(".", movie_name.rfind("/") + 1)  # MUTATED',
     ["case_output_root_matches_withoutextension"]),

    ("--link no longer refused alongside --aggregate-with",
     "tools/multi_gpu/merge_workers.py",
     "    if a.link and a.aggregate_with:",
     "    if False:  # MUTATED",
     ["case_link_with_aggregate_refused"]),

    ("missing worker directory no longer reported",
     "tools/multi_gpu/merge_workers.py",
     '            problems.append(f"worker {k}: {wpath} is not a directory")',
     '            _unused = (f"worker {k}: {wpath} is not a directory")  # MUTATED',
     ["case_missing_worker_directory"]),

    ("per-worker CPU masks collapse to one shared mask",
     "tools/multi_gpu/run_multi_gpu.py",
     "        elif len(parts) == n:\n            masks = parts",
     "        elif len(parts) == n:\n            masks = [parts[0]] * n  # MUTATED",
     ["case_per_worker_cpu_masks"], "taskset"),

    ("sampler stop flag shadows threading.Thread._stop again",
     "tools/multi_gpu/run_multi_gpu.py",
     "        self._stop_event = threading.Event()",
     "        self._stop = self._stop_event = threading.Event()  # MUTATED",
     ["case_sampler_lifecycle"]),

    ("sampler backend errors no longer recorded",
     "tools/multi_gpu/run_multi_gpu.py",
     "                self.errors.append(str(exc))",
     "                pass  # MUTATED",
     ["case_sampler_lifecycle"]),

    ("--devices with --no-witness accepted again",
     "tools/multi_gpu/run_multi_gpu.py",
     "    if a.devices and a.no_witness:",
     "    if False:  # MUTATED",
     ["case_devices_with_no_witness_refused"]),

    ("compare24 keys reports by basename again",
     "tools/multi_gpu/compare24.py",
     '        report_id = rel.replace("/", "__").replace("\\\\", "__")',
     "        report_id = Path(rel).name  # MUTATED",
     ["case_compare24_report_identity"]),

    ("merge matches absolute roots without normalizing",
     "tools/multi_gpu/merge_workers.py",
     "    root_owner = {star_io.worker_relative_root(star_io.output_root(m)): k\n"
     "                  for m, k in owner.items()}",
     "    root_owner = {star_io.output_root(m): k for m, k in owner.items()}  # MUTATED",
     ["case_absolute_movie_roots_attributed"]),

    ("merge completeness check un-normalizes the root",
     "tools/multi_gpu/merge_workers.py",
     "        root = star_io.worker_relative_root(star_io.output_root(movie))",
     "        root = star_io.output_root(movie)  # MUTATED",
     ["case_absolute_movie_roots_attributed"]),

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
    skipped = 0
    for entry in MUTATIONS:
        label, relpath, old, new, cases = entry[:5]
        requires = entry[5] if len(entry) > 5 else None
        if requires and shutil.which(requires) is None:
            skipped += 1
            results.append({"mutation": label, "file": relpath, "status": "SKIPPED",
                            "reason": f"{requires} not on PATH; this mutation is not "
                                      "claimed to be detected in this environment"})
            continue
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

    n_attempted = len(MUTATIONS) - skipped
    record = {"n_mutations": len(MUTATIONS), "n_attempted": n_attempted,
              "n_skipped": skipped,
              "n_detected": sum(1 for r in results if r["status"] == "detected"),
              "survivors": survivors, "results": results}
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(record, indent=2) + "\n")
    print(f"\n{record['n_detected']}/{n_attempted} mutations detected"
          + (f" ({skipped} skipped for a missing tool, and not claimed)"
             if skipped else ""))
    if survivors:
        print("SURVIVED (guard does not observe what it asserts):")
        for s in survivors:
            print("  " + s)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
