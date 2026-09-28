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
re-reads every per-movie STAR from disk (src/motioncorr_runner.cpp:1097-1150),
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
import hashlib
import json
import os
import shlex
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
    "corrected_micrographs.star", "corrected_tilt_series.star",
    "logfile.pdf", "header.pdf", "batch.pdf",
    "all_batches.pdf", "gain.mrc", "run.log", "time.txt", "note.txt",
    # written by run_multi_gpu.py itself, not by the worker
    "command.json", "status.json",
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
    ap.add_argument("--aggregate-args", default="",
                    help="one shell-quoted string of extra arguments for BINARY. Use "
                         "the = form so argparse does not read a leading dash as the "
                         "next option: --aggregate-args='--use_own --j 8'. A single "
                         "string rather than a trailing argparse.REMAINDER, because "
                         "REMAINDER after a named option silently captures nothing and "
                         "the arguments come back as 'unrecognized' -- which reads as a "
                         "usage error rather than as a dropped option list.")
    a = ap.parse_args(argv)

    if a.link and a.aggregate_with:
        print("FAIL: --link with --aggregate-with would let the aggregate step "
              "rewrite a worker's own outputs through the shared inode, destroying "
              "the evidence needed to diagnose the failure. Copy instead.",
              file=sys.stderr)
        return 2

    manifest = json.loads(Path(a.manifest).read_text())
    shards = manifest["shards"]
    products = [s for s in a.products.split(",") if s]

    problems: list[str] = []

    if not manifest.get("canonical_movies"):
        print("FAIL: manifest lists no movies; there is nothing to verify",
              file=sys.stderr)
        return 2

    if len(a.workers) != len(shards):
        print(f"FAIL: {len(a.workers)} worker directories for {len(shards)} shards",
              file=sys.stderr)
        return 2

    # A movie named twice is not a movie processed twice. The canonical list and
    # each shard are keyed into `owner` below by movie name, so a repeated name
    # collapses to one entry while `n_movies_expected` still counts it twice --
    # one product pair then satisfies both and the merge reports PASS on half the
    # coverage. The cross-shard case is caught by attribution; the same-shard case
    # is invisible without this check, so both are rejected here.
    def duplicates(names: list[str]) -> list[str]:
        seen, dupes = set(), []
        for nm in names:
            if nm in seen and nm not in dupes:
                dupes.append(nm)
            seen.add(nm)
        return dupes

    dupe_canonical = duplicates(list(manifest["canonical_movies"]))
    if dupe_canonical:
        print(f"FAIL: manifest lists the same movie more than once: {dupe_canonical}; "
              "one product pair cannot satisfy two expected movies", file=sys.stderr)
        return 2
    for s in shards:
        dupe_shard = duplicates(list(s["movies"]))
        if dupe_shard:
            print(f"FAIL: shard {s['index']} lists the same movie more than once: "
                  f"{dupe_shard}", file=sys.stderr)
            return 2

    # Defence in depth, on the same principle as the duplicate check above: the
    # merge stages worker aggregates under _workers/, so a movie whose root is
    # in that namespace would be overwritten by an aggregate while still
    # counting as covered. The partitioner refuses such a manifest; the merge
    # must not depend on having produced it.
    for movie in manifest["canonical_movies"]:
        root = star_io.worker_relative_root(star_io.output_root(movie))
        if root == "_workers" or root.startswith("_workers/"):
            print(f"FAIL: {movie!r} writes {root}.* into _workers/, the namespace "
                  "this tool stages worker aggregates into; its per-movie products "
                  "would be overwritten by an aggregate", file=sys.stderr)
            return 2

    exits: dict[str, int] = {}
    launcher_verdict = None
    if a.status:
        status = json.loads(Path(a.status).read_text())

        # Bind the status to THIS run. Nothing else here checks that the exit
        # codes and launcher verdict describe the manifest and worker
        # directories being merged, so a status file left over from another run
        # -- or copied from a passing one -- would supply clean exit codes for
        # workers that actually failed, and the merge would report PASS having
        # never seen the current run's result.
        status_manifest = status.get("manifest")
        if status_manifest is None:
            print("FAIL: status file records no manifest, so it cannot be shown to "
                  "describe this run", file=sys.stderr)
            return 2
        if Path(status_manifest).resolve() != Path(a.manifest).resolve():
            print(f"FAIL: status file describes manifest {status_manifest}, not "
                  f"{a.manifest}; refusing to take exit codes from another run",
                  file=sys.stderr)
            return 2
        status_digest = status.get("manifest_sha256")
        if status_digest is None:
            print("FAIL: status file records no manifest_sha256; it cannot be shown to "
                  "describe the shards being merged", file=sys.stderr)
            return 2
        actual_digest = hashlib.sha256(Path(a.manifest).read_bytes()).hexdigest()
        if status_digest != actual_digest:
            print(f"FAIL: manifest has changed since the run recorded in the status "
                  f"file ({status_digest[:16]} recorded, {actual_digest[:16]} on disk)",
                  file=sys.stderr)
            return 2
        recorded_workers = status.get("workers", [])
        if len(recorded_workers) != len(a.workers):
            print(f"FAIL: status file records {len(recorded_workers)} workers for "
                  f"{len(a.workers)} worker directories", file=sys.stderr)
            return 2
        for k, w in enumerate(recorded_workers):
            log = w.get("log")
            if log is None:
                print(f"FAIL: status file records no log path for worker {k}",
                      file=sys.stderr)
                return 2
            wdir = Path(a.workers[k]).resolve()
            if not str(Path(log).resolve()).startswith(str(wdir) + os.sep):
                print(f"FAIL: status file's worker {k} log {log} is not under the "
                      f"worker directory being merged ({wdir})", file=sys.stderr)
                return 2

        for w in status.get("workers", []):
            exits[str(w["index"])] = w.get("returncode")
        for k in range(len(shards)):
            rc = exits.get(str(k))
            if rc is None:
                problems.append(f"worker {k}: no exit code recorded")
            elif rc != 0:
                problems.append(f"worker {k}: exited {rc}")

        # Zero exit codes are not the whole story. run_multi_gpu.py also fails
        # its run when the device witness did not hold -- e.g. two workers were
        # observed on the same physical GPU, or one was never observed at all.
        # Reading only the return codes would launder that into a merge PASS,
        # which is precisely the claim this work exists to support.
        launcher_verdict = status.get("verdict")
        if launcher_verdict is None:
            problems.append("status file records no launcher verdict")
        elif launcher_verdict == "PASS":
            # A PASS is not allowed to contradict the record it carries. The
            # branch below reads gpu_witness only to build a failure message, so
            # without this a status whose own witness says two workers shared a
            # device would be accepted on the strength of the word "PASS".
            witness = status.get("gpu_witness")
            if isinstance(witness, dict) and not witness.get(
                    "all_pids_witnessed_on_intended_distinct_devices"):
                problems.append(
                    "launcher verdict is PASS but its own gpu_witness record does "
                    f"not support it: unwitnessed={witness.get('unwitnessed_pids')}, "
                    f"wrong_device={witness.get('wrong_device')}, "
                    f"shared_devices={witness.get('shared_devices')}, "
                    f"sampler_errors={witness.get('sampler_errors')}")
            elif isinstance(witness, str):
                problems.append(f"launcher verdict is PASS but the device witness was "
                                f"not performed: {witness}")
        else:
            witness = status.get("gpu_witness")
            detail = ""
            if isinstance(witness, dict):
                detail = (f"; gpu_witness: unwitnessed={witness.get('unwitnessed_pids')}, "
                          f"wrong_device={witness.get('wrong_device')}, "
                          f"shared_devices={witness.get('shared_devices')}")
            problems.append(f"launcher verdict is {launcher_verdict}, not PASS{detail}")
    else:
        problems.append("no --status given, so worker exit codes were never checked; "
                        "a worker that died silently would look like a clean partition")

    # Which shard each movie was assigned to.
    owner: dict[str, int] = {}
    for s in shards:
        for m in s["movies"]:
            owner[m] = s["index"]
    # Normalize to where the runner actually writes beneath each worker's --o,
    # so absolute movie names are attributed instead of reading as lost.
    #
    # Build this with a duplicate guard rather than a dict comprehension: two
    # movies whose normalized roots coincide would silently collapse to one
    # entry, and the single surviving product pair would then satisfy both --
    # PASS on coverage that is actually corrupt. The partitioner refuses such a
    # manifest, but the merge must not depend on having produced it.
    root_owner: dict[str, int] = {}
    collapsed_roots: set[str] = set()
    for movie, k in owner.items():
        root = star_io.worker_relative_root(star_io.output_root(movie))
        if root in root_owner:
            problems.append(
                f"duplicate coverage: two movies normalize to the same output root "
                f"{root!r}; one product pair cannot satisfy both"
            )
            # Keep the first owner and remember the clash. Overwriting would make
            # the last colliding movie's shard win attribution, and the single
            # real product would then be reported as misrouted from a shard it
            # never came from -- two invented errors on top of the true one.
            collapsed_roots.add(root)
            continue
        root_owner[root] = k

    # Resolve before use. PR55's shell merge built a relative destination and
    # then ran cp from inside each worker directory, so the copies landed under
    # the worker (or failed silently) and the later --only_do_unfinished pass saw
    # an empty tree and reprocessed the whole dataset. Nothing here chdirs, but
    # resolving removes the question entirely.
    out = Path(a.out).resolve()
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
            # Attribute FIRST. Matching aggregate names by basename alone would
            # divert a real per-movie product: a movie named Movies/run.tiff
            # writes Movies/run.log, and a movie named Movies/gain.tiff writes
            # Movies/gain.mrc. Both would be stashed as "aggregates" and quietly
            # vanish from the merged tree.
            attribution = star_io.split_output_path(str(rel), root_owner)
            if attribution is None:
                if is_aggregate(rel):
                    dst = out / "_workers" / f"w{k}" / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    per_worker_aggregates.append(str(Path("_workers") / f"w{k}" / rel))
                    continue
                problems.append(f"worker {k}: produced {rel}, which belongs to no movie "
                                "in the manifest")
            else:
                assigned = root_owner[attribution[0]]
                if attribution[0] in collapsed_roots:
                    pass  # ownership is ambiguous; already reported above
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
                try:
                    os.link(src, dst)
                except OSError as exc:
                    print(f"FAIL: cannot hardlink {src} -> {dst}: {exc}. A merged tree "
                          "on a different filesystem must be copied, not linked.",
                          file=sys.stderr)
                    return 2
            else:
                shutil.copy2(src, dst)

    canonical = manifest["canonical_movies"]
    for movie in canonical:
        root = star_io.worker_relative_root(star_io.output_root(movie))
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
        "launcher_verdict": launcher_verdict,
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
        extra = shlex.split(a.aggregate_args)
        cmd = [a.aggregate_with, "--i", str(Path(a.input_star).resolve()),
               "--o", str(out) + os.sep, "--only_do_unfinished"] + extra
        # The aggregate step exists only to have the stock binary regenerate the
        # dataset STAR over the staged tree. It is a full --only_do_unfinished run,
        # and isMovieComplete() is option-dependent -- do_dose_weighting/save_noDW,
        # even_odd_split, grouping_for_ps, and since PR110 the per-movie expected
        # frame count (src/motioncorr_runner.cpp:596-620). If --aggregate-args does
        # not match what the workers ran, a movie this merge just certified is
        # judged incomplete and REPROCESSED on top of the staged product, and the
        # report would then describe bytes the workers never wrote. Digest the
        # staged per-movie products first and require every one of them to survive
        # untouched.
        staged_before = {rel: hashlib.sha256((out / rel).read_bytes()).hexdigest()
                         for rel in sorted(produced)}
        proc = subprocess.run(cmd, capture_output=True, text=True)
        rewritten = sorted(
            rel for rel, digest in staged_before.items()
            if not (out / rel).exists()
            or hashlib.sha256((out / rel).read_bytes()).hexdigest() != digest)
        if rewritten:
            problems.append(
                f"aggregate step rewrote {len(rewritten)} staged worker product(s) "
                f"instead of only regenerating the dataset STAR: {rewritten[:5]}"
                + (" ..." if len(rewritten) > 5 else "")
                + ". --only_do_unfinished judged them incomplete, so --aggregate-args "
                  "does not match the options the workers ran under.")
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
                # Normalize both sides. getOutputFileNames() is plain
                # concatenation (src/motioncorr_runner.cpp:553-573), so an
                # absolute movie name writes "<out>//abs/path/x.mrc" while the
                # expectation is built through worker_relative_root, which
                # strips the leading slash. Those name one file but are
                # different strings, so a correct tree would fail this check.
                got = [os.path.normpath(r.values[col]) for r in block.rows]
                want = [os.path.normpath(str(out / (star_io.worker_relative_root(
                    star_io.output_root(m)) + ".mrc"))) for m in canonical]
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
