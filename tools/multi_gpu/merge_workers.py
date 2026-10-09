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

The authoritative dataset STAR and full report are produced by the stock
binary's explicit --aggregate_only mode. Every requested movie is preflighted
as complete; aggregation cannot process a missing movie or rewrite its products.
Per-worker aggregate reports remain retained as provenance, not substitutes for
the final canonical dataset report. Without --aggregate-with, staging PASS is
not dataset readiness.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import output_digests  # noqa: E402
import star_io  # noqa: E402
from output_digests import FileChanged, stat_key  # noqa: E402

# Fixed-name per-process artifacts. Every worker writes its own; none of them is
# the dataset product, so they are staged under a per-worker subdirectory
# instead of being copied into, or silently dropped from, the merged tree.
AGGREGATE_NAMES = {
    "corrected_micrographs.star", "corrected_tilt_series.star",
    "logfile.pdf", "header.pdf", "batch.pdf",
    "all_batches.pdf", "gain.mrc", "time.txt", "note.txt",
    # written by run_multi_gpu.py itself, not by the worker. The console log's
    # stem contains '.', which no movie output root can (star_io.output_root).
    "launcher.console.log", "command.json", "status.json",
}
AGGREGATE_PREFIXES = ("corrected_micrographs_",)
AGGREGATE_SUFFIXES = (".lst",)


def is_aggregate(rel: Path) -> bool:
    name = rel.name
    return (name in AGGREGATE_NAMES
            or name.startswith(AGGREGATE_PREFIXES)
            or name.endswith(AGGREGATE_SUFFIXES))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def changed_inputs(expected: dict[Path, str]) -> list[str]:
    """Input STARs whose current bytes differ from the partition-time digest."""
    changed = []
    for path, want in expected.items():
        try:
            got = sha256_file(path)
        except OSError as exc:
            changed.append(f"{path} ({exc})")
            continue
        if got.lower() != want.lower():
            changed.append(str(path))
    return changed


def gpu_witness_problems(status: dict[str, object]) -> list[str]:
    """Validate the evidence needed to certify a GPU-backed PASS."""
    devices = status.get("devices")
    if devices is None:
        if "gpu_witness" in status:
            return ["GPU witness is present without an intended-device list"]
        return []
    problems: list[str] = []
    if not isinstance(devices, list) or not devices:
        return ["GPU status has no valid intended-device list"]
    workers = status.get("workers")
    if not isinstance(workers, list) or len(workers) != len(devices):
        return ["GPU status worker/device counts do not match"]

    expected: dict[str, str] = {}
    seen_indices: set[int] = set()
    uuids: list[str] = []
    for device in devices:
        if not isinstance(device, dict) or not isinstance(device.get("uuid"), str) \
                or not device["uuid"]:
            problems.append("GPU status contains a device without a physical UUID")
            continue
        uuids.append(device["uuid"])
    if len(uuids) != len(devices) or len(set(uuids)) != len(devices):
        problems.append("GPU status intended UUIDs are missing or not distinct")

    for worker in workers:
        if not isinstance(worker, dict):
            problems.append("GPU status contains a malformed worker record")
            continue
        index, pid = worker.get("index"), worker.get("pid")
        if (not isinstance(index, int) or isinstance(index, bool)
                or index < 0 or index >= len(devices) or index in seen_indices):
            problems.append("GPU status worker indices do not form a unique device mapping")
            continue
        seen_indices.add(index)
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            problems.append(f"GPU status worker {index} has no valid PID")
            continue
        if any(str(pid) == prior for prior in expected):
            problems.append("GPU status assigns the same PID to multiple workers")
            continue
        device = devices[index]
        if isinstance(device, dict) and isinstance(device.get("uuid"), str):
            expected[str(pid)] = device["uuid"]
    if seen_indices != set(range(len(devices))):
        problems.append("GPU status worker indices do not cover every intended device")

    witness = status.get("gpu_witness")
    if not isinstance(witness, dict):
        return problems + ["GPU PASS has no complete gpu_witness record"]
    if witness.get("all_pids_witnessed_on_intended_distinct_devices") is not True:
        problems.append("GPU witness success condition is not true")
    if witness.get("sampler_errors") != []:
        problems.append("GPU witness has missing or non-empty sampler_errors")
    if witness.get("expected") != expected:
        problems.append("GPU witness expected PID/UUID mapping differs from worker/device records")

    witnessed = witness.get("witnessed")
    expected_observed = {pid: [uuid] for pid, uuid in expected.items()}
    if witnessed != expected_observed:
        problems.append("GPU witness did not observe every worker PID on its intended UUID")
    if witness.get("unwitnessed_pids") != []:
        problems.append("GPU witness records unwitnessed worker PIDs")
    if witness.get("wrong_device") != []:
        problems.append("GPU witness records a wrong-device worker")
    if witness.get("shared_devices") != []:
        problems.append("GPU witness records shared physical devices")
    if witness.get("distinct_devices_witnessed") != len(devices):
        problems.append("GPU witness distinct-device count does not match the worker count")
    return problems


def first_difference(got: list[str], want: list[str]) -> int:
    return next((i for i, (g, w) in enumerate(zip(got, want)) if g != w),
                min(len(got), len(want)))


def image_paths(out: Path, movies: list[str]) -> list[str]:
    # Normalize both sides. getOutputFileNames() is plain concatenation
    # (src/motioncorr_runner.cpp:553-573), so an absolute movie name writes
    # "<out>//abs/path/x.mrc" while the expectation is built through
    # worker_relative_root, which strips the leading slash. Those name one file
    # but are different strings, so a correct tree would fail the comparison.
    return [os.path.normpath(str(out / (star_io.worker_relative_root(
        star_io.output_root(m)) + ".mrc"))) for m in movies]


def micrograph_names(path: Path, block: star_io.Block) -> list[str]:
    col = block.column("rlnMicrographName")
    return [os.path.normpath(r.values[col]) for r in block.rows]


def joint_star_problems(out: Path, manifest: dict, input_type: str,
                        agg: dict) -> list[str]:
    """Check the dataset STAR the aggregate step published, by input type.

    SPA: corrected_micrographs.star lists every corrected image in canonical
    input order. Tomography: corrected_tilt_series.star lists every series in
    global-table order, each reference resolves to a per-series table inside
    the merged tree, and each table lists that series' images in pre-exposure
    order (src/jaz/tomography/tomogram_set.cpp:110-156, :818-841).
    """
    canonical = manifest["canonical_movies"]
    if input_type == "spa":
        star_path = out / "corrected_micrographs.star"
        if not star_path.exists():
            return [f"aggregate step produced no {star_path}"]
        try:
            got = micrograph_names(star_path, star_io.parse(star_path)
                                   .block_with_label("rlnMicrographName"))
        except star_io.StarFormatError as exc:
            return [f"aggregate joint STAR is unreadable: {exc}"]
        want = image_paths(out, canonical)
        agg["n_rows"] = len(got)
        if got != want:
            return ["aggregate row order is not the canonical input order "
                    f"({len(got)} rows against {len(want)} expected); first "
                    f"difference at {first_difference(got, want)}"]
        return []

    star_path = out / "corrected_tilt_series.star"
    if not star_path.exists():
        return [f"aggregate step produced no {star_path}"]
    series = manifest["tomography"]["series"]
    try:
        glob = star_io.tomo_global_block(star_io.parse(star_path))
        if glob is None:
            return [f"{star_path} has no data_global rows"]
        names = [r.values[glob.column(star_io.TOMO_NAME_LABEL)] for r in glob.rows]
        refs = [r.values[glob.column(star_io.TOMO_STAR_LABEL)] for r in glob.rows]
    except star_io.StarFormatError as exc:
        return [f"aggregate joint STAR is unreadable: {exc}"]
    want_names = [t["name"] for t in series]
    agg["n_series"] = len(names)
    if names != want_names:
        return ["aggregate tilt-series order is not the canonical global order "
                f"({len(names)} series against {len(want_names)} expected); first "
                f"difference at {first_difference(names, want_names)}"]
    problems = []
    n_rows = 0
    for t, ref in zip(series, refs):
        # The binary resolves a relative reference against its cwd, which the
        # aggregate step shares with this process.
        table_path = os.path.abspath(str(out / t["sidecar"]))
        if os.path.abspath(ref) != table_path:
            problems.append(f"tilt series {t['name']!r} references {ref}, not its "
                            f"per-series table {table_path}")
            continue
        try:
            got = micrograph_names(Path(table_path),
                                   star_io.parse(table_path).block(t["name"]))
        except (OSError, star_io.StarFormatError) as exc:
            problems.append(f"tilt series {t['name']!r}: per-series table unreadable: {exc}")
            continue
        want = image_paths(out, t["movies"])
        n_rows += len(got)
        if got != want:
            problems.append(f"tilt series {t['name']!r}: images are not the canonical "
                            f"pre-exposure order ({len(got)} rows against {len(want)} "
                            f"expected); first difference at {first_difference(got, want)}")
    agg["n_rows"] = n_rows
    return problems


def worker_files(root: Path) -> dict[Path, Path]:
    out = {}
    for f in sorted(root.rglob("*")):
        if f.is_file():
            out[f.relative_to(root)] = f
    return out


# Filesystems that cannot hardlink this pair: a different filesystem, a
# filesystem without hardlinks, a link-count limit, or protected_hardlinks.
LINK_FALLBACK_ERRNOS = {errno.EXDEV, errno.EPERM, errno.EMLINK, errno.ENOTSUP,
                        errno.EOPNOTSUPP}


def exit_records(worker: dict, k: int, problems: list[str]) -> dict[str, dict] | None:
    """The launcher's digests of worker k's outputs at exit, if it recorded any.

    None means no reference: a status without exit digests (an older launcher,
    or a hand-written status) leaves the merge to hash the products itself.
    """
    rec = worker.get("exit_digest")
    if rec is None:
        return None
    if not isinstance(rec, dict) or rec.get("status") != "complete":
        if worker.get("returncode") == 0:
            problems.append(f"worker {k}: outputs were not digested at exit "
                            f"({rec.get('status') if isinstance(rec, dict) else rec}: "
                            f"{rec.get('error') if isinstance(rec, dict) else ''})")
        return None
    outputs = rec.get("outputs")
    hexdigest = re.compile(r"[0-9a-f]{64}")
    if not isinstance(outputs, dict) or not all(
            isinstance(rel, str) and isinstance(v, dict)
            and (isinstance(v.get("error"), str)
                 or (isinstance(v.get("sha256"), str) and hexdigest.fullmatch(v["sha256"])
                     and isinstance(v.get("key"), list) and len(v["key"]) == 5
                     and all(type(x) is int for x in v["key"])))
            for rel, v in outputs.items()):
        problems.append(f"worker {k}: exit digest record is malformed")
        return None
    return outputs


def stage_one(src: Path, dst: Path, mode: str, record: dict | None) -> dict:
    """Put one product at dst and return its digest and staged stat key.

    A link shares the source inode, so the bytes need not be read when the
    source still has the stat key recorded at worker exit. Otherwise the bytes
    are hashed -- during the copy when copying -- and compared with the record.
    """
    res: dict = {}
    try:
        key = stat_key(os.stat(src))
        sha = record["sha256"] if record is not None and record["key"] == key else None
        linked = False
        if mode != "copy":
            try:
                os.link(src, dst)
                linked = True
            except OSError as exc:
                if mode == "link":
                    res["fatal"] = (f"cannot hardlink {src} -> {dst}: {exc}. --stage link "
                                    "does not fall back; use --stage auto or copy.")
                    return res
                if exc.errno not in LINK_FALLBACK_ERRNOS:
                    raise
                res["fallback"] = errno.errorcode.get(exc.errno, str(exc.errno))
        if linked:
            dst_st = os.stat(dst)
            # ctime moves with the link count; anything else moving means the
            # source was written between the stat above and the link.
            if stat_key(dst_st)[:4] != key[:4]:
                raise FileChanged(f"{src} changed while it was linked")
            if sha is not None:
                res["digest"] = "worker exit"
            else:
                sha = output_digests.hash_file(dst, stat_key(dst_st))
                res["digest"] = "merge" if record is None else "verified"
        else:
            sha = output_digests.copy_with_digest(src, dst, key)
            res["digest"] = "merge" if record is None else "verified"
        if record is not None and sha != record["sha256"]:
            res["problem"] = (f"changed after the worker exited (sha256 "
                              f"{record['sha256'][:16]} at exit, {sha[:16]} now)")
        res.update(stage="link" if linked else "copy", sha256=sha,
                   dst_key=stat_key(os.stat(dst)))
    except (OSError, FileChanged) as exc:
        res["problem"] = f"could not be staged: {type(exc).__name__}: {exc}"
    return res


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
    ap.add_argument("--stage", choices=("auto", "link", "copy"), default="auto",
                    help="how per-movie products enter the merged tree. auto (default) "
                         "hardlinks and copies only where the filesystem refuses a link "
                         "(e.g. a different filesystem); link refuses to fall back; copy "
                         "always copies. See docs/multi_gpu/AGGREGATE_STAGING.md")
    ap.add_argument("--link", dest="stage", action="store_const", const="link",
                    help="same as --stage link")
    ap.add_argument("--report", default=None, help="write the verdict JSON here")
    ap.add_argument("--aggregate-with", default=None, metavar="BINARY",
                    help="regenerate corrected_micrographs.star by running BINARY over the "
                         "full input STAR with --aggregate_only against the merged tree")
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

    products = [suffix.strip() for suffix in a.products.split(",") if suffix.strip()]
    if not products:
        print("FAIL: at least one required product suffix must be specified",
              file=sys.stderr)
        return 2

    aggregate_extra = shlex.split(a.aggregate_args)
    aggregate_owned = {"--i", "--o"}
    clashes = sorted({arg.split("=", 1)[0] for arg in aggregate_extra
                      if arg.split("=", 1)[0] in aggregate_owned})
    if clashes:
        print(f"FAIL: {', '.join(clashes)} is owned by the aggregate step and must "
              "not appear in --aggregate-args; the input STAR and output tree "
              "must remain the ones verified by this merge", file=sys.stderr)
        return 2

    manifest_path = Path(a.manifest).resolve()
    manifest = json.loads(manifest_path.read_text())
    shards = manifest["shards"]

    input_star_path = None
    manifest_input_sha256 = None
    if a.aggregate_with:
        if not a.input_star:
            print("FAIL: --aggregate-with requires --input-star", file=sys.stderr)
            return 2
        manifest_input_sha256 = manifest.get("input_sha256")
        if (not isinstance(manifest_input_sha256, str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", manifest_input_sha256) is None):
            print("FAIL: partition manifest has no valid input_sha256 for aggregate STAR",
                  file=sys.stderr)
            return 2
        input_star_path = Path(a.input_star).resolve()
        # The aggregate binary rereads every per-series table of a tomography
        # input, so those are aggregate inputs too.
        input_digests = {input_star_path: manifest_input_sha256}
        if manifest.get("input_type") == "tomography":
            for t in manifest.get("tomography", {}).get("series", []):
                ref_sha256 = t.get("ref_sha256")
                if (not t.get("ref_path") or not isinstance(ref_sha256, str)
                        or re.fullmatch(r"[0-9a-fA-F]{64}", ref_sha256) is None):
                    print(f"FAIL: partition manifest has no valid ref_sha256 for tilt "
                          f"series {t.get('name')!r}", file=sys.stderr)
                    return 2
                input_digests[Path(t["ref_path"])] = ref_sha256
        changed = changed_inputs(input_digests)
        if changed:
            print("FAIL: aggregate input STAR content does not match the partition "
                  f"manifest digest: {changed}", file=sys.stderr)
            return 2

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

    plot_movies = {}
    for movie in manifest["canonical_movies"]:
        try:
            plot = star_io.shift_plot_path(movie)
        except ValueError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
        prior = plot_movies.get(plot)
        if (plot.startswith("_workers/") or
            (prior is not None and star_io.worker_relative_root(star_io.output_root(prior)) !=
             star_io.worker_relative_root(star_io.output_root(movie)))):
            print(f"FAIL: ambiguous or reserved shift-plot path {plot}", file=sys.stderr)
            return 2
        # Identical numerical roots retain the existing duplicate-coverage report.
        plot_movies.setdefault(plot, movie)

    exits: dict[str, int] = {}
    launcher_verdict = None
    records: dict[int, dict[str, dict]] = {}
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
            rec = exit_records(w, k, problems)
            if rec is not None:
                records[k] = rec

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
            problems.extend(gpu_witness_problems(status))
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

    input_type = manifest.get("input_type", "spa")
    if input_type not in ("spa", "tomography"):
        print(f"FAIL: manifest input_type {input_type!r} is not spa or tomography",
              file=sys.stderr)
        return 2
    sidecar_owner: dict[str, int] = {}
    if input_type == "tomography":
        for s in shards:
            for sidecar in s.get("sidecars", []):
                sidecar_owner[sidecar] = s["index"]
        tomo_series = manifest.get("tomography", {}).get("series", [])
        if ([m for t in tomo_series for m in t["movies"]] != list(manifest["canonical_movies"])
                or sorted(sidecar_owner) != sorted(t["sidecar"] for t in tomo_series)):
            print("FAIL: tomography manifest series do not cover the canonical movies "
                  "and per-series tables exactly", file=sys.stderr)
            return 2

    produced: dict[Path, int] = {}     # staged relative path -> worker index
    per_worker_aggregates: list[str] = []
    plan: list[tuple[int, Path, Path, Path]] = []

    for k, wdir in enumerate(a.workers):
        wpath = Path(wdir)
        if not wpath.is_dir():
            problems.append(f"worker {k}: {wpath} is not a directory")
            continue
        files = worker_files(wpath)
        if k in records:
            # The record lists everything the worker left at exit, so a file
            # present now but not then, or the reverse, was made or removed
            # after the worker exited.
            now = {str(rel) for rel in files} - output_digests.LAUNCHER_FILES
            for rel in sorted(now - set(records[k])):
                problems.append(f"worker {k}: {rel} appeared after the worker exited")
            for rel in sorted(set(records[k]) - now):
                problems.append(f"worker {k}: {rel} existed at worker exit and is now "
                                "missing")
            for rel in sorted(now & set(records[k])):
                if "error" in records[k][rel]:
                    problems.append(f"worker {k}: {rel} could not be digested at exit: "
                                    f"{records[k][rel]['error']}")
        for rel, src in files.items():
            # Attribute FIRST. Matching aggregate names by basename alone would
            # divert a real per-movie product: a movie named Movies/run.tiff
            # writes Movies/run.log, and a movie named Movies/gain.tiff writes
            # Movies/gain.mrc. Both would be stashed as "aggregates" and quietly
            # vanish from the merged tree.
            plot_movie = plot_movies.get(str(rel))
            attribution = star_io.split_output_path(str(rel), root_owner)
            if plot_movie is not None:
                attribution = (star_io.worker_relative_root(
                    star_io.output_root(plot_movie)), "_shifts", ".eps")
            if attribution is None and str(rel) in sidecar_owner \
                    and sidecar_owner[str(rel)] != k:
                problems.append(f"misrouted: worker {k} produced per-series table {rel}, "
                                f"assigned to shard {sidecar_owner[str(rel)]}")
                continue
            if attribution is None:
                # A worker's per-series tables describe only its own series; the
                # aggregate step writes the dataset's versions into the merged
                # root, so the worker copies are provenance, like its joint STAR.
                if is_aggregate(rel) or str(rel) in sidecar_owner:
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
            plan.append((k, rel, src, dst))

    def stage(item: tuple[int, Path, Path, Path]) -> tuple[Path, int, dict]:
        k, rel, src, dst = item
        rec = records.get(k, {}).get(str(rel))
        return rel, k, stage_one(src, dst, a.stage,
                                 rec if rec is not None and "error" not in rec else None)

    t_stage = time.monotonic()
    with ThreadPoolExecutor(max_workers=output_digests.pool_size()) as pool:
        staged_results = list(pool.map(stage, plan))
    staging: dict[str, object] = {"mode_requested": a.stage,
                                  "threads": output_digests.pool_size()}
    staged: dict[Path, dict] = {}
    for rel, k, res in staged_results:
        if "fatal" in res:
            print(f"FAIL: {res['fatal']}", file=sys.stderr)
            return 2
        if "problem" in res:
            problems.append(f"worker {k}: {rel} {res['problem']}")
        staged[rel] = res
    for field in ("stage", "digest", "fallback"):
        counts: dict[str, int] = {}
        for res in staged.values():
            if field in res:
                counts[res[field]] = counts.get(res[field], 0) + 1
        staging[{"stage": "staged_by", "digest": "digest_source",
                 "fallback": "link_fallback_errno"}[field]] = counts
    staging["seconds"] = round(time.monotonic() - t_stage, 3)

    canonical = manifest["canonical_movies"]
    for movie in canonical:
        root = star_io.worker_relative_root(star_io.output_root(movie))
        for suffix in products:
            rel = Path(star_io.movie_output_path(movie, suffix))
            if rel not in produced:
                problems.append(f"lost: {movie} has no {suffix} output "
                                f"(expected {rel}, shard {owner[movie]})")

    report: dict[str, object] = {
        "manifest": str(a.manifest),
        "aggregate_input_star_sha256": manifest_input_sha256,
        "merged_into": str(out),
        "input_type": input_type,
        "n_movies_expected": len(canonical),
        "n_files_staged": len(produced),
        "worker_exit_codes": exits,
        "launcher_verdict": launcher_verdict,
        "per_worker_aggregates_preserved": sorted(per_worker_aggregates),
        "staging": staging,
        "staged_sha256": {str(rel): res.get("sha256") for rel, res in sorted(staged.items())},
        "problems": problems,
        "verdict": "PASS" if not problems else "FAIL",
        "logfile_pdf": "not produced and not claimed equivalent; the PDF batch loop is "
                       "path-dependent by construction (see module docstring)",
    }

    if a.aggregate_with and not problems:
        changed = changed_inputs(input_digests)
        if changed:
            problems.append("aggregate input STAR changed after preflight; aggregate "
                            f"binary was not run: {changed}")

    timing = report["timing_seconds"] = {"staging": staging["seconds"]}
    if a.aggregate_with and not problems:
        # The stock binary verifies every movie before generating the complete
        # dataset STAR/report. --aggregate_only cannot process an incomplete movie,
        # and isMovieComplete() is option-dependent -- do_dose_weighting/save_noDW,
        # even_odd_split, grouping_for_ps, and since PR110 the per-movie expected
        # frame count (src/motioncorr_runner.cpp:596-620). If --aggregate-args does
        # not match what the workers ran, the binary refuses. Independently,
        # require every staged product to keep the stat key it had when staged:
        # any write changes mtime and ctime, a replacement changes the inode, and
        # ctime cannot be restored from userspace, so a same-byte rewrite is
        # caught too. The barrier first moves the filesystem clock past every
        # staged ctime, so a write in the same tick as staging cannot hide.
        #
        # A linked product shares its inode with the worker's file, so a rewrite
        # here also changes the worker's copy; the sha256 recorded at staging is
        # then the only reference to what the worker wrote.
        keys = [staged[rel]["dst_key"] for rel in produced]
        t0 = time.monotonic()
        (out / "_workers").mkdir(parents=True, exist_ok=True)
        try:
            output_digests.ctime_barrier(out / "_workers", max((k[4] for k in keys), default=0),
                                         {k[0] for k in keys})
        except RuntimeError as exc:
            problems.append(f"cannot order staged timestamps, aggregate binary was not "
                            f"run: {exc}")
        timing["ctime_barrier"] = round(time.monotonic() - t0, 3)
    if problems:
        report["aggregate_star"] = "not attempted: staging failed"
    elif a.aggregate_with:
        if not a.input_star:
            print("FAIL: --aggregate-with requires --input-star", file=sys.stderr)
            return 2
        cmd = [a.aggregate_with, "--i", str(Path(a.input_star).resolve()),
               "--o", str(out) + os.sep, "--aggregate_only"] + aggregate_extra
        t0 = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        timing["aggregate_binary"] = round(time.monotonic() - t0, 3)
        t0 = time.monotonic()
        changed = changed_inputs(input_digests)
        if changed:
            problems.append(f"aggregate input STAR changed while the aggregate binary ran: "
                            f"{changed}")

        def moved(rel: Path) -> tuple[Path, bool, bool]:
            """(rel, stat key changed, bytes changed)."""
            try:
                now = stat_key(os.stat(out / rel))
            except OSError:
                return rel, True, True
            if now == staged[rel]["dst_key"]:
                return rel, False, False
            try:
                return rel, True, output_digests.hash_file(out / rel, now) != staged[rel]["sha256"]
            except (OSError, FileChanged):
                return rel, True, True

        with ThreadPoolExecutor(max_workers=output_digests.pool_size()) as pool:
            after = [m for m in pool.map(moved, sorted(produced)) if m[1]]
        rewritten = [str(rel) for rel, _, _ in after]
        if rewritten:
            n_bytes = sum(1 for _, _, b in after if b)
            linked = sum(1 for rel, _, _ in after if staged[rel]["stage"] == "link")
            problems.append(
                f"aggregate step rewrote {len(rewritten)} staged worker product(s) "
                f"instead of only regenerating the dataset STAR: {rewritten[:5]}"
                + (" ..." if len(rewritten) > 5 else "")
                + f" ({n_bytes} with different bytes, the rest metadata only)."
                + (f" {linked} were hardlinks, so the workers' own copies changed with "
                   "them; staged_sha256 in this report records what was staged."
                   if linked else "")
                + " --aggregate_only must not process or rewrite per-movie products.")
        timing["after_check"] = round(time.monotonic() - t0, 3)
        (out / "_workers" / "merge.log").parent.mkdir(parents=True, exist_ok=True)
        (out / "_workers" / "merge.log").write_text(proc.stdout + proc.stderr)
        agg = {"command": cmd, "returncode": proc.returncode}
        if proc.returncode != 0:
            problems.append(f"aggregate step exited {proc.returncode}; see "
                            f"{out / '_workers' / 'merge.log'}")
        else:
            joint = joint_star_problems(out, manifest, input_type, agg)
            problems.extend(joint)
            if not joint:
                agg["row_order"] = "canonical"
        pdf = out / "logfile.pdf"
        if proc.returncode == 0:
            try:
                data = pdf.read_bytes()
                if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-1024:]:
                    problems.append("aggregate produced an invalid/truncated logfile.pdf")
                else:
                    report["logfile_pdf"] = "complete canonical report generated by aggregate-only binary"
            except OSError as exc:
                problems.append(f"aggregate report missing/unreadable: {exc}")
        report["dataset_ready"] = not problems
        report["aggregate_star"] = agg
        report["problems"] = problems
        report["verdict"] = "PASS" if not problems else "FAIL"
    else:
        report["aggregate_star"] = ("not requested; staged outputs only. No dataset STAR "
                                    "is claimed.")

    # Problems can be added after the report was first built (an input STAR
    # changed after preflight, the timestamp barrier failed), so the verdict is
    # taken from the final list.
    report["verdict"] = "PASS" if not problems else "FAIL"
    if a.report:
        Path(a.report).write_text(json.dumps(report, indent=2) + "\n")

    print(json.dumps({k: report[k] for k in
                      ("n_movies_expected", "n_files_staged", "verdict")}, indent=2))
    for p in problems:
        print("  " + p, file=sys.stderr)
    return 0 if report["verdict"] == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
