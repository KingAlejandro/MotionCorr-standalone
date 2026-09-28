#!/usr/bin/env python3
"""Stage sharded worker outputs into one tree and verify the partition held.

What this checks, all fail-closed, before anything is called merged:

  lost        a movie assigned to a shard whose products are absent
  duplicate   the same output path produced under two workers
  misrouted   a worker produced a movie that was assigned to a different shard
  unassigned  a shard in the manifest with no worker directory
  failed      a worker that exited non-zero, or whose exit was never recorded

Order is taken from the manifest's canonical movie list -- the input STAR's row
order -- not from completion order, so the staged tree and the aggregate row
order do not depend on which worker finished first.

The authoritative aggregate `corrected_micrographs.star` is produced by the
stock binary, not synthesized here. generateLogFilePDFAndWriteStarFiles()
re-reads every per-movie STAR from disk (src/motioncorr_runner.cpp:1053-1100),
so running the binary over the full input with --only_do_unfinished against the
staged tree regenerates it exactly, with no source change and no re-serialized
metadata. Pass --aggregate-with to do that.

`logfile.pdf` is deliberately NOT reproduced. The PDF batch loop globs only the
movies in the current pending list, so a merged run's PDF is not equivalent to a
serial run's, by construction; producing one that is needs a source change and
is out of scope here. This tool neither writes it nor claims it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import star_io  # noqa: E402

# Fixed-name per-process artifacts. Every worker writes its own; none of them is
# the dataset product, so they are staged under a per-worker subdirectory
# instead of being copied into, or silently dropped from, the merged tree.
AGGREGATE_NAMES = {
    "corrected_micrographs.star", "logfile.pdf", "header.pdf", "batch.pdf",
    "all_batches.pdf", "gain.mrc", "run.log", "time.txt", "note.txt",
}
AGGREGATE_PREFIXES = ("corrected_micrographs_",)
AGGREGATE_SUFFIXES = (".lst",)


def is_aggregate(rel: Path) -> bool:
    name = rel.name
    return (name in AGGREGATE_NAMES
            or name.startswith(AGGREGATE_PREFIXES)
            or name.endswith(AGGREGATE_SUFFIXES))


def worker_files(root: Path) -> dict[Path, Path]:
    out = {}
    for f in sorted(root.rglob("*")):
        if f.is_file():
            out[f.relative_to(root)] = f
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, help="partition_star.py manifest")
    ap.add_argument("--workers", nargs="+", required=True,
                    help="worker output directories, in shard index order")
    ap.add_argument("--status", default=None,
                    help="run_multi_gpu.py status JSON holding each worker's exit code")
    ap.add_argument("--out", required=True, help="merged tree to create")
    ap.add_argument("--products", default=".mrc,.star",
                    help="per-movie suffixes every movie must have produced")
    ap.add_argument("--link", action="store_true",
                    help="hardlink instead of copying; the comparison still reads real bytes")
    ap.add_argument("--report", default=None, help="write the verdict JSON here")
    ap.add_argument("--aggregate-with", default=None, metavar="BINARY",
                    help="regenerate corrected_micrographs.star by running BINARY over the "
                         "full input STAR with --only_do_unfinished against the merged tree")
    ap.add_argument("--input-star", default=None,
                    help="full input STAR, required with --aggregate-with")
    ap.add_argument("--aggregate-args", nargs=argparse.REMAINDER, default=[],
                    help="everything after this flag is passed to BINARY verbatim")
    a = ap.parse_args(argv)

    manifest = json.loads(Path(a.manifest).read_text())
    shards = manifest["shards"]
    products = [s for s in a.products.split(",") if s]

    problems: list[str] = []

    if len(a.workers) != len(shards):
        print(f"FAIL: {len(a.workers)} worker directories for {len(shards)} shards",
              file=sys.stderr)
        return 2

    exits: dict[str, int] = {}
    if a.status:
        status = json.loads(Path(a.status).read_text())
        for w in status.get("workers", []):
            exits[str(w["index"])] = w.get("returncode")
        for k in range(len(shards)):
            rc = exits.get(str(k))
            if rc is None:
                problems.append(f"worker {k}: no exit code recorded")
            elif rc != 0:
                problems.append(f"worker {k}: exited {rc}")
    else:
        problems.append("no --status given, so worker exit codes were never checked; "
                        "a worker that died silently would look like a clean partition")

    # Which shard each movie was assigned to.
    owner: dict[str, int] = {}
    for s in shards:
        for m in s["movies"]:
            owner[m] = s["index"]
    root_owner = {star_io.output_root(m): k for m, k in owner.items()}

    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        print(f"FAIL: refusing to merge into non-empty {out}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)

    produced: dict[Path, int] = {}     # staged relative path -> worker index
    per_worker_aggregates: list[str] = []

    for k, wdir in enumerate(a.workers):
        wpath = Path(wdir)
        if not wpath.is_dir():
            problems.append(f"worker {k}: {wpath} is not a directory")
            continue
        for rel, src in worker_files(wpath).items():
            if is_aggregate(rel):
                dst = out / "_workers" / f"w{k}" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                per_worker_aggregates.append(str(Path("_workers") / f"w{k}" / rel))
                continue

            stem = str(rel)
            for suffix in (".mrc", ".star", ".eps", ".log"):
                if stem.endswith(suffix):
                    stem = stem[: -len(suffix)]
                    break
            base = stem
            for tail in ("_noDW", "_PS", "_EVN", "_ODD"):
                if base.endswith(tail):
                    base = base[: -len(tail)]
                    break

            assigned = root_owner.get(base)
            if assigned is None:
                problems.append(f"worker {k}: produced {rel}, which belongs to no movie "
                                "in the manifest")
            elif assigned != k:
                problems.append(f"misrouted: worker {k} produced {rel}, assigned to "
                                f"shard {assigned}")

            if rel in produced:
                problems.append(f"duplicate: {rel} produced by workers "
                                f"{produced[rel]} and {k}")
                continue
            produced[rel] = k
            dst = out / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if a.link:
                os.link(src, dst)
            else:
                shutil.copy2(src, dst)

    canonical = manifest["canonical_movies"]
    for movie in canonical:
        root = star_io.output_root(movie)
        for suffix in products:
            rel = Path(root + suffix)
            if rel not in produced:
                problems.append(f"lost: {movie} has no {suffix} output "
                                f"(expected {rel}, shard {owner[movie]})")

    report: dict[str, object] = {
        "manifest": str(a.manifest),
        "merged_into": str(out),
        "n_movies_expected": len(canonical),
        "n_files_staged": len(produced),
        "worker_exit_codes": exits,
        "per_worker_aggregates_preserved": sorted(per_worker_aggregates),
        "problems": problems,
        "verdict": "PASS" if not problems else "FAIL",
        "logfile_pdf": "not produced and not claimed equivalent; the PDF batch loop is "
                       "path-dependent by construction (see module docstring)",
    }

    if problems:
        report["aggregate_star"] = "not attempted: staging failed"
    elif a.aggregate_with:
        if not a.input_star:
            print("FAIL: --aggregate-with requires --input-star", file=sys.stderr)
            return 2
        extra = [x for x in a.aggregate_args if x != "--"]
        cmd = [a.aggregate_with, "--i", str(a.input_star), "--o", str(out) + os.sep,
               "--only_do_unfinished"] + extra
        proc = subprocess.run(cmd, capture_output=True, text=True)
        (out / "_workers" / "merge.log").parent.mkdir(parents=True, exist_ok=True)
        (out / "_workers" / "merge.log").write_text(proc.stdout + proc.stderr)
        agg = {"command": cmd, "returncode": proc.returncode}
        if proc.returncode != 0:
            problems.append(f"aggregate step exited {proc.returncode}; see "
                            f"{out / '_workers' / 'merge.log'}")
        else:
            star_path = out / "corrected_micrographs.star"
            if not star_path.exists():
                problems.append(f"aggregate step produced no {star_path}")
            else:
                merged = star_io.parse(star_path)
                block = merged.block_with_label("rlnMicrographName")
                col = block.column("rlnMicrographName")
                got = [r.values[col] for r in block.rows]
                want = [str(out / (star_io.output_root(m) + ".mrc")) for m in canonical]
                agg["n_rows"] = len(got)
                if got != want:
                    problems.append(
                        "aggregate row order is not the canonical input order "
                        f"({len(got)} rows against {len(want)} expected); "
                        "first difference at "
                        + str(next((i for i, (g, w) in enumerate(zip(got, want)) if g != w),
                                   min(len(got), len(want))))
                    )
                else:
                    agg["row_order"] = "canonical"
        report["aggregate_star"] = agg
        report["problems"] = problems
        report["verdict"] = "PASS" if not problems else "FAIL"
    else:
        report["aggregate_star"] = ("not requested; staged outputs only. No dataset STAR "
                                    "is claimed.")

    if a.report:
        Path(a.report).write_text(json.dumps(report, indent=2) + "\n")

    print(json.dumps({k: report[k] for k in
                      ("n_movies_expected", "n_files_staged", "verdict")}, indent=2))
    for p in problems:
        print("  " + p, file=sys.stderr)
    return 0 if report["verdict"] == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
