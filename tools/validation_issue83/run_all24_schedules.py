#!/usr/bin/env python3
"""All-24 tutorial repeat / batch / non-prefix-resume equality for issue #83.

Runs the standard tutorial configuration uninterrupted, then repeats it, then
rebuilds it one movie at a time, then rebuilds it from a non-prefix partial
state, and requires every one of the 24 movies to be pixel- and
metadata-identical across all four schedules.

Every movie is checked individually with ``tools/compare_motioncorr.py --gate
exact``. A missing movie, a missing image/metadata pair, or a comparator report
that cannot be read fails the aggregate -- counts and exit status alone are
never accepted as evidence.

Sharding is intentionally not performed here. The scheduler wrapper lives in
#53/#55 and is consumed only once its aggregation is independently valid.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_matrix import (backend_witness, compare_pair, product_hashes,  # noqa: E402
                        report_name, run_binary, sha256)
import products as prod  # noqa: E402
from products import output_stem  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MOVIES = 24


def read_movie_stems(star: Path) -> List[str]:
    """Movie stems exactly as the runner derives them: dots become underscores."""
    blocks = prod.parse_star(star)
    movies = blocks.get("movies", {})
    fields = movies.get("fields", [])
    if "rlnMicrographMovieName" not in fields:
        raise SystemExit(f"{star}: no rlnMicrographMovieName column")
    column = fields.index("rlnMicrographMovieName")
    # Keep the movie's relative directory: the runner writes products under it.
    return [output_stem(row[column]) for row in movies.get("rows", [])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--runroot", type=Path, required=True,
                        help="Directory containing movies.star and Movies/")
    parser.add_argument("--star", default="movies.star")
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--gpu", type=int, default=None)
    parser.add_argument("--threads", default="8")
    parser.add_argument("--gainref", default="Movies/gain.mrc")
    parser.add_argument("--dose-per-frame", default="1.277")
    parser.add_argument("--schedules", default="repeat,batch,resume")
    parser.add_argument("--compare-tool", type=Path,
                        default=REPO_ROOT / "tools" / "compare_motioncorr.py")
    parser.add_argument("--json", type=Path)
    opts = parser.parse_args()

    runroot = opts.runroot.resolve()
    star = runroot / opts.star
    if not star.exists():
        parser.error(f"movies STAR not found: {star}")
    stems = read_movie_stems(star)
    if len(stems) != EXPECTED_MOVIES:
        print(f"WARNING: {len(stems)} movies in {star}, expected {EXPECTED_MOVIES}",
              file=sys.stderr)

    args = ["--use_own", "--j", opts.threads, "--seed", "1",
            "--dose_weighting", "--dose_per_frame", opts.dose_per_frame,
            "--patch_x", "5", "--patch_y", "5", "--bfactor", "150",
            "--gainref", opts.gainref, "--skip_logfile"]
    suffixes = [".mrc", ".star"]

    opts.outdir.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "schema": "issue83-all24-schedules/1",
        "provenance": {
            "binary": str(opts.binary.resolve()),
            "binary_sha256": sha256(opts.binary),
            "comparator_sha256": sha256(opts.compare_tool),
            "runroot": str(runroot), "star": str(star),
            "gpu": opts.gpu, "hostname": os.uname().nodename,
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "common_args": args,
        },
        "expected_movies": EXPECTED_MOVIES,
        "movies_in_star": len(stems),
        "schedules": {},
        "errors": [],
    }

    base_dir = opts.outdir / "base"
    base = run_binary(opts.binary, runroot, star, base_dir, args, opts.gpu)
    (base_dir / "run-stdout.txt").write_text(base["stdout"])
    (base_dir / "run-stderr.txt").write_text(base["stderr"])
    witness = backend_witness(base["stdout"], base_dir, stems, opts.gpu)
    inventory = prod.check_products(base_dir, stems, suffixes, {}, None)
    report["schedules"]["base"] = {
        "returncode": base["returncode"], "elapsed_sec": base["elapsed_sec"],
        "command": base["command"], "backend_evidence": witness,
        "inventory_errors": inventory["errors"],
        "movies_present": sum(1 for s in stems if (base_dir / f"{s}.mrc").exists()
                              and (base_dir / f"{s}.star").exists()),
    }
    if base["returncode"] != 0:
        report["errors"].append(f"base run exited {base['returncode']}")
    if opts.gpu is not None and not witness["native_cuda_proven"]:
        report["errors"].append("no native CUDA execution witness on the base run")
    report["errors"].extend(inventory["errors"])
    if report["schedules"]["base"]["movies_present"] != len(stems):
        report["errors"].append("base run is missing image/metadata pairs")

    base_hashes = product_hashes(base_dir, stems, suffixes)

    for schedule in [s.strip() for s in opts.schedules.split(",") if s.strip()]:
        sched_dir = opts.outdir / schedule
        entry: Dict[str, Any] = {"runs": []}
        last: Optional[Dict[str, Any]] = None

        if schedule == "repeat":
            last = run_binary(opts.binary, runroot, star, sched_dir, args, opts.gpu)
            entry["runs"].append({"returncode": last["returncode"],
                                  "elapsed_sec": last["elapsed_sec"]})
        elif schedule == "batch":
            for _ in range(len(stems)):
                last = run_binary(opts.binary, runroot, star, sched_dir, args, opts.gpu,
                                  ["--do_at_most", "1", "--only_do_unfinished"])
                entry["runs"].append({"returncode": last["returncode"],
                                      "elapsed_sec": last["elapsed_sec"]})
                if last["returncode"] != 0:
                    break
        elif schedule == "resume":
            # Seed a non-prefix partial state by copying a scattered subset of
            # already-good base outputs, then resume the full dataset.
            sched_dir.mkdir(parents=True, exist_ok=True)
            seeded = [stems[i] for i in range(1, len(stems), 3)]
            for stem in seeded:
                for suffix in suffixes:
                    name = f"{stem}.star" if suffix == ".star" else f"{stem}{suffix}"
                    src = base_dir / name
                    if src.exists():
                        target = sched_dir / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(src.read_bytes())
            entry["seeded_movies"] = seeded
            before = product_hashes(sched_dir, seeded, suffixes)
            last = run_binary(opts.binary, runroot, star, sched_dir, args, opts.gpu,
                              ["--only_do_unfinished"])
            entry["runs"].append({"returncode": last["returncode"],
                                  "elapsed_sec": last["elapsed_sec"]})
            after = product_hashes(sched_dir, seeded, suffixes)
            entry["preserved_seeded_outputs"] = bool(before) and before == after
            if not entry["preserved_seeded_outputs"]:
                report["errors"].append(
                    "resume: previously completed movies were not preserved")
        else:
            report["errors"].append(f"unknown schedule {schedule}")
            continue

        if last is not None:
            (sched_dir / "run-stdout.txt").write_text(last["stdout"])
            entry["backend_evidence"] = backend_witness(last["stdout"], sched_dir,
                                                        stems, opts.gpu)
        bad = [r for r in entry["runs"] if r["returncode"] != 0]
        if bad:
            entry["passed"] = False
            report["errors"].append(f"{schedule}: nonzero exit {bad}")
            report["schedules"][schedule] = entry
            continue

        missing = [s for s in stems
                   if not ((sched_dir / f"{s}.mrc").exists()
                           and (sched_dir / f"{s}.star").exists())]
        entry["missing_pairs"] = missing
        if missing:
            report["errors"].append(f"{schedule}: missing pairs for {', '.join(missing)}")

        reports = sched_dir / "compare"
        reports.mkdir(exist_ok=True)
        comparisons = {}
        for stem in stems:
            comparisons[stem] = compare_pair(opts.compare_tool, base_dir, sched_dir,
                                             stem, reports / report_name(stem, "exact"))
        entry["per_movie"] = comparisons
        entry["movies_compared"] = len(comparisons)
        entry["movies_passed"] = sum(1 for c in comparisons.values() if c["passed"])
        entry["failed_movies"] = sorted(s for s, c in comparisons.items()
                                        if not c["passed"])

        # Informational only. A byte digest also covers the MRC label
        # timestamp, so a product can be pixel-exact here yet not byte-equal;
        # the pass condition is the comparator verdict above, not this count.
        sched_hashes = product_hashes(sched_dir, stems, suffixes)
        entry["byte_identical_products"] = sum(
            1 for name, digest in base_hashes.items()
            if sched_hashes.get(name) == digest)
        entry["products_compared_by_digest"] = len(base_hashes)

        entry["passed"] = (not missing
                           and entry["movies_compared"] == len(stems)
                           and entry["movies_passed"] == len(stems)
                           and entry.get("preserved_seeded_outputs", True))
        if not entry["passed"]:
            report["errors"].append(
                f"{schedule}: {entry['movies_passed']}/{entry['movies_compared']} exact"
                + (f", failures: {', '.join(entry['failed_movies'])}"
                   if entry["failed_movies"] else ""))
        report["schedules"][schedule] = entry

    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report["all24_equal"] = (
        not report["errors"]
        and report["movies_in_star"] == EXPECTED_MOVIES
        and all(report["schedules"][s].get("passed")
                for s in report["schedules"] if s != "base"))

    if opts.json:
        opts.json.parent.mkdir(parents=True, exist_ok=True)
        opts.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"all24_equal": report["all24_equal"],
                      "errors": report["errors"][:20]}, indent=2))
    return 0 if report["all24_equal"] else 1


if __name__ == "__main__":
    sys.exit(main())
