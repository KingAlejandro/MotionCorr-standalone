#!/usr/bin/env python3
"""Portable product controls. Wall/RSS values are diagnostic, not speed verdicts.

The synthetic local-j4 block has one warmup and three alternating measured pairs;
remaining blocks have one identity pair. The existing strict comparator checks
all products outside timing. No legacy fixed-mask harness is invoked.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from cpu_venue import add_arguments, validate


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    for name in ("base", "candidate", "data", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("base", "candidate"):
        parser.add_argument("--" + name + "-source-sha", required=True,
                            help="Full source commit used to build this binary (caller attestation, not driver HEAD)")
    args = parser.parse_args()
    for name in ("base", "candidate"):
        if not re.fullmatch(r"[0-9a-f]{40}", getattr(args, name + "_source_sha")):
            parser.error("--" + name + "-source-sha must be a full 40-character lowercase SHA")
    venue = validate(args)  # Fail before outputs, hashing, or child launch.
    args.out.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / "tools/profiling"))
    from lib import identity, provenance
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    binaries = {"base": args.base.resolve(strict=True), "candidate": args.candidate.resolve(strict=True)}
    data = args.data.resolve(strict=True)
    env = dict(os.environ, OMP_DYNAMIC="false", OMP_PROC_BIND="close", OMP_PLACES="cores", OPENBLAS_NUM_THREADS="1")
    receipt = {"driver_source": source, "driver_sha256": digest(Path(__file__).resolve()), "venue": venue,
               "platform": platform.platform(),
               "binaries": {k: {"path": str(v), "sha256": digest(v),
                                "source": {"commit": getattr(args, k + "_source_sha"),
                                           "origin": "caller-attested build source SHA", "dirty": None}}
                            for k, v in binaries.items()},
               "inputs": {p.name: digest(p) for p in (data / "synthetic_512x512_16frames.mrcs", data / "tutorial.tiff", data / "gain.mrc")},
               "environment": {k: env.get(k, "runtime default") for k in
                               ("OMP_DYNAMIC", "OMP_PROC_BIND", "OMP_PLACES", "OMP_WAIT_POLICY", "OPENBLAS_NUM_THREADS")},
               "scope": "identity controls with diagnostic spawn-to-reap wall and wait4 rusage",
               "performance_verdict": "unresolved: three synthetic pairs or one identity pair, not a movie-speed claim",
               "limitation": "Cooperating benchmark lock and validated CPU masks do not certify host-wide workload isolation; local-container /proc ownership is not certified",
               "runs": [], "comparisons": []}

    def save():
        (args.out / "identity-results.json").write_text(json.dumps(receipt, indent=2) + "\n")

    cases = [("synthetic", 5, 4, 3, True), ("synthetic", 1, 1, 1, False),
             ("synthetic", 1, 4, 1, False), ("synthetic", 5, 1, 1, False),
             ("tutorial", 5, 4, 1, False)]
    with open("/tmp/motioncorr-bench.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if provenance.compilers_running():
            raise RuntimeError("Compiler detected; finish builds before product checks")
        for geometry, patch, threads, repeats, warmup in cases:
            mask = venue["masks"][threads]
            label = f"{geometry}-patch{patch}-j{threads}"
            observed = json.loads(subprocess.check_output(["taskset", "-c", mask, sys.executable, "-c",
                                                          "import json,os; print(json.dumps(sorted(os.sched_getaffinity(0))))"]))
            if observed != venue["requested_affinity"][threads]:
                raise RuntimeError(f"taskset did not establish requested CPU mask: {mask}, observed {observed}")
            env["OMP_NUM_THREADS"] = str(threads)
            movie = data / ("tutorial.tiff" if geometry == "tutorial" else "synthetic_512x512_16frames.mrcs")
            for rep in range(-1 if warmup else 0, repeats):
                trees = {}
                order = ("base", "candidate") if rep == -1 or rep % 2 == 0 else ("candidate", "base")
                for arm in order:
                    out = (args.out / label / f"r{rep}-{arm}").resolve()
                    trees[arm] = str(out)
                    command = ["taskset", "-c", mask, str(binaries[arm]), "--i", str(movie), "--o", str(out),
                               "--use_own", "--j", str(threads), "--angpix", "0.885" if geometry == "tutorial" else "1",
                               "--voltage", "300", "--bfactor", "150", "--seed", "1", "--patch_x", str(patch), "--patch_y", str(patch)]
                    if geometry == "tutorial":
                        command += ["--gainref", str(data / "gain.mrc")]
                    if patch == 5:
                        command += ["--dose_weighting", "--dose_per_frame", "1.277", "--save_noDW", "--even_odd_split"]
                    with (args.out / f"{label}-r{rep}-{arm}.log").open("w") as log:
                        started = time.monotonic()
                        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
                        _, status, usage = os.wait4(child.pid, 0)
                        wall = time.monotonic() - started
                        child.returncode = os.waitstatus_to_exitcode(status)
                    receipt["runs"].append({"case": label, "rep": rep, "warmup": rep == -1,
                                            "arm": arm, "command": command, "rc": child.returncode,
                                            "cpu_mask": mask, "verified_self_affinity": observed,
                                            "wall_diagnostic_seconds": wall, "user_seconds": usage.ru_utime,
                                            "sys_seconds": usage.ru_stime, "peak_rss_kib": usage.ru_maxrss})
                    save()
                    if child.returncode:
                        raise RuntimeError(f"{label}/{arm} failed {child.returncode}; evidence retained")
                    print(label, rep, arm, "diagnostic wall", wall, flush=True)
                comparison = identity.compare_trees(trees["base"], trees["candidate"])
                receipt["comparisons"].append({"case": label, "rep": rep, "warmup": rep == -1, **comparison})
                save()
                if not comparison["identical"]:
                    raise RuntimeError(f"Product identity failed: {label}")

    def canonical(path, root):
        h = hashlib.sha256()
        if path.suffix.lower() in (".mrc", ".mrcs"):
            with path.open("rb") as f:
                h.update(identity.normalise_mrc_header(f.read(1024)))
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
        else:
            h.update(identity.normalise(path.read_bytes(), str(root)))
        return h.hexdigest()

    hashes = []
    for comparison in receipt["comparisons"]:
        a, b = Path(comparison["root_a"]), Path(comparison["root_b"])
        for rel in identity.inventory(str(a)):
            if Path(rel).suffix.lower() not in (".mrc", ".mrcs", ".star"):
                continue
            ah, bh = canonical(a / rel, a), canonical(b / rel, b)
            if ah != bh:
                raise RuntimeError(f"Canonical hash differs: {a}, {b}, {rel}")
            hashes.append({"root_a": str(a), "root_b": str(b), "file": rel,
                           "base_canonical_sha256": ah, "candidate_canonical_sha256": bh})
    (args.out / "canonical-product-hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")


if __name__ == "__main__":
    main()
