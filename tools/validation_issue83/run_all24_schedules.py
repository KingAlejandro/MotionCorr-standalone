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

Three further conditions, each added after review found it absent:

* On a CUDA request every schedule must carry a native-execution witness over
  the movies it actually executed, and every invocation must announce the
  device. Output equality alone says nothing about which backend produced it.
* ``repeat``, ``batch`` and ``resume`` must all be present. A subset -- or an
  empty ``--schedules`` -- is reported as a partial screen and certifies
  nothing, rather than quantifying vacuously over whatever happened to run.
* The STAR, all movie files, the gain reference and this harness are hashed, so
  the archived result names the bytes it consumed rather than their paths.

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
from run_matrix import (CUDA_STARTUP, backend_witness, compare_pair,  # noqa: E402
                        product_hashes, report_name, run_binary,
                        schedule_witness, sha256)
import products as prod  # noqa: E402
from products import output_stem  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MOVIES = 24

#: Every schedule that must be present before the aggregate may certify
#: schedule equality. Iterating over whatever happened to be requested lets
#: ``--schedules repeat`` -- or an empty value -- certify the dataset without
#: batch or resume ever running.
REQUIRED_SCHEDULES = ("repeat", "batch", "resume")


def read_movie_names(star: Path) -> List[str]:
    """Movie paths exactly as written in the STAR, relative to the runroot."""
    blocks = prod.parse_star(star)
    movies = blocks.get("movies", {})
    fields = movies.get("fields", [])
    if "rlnMicrographMovieName" not in fields:
        raise SystemExit(f"{star}: no rlnMicrographMovieName column")
    column = fields.index("rlnMicrographMovieName")
    return [row[column] for row in movies.get("rows", [])]


def input_hashes(runroot: Path, star: Path, movie_names: List[str],
                 gainref: str) -> Dict[str, Any]:
    """Digest every byte this run consumed, not just the paths it was given.

    A path records where a file was, not what it contained. Without the digests
    two runs over different tutorial data are indistinguishable in the archived
    JSON, and the central all-24 result cannot be tied to the dataset it claims.
    Anything absent is recorded as ``null`` rather than omitted, so a gap is
    visible instead of merely missing.
    """
    here = Path(__file__).resolve().parent

    def digest(path: Path) -> Optional[str]:
        return sha256(path) if path.is_file() else None

    movies = {}
    for name in movie_names:
        path = (runroot / name)
        movies[name] = {"sha256": digest(path),
                        "bytes": path.stat().st_size if path.is_file() else None}
    missing = sorted(n for n, m in movies.items() if m["sha256"] is None)
    return {
        "star": {"path": str(star), "sha256": digest(star)},
        "movies": movies,
        "movies_hashed": sum(1 for m in movies.values() if m["sha256"]),
        "movies_missing": missing,
        "gainref": {"path": gainref, "sha256": digest(runroot / gainref)},
        "harness": {name: digest(here / name) for name in
                    ("run_all24_schedules.py", "run_matrix.py", "products.py")},
    }


def source_provenance(repo: Path) -> Dict[str, Any]:
    """The exact source this harness was read from, including uncommitted edits."""
    def git(*args: str) -> Optional[str]:
        try:
            out = subprocess.run(["git", "-C", str(repo), *args],
                                 capture_output=True, text=True, check=True)
        except (subprocess.CalledProcessError, OSError):
            return None
        return out.stdout.strip()

    dirty = git("status", "--porcelain")
    return {"commit": git("rev-parse", "HEAD"),
            "dirty": None if dirty is None else bool(dirty),
            "dirty_paths": dirty.splitlines() if dirty else []}


def expected_star_metadata(args: List[str]) -> Dict[str, Any]:
    """Metadata the integrated screen's invocation entails, field by field.

    The screen used to pass ``{}`` here, so it asserted presence and
    cross-schedule equality and nothing else: a build that ignored
    ``--dose_per_frame`` outright would have produced 24 movies that were
    equal under every schedule and passed.

    Only what the invocation determines is asserted. The original pixel size
    and the image dimensions come from the movies, which this harness does not
    parse -- the tutorial movies are not MRC -- so they are recorded as not
    asserted rather than guessed at.
    """
    def value_of(flag: str, default: Any) -> Any:
        return args[args.index(flag) + 1] if flag in args else default

    return {
        "binning": float(value_of("--bin_factor", 1)),
        "first_frame": int(value_of("--first_frame_sum", 1)),
        "dose_per_frame": (float(value_of("--dose_per_frame", 0))
                           if "--dose_weighting" in args else None),
        "pre_exposure": float(value_of("--preexposure", 0)),
    }


def schedule_passed(entry: Dict[str, Any], evidence: Dict[str, Any],
                    missing: List[str], n_movies: int,
                    gpu: Optional[int]) -> bool:
    """Whether one schedule may be recorded as passing.

    Output equality, a complete inventory and preserved seeded outputs say the
    schedule produced the right bytes. They say nothing about which backend
    produced them. The published resume entry recorded
    ``native_cuda_proven: false`` beside ``passed: true`` for exactly that
    reason -- the witness was collected and then not consumed -- so on a GPU
    request it is part of the condition, not a field printed next to it.
    """
    entry["native_cuda_required"] = gpu is not None
    return bool(not missing
                and entry.get("movies_compared") == n_movies
                and entry.get("movies_passed") == n_movies
                and entry.get("preserved_seeded_outputs", True)
                and (gpu is None or evidence.get("native_cuda_proven"))
                and not evidence.get("unexpected_cuda_marker"))


def certify(report: Dict[str, Any]) -> Dict[str, Any]:
    """Decide ``all24_equal`` from a finished report, in one place.

    Quantifies over the schedules that are *required*, not over the ones that
    happen to be present. Iterating the latter lets ``--schedules repeat``
    certify the dataset without batch or resume ever running, and lets an empty
    value certify it without running anything at all -- ``all()`` over nothing
    is true. A run that skipped a required schedule is still reported, and what
    it did verify is listed, but it is labelled partial and certifies nothing.
    """
    absent = [s for s in REQUIRED_SCHEDULES if s not in report.get("schedules", {})]
    report["missing_required_schedules"] = absent
    report["partial_screen"] = bool(absent)
    if absent:
        report.setdefault("errors", []).append(
            "partial screen: required schedule(s) " + ", ".join(absent)
            + " did not run, so schedule equality is not established for this "
              "dataset")
    report["all24_equal"] = bool(
        not report.get("errors")
        and not absent
        and report.get("movies_in_star") == EXPECTED_MOVIES
        and all(report["schedules"][s].get("passed") for s in REQUIRED_SCHEDULES))
    # What a partial screen *did* verify, reported without certifying anything.
    report["schedules_passed"] = sorted(
        s for s, e in report.get("schedules", {}).items()
        if s != "base" and e.get("passed"))
    return report


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
    movie_names = read_movie_names(star)
    stems = [output_stem(name) for name in movie_names]
    if len(stems) != EXPECTED_MOVIES:
        print(f"WARNING: {len(stems)} movies in {star}, expected {EXPECTED_MOVIES}",
              file=sys.stderr)

    args = ["--use_own", "--j", opts.threads, "--seed", "1",
            "--dose_weighting", "--dose_per_frame", opts.dose_per_frame,
            "--patch_x", "5", "--patch_y", "5", "--bfactor", "150",
            "--gainref", opts.gainref, "--skip_logfile"]
    suffixes = [".mrc", ".star"]
    star_expect = expected_star_metadata(args)

    opts.outdir.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "schema": "issue83-all24-schedules/2",
        "provenance": {
            "binary": str(opts.binary.resolve()),
            "binary_sha256": sha256(opts.binary),
            "comparator_sha256": sha256(opts.compare_tool),
            "runroot": str(runroot), "star": str(star),
            "gpu": opts.gpu, "hostname": os.uname().nodename,
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "common_args": args,
            "source": source_provenance(REPO_ROOT),
            "inputs": input_hashes(runroot, star, movie_names, opts.gainref),
        },
        "expected_movies": EXPECTED_MOVIES,
        "movies_in_star": len(stems),
        "star_metadata_asserted": star_expect,
        # Said plainly rather than left as an empty expectation. The tutorial
        # movies are not MRC, so this harness cannot read their pixel size or
        # dimensions, and asserting a guess would be worse than asserting
        # nothing.
        "metadata_not_asserted": ["original_pixel_size", "image_geometry"],
        "schedules_requested": [s.strip() for s in opts.schedules.split(",") if s.strip()],
        "required_schedules": list(REQUIRED_SCHEDULES),
        "schedules": {},
        "errors": [],
    }
    inputs = report["provenance"]["inputs"]
    if inputs["movies_missing"]:
        report["errors"].append(
            "movies named in the STAR are not readable, so the dataset cannot "
            f"be pinned: {', '.join(inputs['movies_missing'])}")
    if inputs["star"]["sha256"] is None:
        report["errors"].append("the movies STAR could not be hashed")

    base_dir = opts.outdir / "base"
    base = run_binary(opts.binary, runroot, star, base_dir, args, opts.gpu)
    (base_dir / "run-stdout.txt").write_text(base["stdout"])
    (base_dir / "run-stderr.txt").write_text(base["stderr"])
    witness = schedule_witness([base["stdout"]], base_dir, stems, opts.gpu)
    inventory = prod.check_products(base_dir, stems, suffixes, star_expect, None)
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

    for schedule in report["schedules_requested"]:
        sched_dir = opts.outdir / schedule
        entry: Dict[str, Any] = {"runs": []}
        last: Optional[Dict[str, Any]] = None
        stdouts: List[str] = []
        executed: List[str] = list(stems)

        if schedule == "repeat":
            last = run_binary(opts.binary, runroot, star, sched_dir, args, opts.gpu)
            stdouts.append(last["stdout"])
            entry["runs"].append({"returncode": last["returncode"],
                                  "elapsed_sec": last["elapsed_sec"]})
        elif schedule == "batch":
            for _ in range(len(stems)):
                last = run_binary(opts.binary, runroot, star, sched_dir, args, opts.gpu,
                                  ["--do_at_most", "1", "--only_do_unfinished"])
                stdouts.append(last["stdout"])
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
            # Only the movies it was *not* handed are actually executed, and
            # those are the only ones a native-execution witness can speak for.
            executed = [s for s in stems if s not in set(seeded)]
            before = product_hashes(sched_dir, seeded, suffixes)
            last = run_binary(opts.binary, runroot, star, sched_dir, args, opts.gpu,
                              ["--only_do_unfinished"])
            stdouts.append(last["stdout"])
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
        evidence = schedule_witness(stdouts, sched_dir, executed, opts.gpu)
        entry["backend_evidence"] = evidence
        if opts.gpu is not None and not evidence["native_cuda_proven"]:
            report["errors"].append(
                f"{schedule}: no native CUDA witness for the movies it executed "
                f"({evidence['movies_with_stage_marker']}/"
                f"{len(evidence['executed_movies'])} with a kernel marker, "
                f"device announced in {sum(evidence['startup_marker_per_invocation'])}"
                f"/{evidence['invocations']} invocations)")
        if evidence.get("unexpected_cuda_marker"):
            report["errors"].append(f"{schedule}: CPU run produced a CUDA marker")

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

        entry["passed"] = schedule_passed(entry, evidence, missing, len(stems),
                                          opts.gpu)
        if not entry["passed"]:
            report["errors"].append(
                f"{schedule}: {entry['movies_passed']}/{entry['movies_compared']} exact"
                + (f", failures: {', '.join(entry['failed_movies'])}"
                   if entry["failed_movies"] else ""))
        report["schedules"][schedule] = entry

    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    certify(report)
    absent = report["missing_required_schedules"]

    if opts.json:
        opts.json.parent.mkdir(parents=True, exist_ok=True)
        opts.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"all24_equal": report["all24_equal"],
                      "partial_screen": report["partial_screen"],
                      "schedules_passed": report["schedules_passed"],
                      "missing_required_schedules": absent,
                      "errors": report["errors"][:20]}, indent=2))
    if report["partial_screen"]:
        print("PARTIAL: this run does not certify all24_equal")
    return 0 if report["all24_equal"] else 1


if __name__ == "__main__":
    sys.exit(main())
