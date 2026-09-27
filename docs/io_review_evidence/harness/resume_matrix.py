#!/usr/bin/env python3
"""--only_do_unfinished resume behaviour after a damaged-input failure (PR #91).

Three runs over one output directory:

  run1  healthy + damaged batch, plain run. Expected to fail, retain the healthy
        per-movie products and withhold the joint outputs.
  run2  same inputs, --only_do_unfinished. The healthy products must not be
        regenerated -- proven by unchanged content hash AND unchanged mtime, not
        by hash alone, since a byte-identical rewrite would pass a hash check --
        and the damaged movie must be retried, proven from the runner's own
        "to correct beam-induced motion for the following micrographs" list.
  run3  damaged input replaced with healthy data, --only_do_unfinished again.
        Must complete, emit the joint STAR and logfile PDF it previously
        withheld, produce the formerly-damaged movie's products, and still leave
        the run1 healthy products untouched.

Whether run3's joint STAR covers all three movies is checked explicitly: a
resume that completes but silently drops the movies it skipped would be a
product bug, and is reported as one rather than smoothed over.
"""
import argparse
import hashlib
import json
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

OPTIONS = ["--use_own", "--dose_weighting", "--dose_per_frame", "1.277",
           "--patch_x", "5", "--patch_y", "5", "--bfactor", "150",
           "--gainref", "Movies/gain.mrc", "--seed", "1"]

JOINT_OUTPUTS = ["corrected_micrographs.star", "logfile.pdf"]

# Measured boundary; see damaged_matrix.py for the prefix-length sweep.
TRUNCATE_HARD_BYTES = 1 << 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def describe_exit(rc: int) -> dict:
    if rc < 0:
        return {"exit_code": rc, "kind": "signal", "signal": signal.Signals(-rc).name}
    if rc > 128:
        try:
            name = signal.Signals(rc - 128).name
        except ValueError:
            name = f"unknown({rc - 128})"
        return {"exit_code": rc, "kind": "signal", "signal": name}
    return {"exit_code": rc,
            "kind": "clean_success" if rc == 0 else "clean_failure"}


def snapshot(outdir: Path, stems: list) -> dict:
    """Content hash plus mtime for every per-movie product, and joint presence."""
    movies = outdir / "Movies"
    per_movie = {}
    for stem in stems:
        entry = {}
        for kind, path in (("image", movies / f"{stem}.mrc"),
                           ("model", movies / f"{stem}.star")):
            if path.is_file() and path.stat().st_size > 0:
                stat = path.stat()
                entry[kind] = {"sha256": sha256(path), "mtime_ns": stat.st_mtime_ns,
                               "bytes": stat.st_size}
            else:
                entry[kind] = None
        entry["complete"] = entry["image"] is not None and entry["model"] is not None
        per_movie[stem] = entry
    joint = {}
    for name in JOINT_OUTPUTS:
        path = outdir / name
        joint[name] = ({"sha256": sha256(path), "bytes": path.stat().st_size}
                       if path.is_file() and path.stat().st_size > 0 else None)
    return {"per_movie": per_movie, "joint": joint}


def unchanged(before: dict, after: dict, stem: str) -> dict:
    """Both hash and mtime must match, and the product must have existed."""
    b, a = before["per_movie"][stem], after["per_movie"][stem]
    out = {}
    for kind in ("image", "model"):
        if b[kind] is None or a[kind] is None:
            out[kind] = {"existed_before": b[kind] is not None,
                         "exists_after": a[kind] is not None,
                         "not_regenerated": False}
            continue
        out[kind] = {
            "sha256_same": b[kind]["sha256"] == a[kind]["sha256"],
            "mtime_same": b[kind]["mtime_ns"] == a[kind]["mtime_ns"],
            "not_regenerated": (b[kind]["sha256"] == a[kind]["sha256"]
                                and b[kind]["mtime_ns"] == a[kind]["mtime_ns"]),
        }
    out["not_regenerated"] = all(out[k]["not_regenerated"] for k in ("image", "model"))
    return out


def scheduled_movies(stdout: str) -> list:
    """The runner's own list of what this invocation will process."""
    marker = "to correct beam-induced motion for the following micrographs:"
    if marker not in stdout:
        return []
    tail = stdout.split(marker, 1)[1]
    names = []
    for line in tail.splitlines():
        stripped = line.strip()
        if stripped.startswith("* "):
            names.append(Path(stripped[2:].strip()).stem)
        elif names and stripped and not stripped.startswith("("):
            break
    return names


def star_micrograph_names(path: Path) -> list:
    if not path.is_file():
        return []
    names = []
    for line in path.read_text().splitlines():
        for field in line.split():
            if field.endswith(".mrc") and "/" in field:
                names.append(Path(field).stem)
                break
    return names


def run(binary: Path, cwd: Path, star: str, outdir: Path, threads: int,
        resume: bool) -> dict:
    cmd = [str(binary), "--i", star, "--o", str(outdir), *OPTIONS,
           "--j", str(threads), "--pipeline_control", str(outdir) + "/"]
    if resume:
        cmd.append("--only_do_unfinished")
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    result = {"command": cmd, "stdout_tail": proc.stdout[-6000:],
              "stderr_tail": proc.stderr[-4000:],
              "scheduled_movies": scheduled_movies(proc.stdout),
              "markers": {n: (Path(str(outdir) + "/" + n)).is_file()
                          for n in ("RELION_JOB_EXIT_SUCCESS",
                                    "RELION_JOB_EXIT_FAILURE",
                                    "RELION_JOB_EXIT_ABORTED")}}
    result.update(describe_exit(proc.returncode))
    return result


def write_star(path: Path, template: Path, movie_names: list) -> None:
    text = template.read_text()
    prefix = text.split("Movies/", 1)[0]
    lines = [l for l in text.splitlines(keepends=True) if l.lstrip().startswith("Movies/")]
    by_name = {Path(l.split()[0]).name: l for l in lines}
    body = "".join(by_name[n] if n in by_name
                   else lines[0].replace(Path(lines[0].split()[0]).name, n)
                   for n in movie_names)
    path.write_text(prefix + body)


def clear_markers(outdir: Path) -> None:
    for name in ("RELION_JOB_EXIT_SUCCESS", "RELION_JOB_EXIT_FAILURE",
                 "RELION_JOB_EXIT_ABORTED"):
        (outdir / name).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--tutorial", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--healthy", nargs="+",
                        default=["20170629_00021_frameImage.tiff",
                                 "20170629_00022_frameImage.tiff"])
    parser.add_argument("--donor", default="20170629_00023_frameImage.tiff")
    args = parser.parse_args()

    sandbox = args.work / "inputs"
    if sandbox.exists():
        shutil.rmtree(sandbox)
    (sandbox / "Movies").mkdir(parents=True)
    for name in set(args.healthy) | {args.donor}:
        shutil.copy2(args.tutorial / "Movies" / name, sandbox / "Movies" / name)
    shutil.copy2(args.tutorial / "Movies" / "gain.mrc", sandbox / "Movies" / "gain.mrc")

    damaged_name = "RESUME_frameImage.tiff"
    damaged_stem = Path(damaged_name).stem
    damaged_path = sandbox / "Movies" / damaged_name
    donor_path = sandbox / "Movies" / args.donor

    # Truncated frame data, short enough that no complete image directory
    # survives so the read itself fails. A longer prefix is a different
    # phenomenon -- the file is accepted with fewer frames -- and is exercised
    # as a labelled observation in damaged_matrix.py, not here.
    raw = donor_path.read_bytes()
    damaged_path.write_bytes(raw[:TRUNCATE_HARD_BYTES])

    movie_names = list(args.healthy) + [damaged_name]
    healthy_stems = [Path(n).stem for n in args.healthy]
    all_stems = healthy_stems + [damaged_stem]

    star = sandbox / "resume_batch.star"
    write_star(star, args.tutorial / "movies.star", movie_names)

    outdir = args.work / f"out_{args.label}_resume"
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)

    report = {
        "what": f"--only_do_unfinished resume after damaged-input failure, {args.label}",
        "binary": str(args.binary), "binary_sha256": sha256(args.binary),
        "options": OPTIONS, "threads": args.threads,
        "movies": movie_names,
        "damaged_truncated_bytes": TRUNCATE_HARD_BYTES,
        "damaged_original_bytes": len(raw),
        "input_hashes": {p.name: sha256(p)
                         for p in sorted((sandbox / "Movies").glob("*"))},
    }

    # --- run 1: plain run, must fail and withhold the joint outputs ----------
    report["run1"] = run(args.binary, sandbox, star.name, outdir, args.threads, False)
    after1 = snapshot(outdir, all_stems)
    report["state_after_run1"] = after1
    report["run1_checks"] = {
        "nonzero_exit": report["run1"]["exit_code"] != 0,
        "clean_failure_not_signal": report["run1"]["kind"] == "clean_failure",
        "healthy_complete": all(after1["per_movie"][s]["complete"] for s in healthy_stems),
        "damaged_absent": not after1["per_movie"][damaged_stem]["complete"],
        "joint_withheld": all(after1["joint"][n] is None for n in JOINT_OUTPUTS),
        "failure_marker": report["run1"]["markers"]["RELION_JOB_EXIT_FAILURE"],
        "success_marker_absent": not report["run1"]["markers"]["RELION_JOB_EXIT_SUCCESS"],
    }

    clear_markers(outdir)
    # Filesystem mtime granularity: make any rewrite in run 2 visibly newer.
    time.sleep(1.1)

    # --- run 2: resume, must skip the healthy work and retry the damaged one -
    report["run2"] = run(args.binary, sandbox, star.name, outdir, args.threads, True)
    after2 = snapshot(outdir, all_stems)
    report["state_after_run2"] = after2
    report["run2_not_regenerated"] = {s: unchanged(after1, after2, s) for s in healthy_stems}
    report["run2_checks"] = {
        "nonzero_exit": report["run2"]["exit_code"] != 0,
        "clean_failure_not_signal": report["run2"]["kind"] == "clean_failure",
        "healthy_not_regenerated": all(report["run2_not_regenerated"][s]["not_regenerated"]
                                       for s in healthy_stems),
        "damaged_retried_per_runner_log": report["run2"]["scheduled_movies"] == [damaged_stem],
        "healthy_not_scheduled": all(s not in report["run2"]["scheduled_movies"]
                                     for s in healthy_stems),
        "damaged_named_in_error": damaged_stem in report["run2"]["stderr_tail"],
        "joint_still_withheld": all(after2["joint"][n] is None for n in JOINT_OUTPUTS),
        "failure_marker": report["run2"]["markers"]["RELION_JOB_EXIT_FAILURE"],
    }

    clear_markers(outdir)
    time.sleep(1.1)

    # --- run 3: healthy replacement, resume, must complete -------------------
    shutil.copyfile(donor_path, damaged_path)
    report["replacement"] = {"source": str(donor_path),
                             "sha256": sha256(damaged_path),
                             "bytes": damaged_path.stat().st_size}
    report["run3"] = run(args.binary, sandbox, star.name, outdir, args.threads, True)
    after3 = snapshot(outdir, all_stems)
    report["state_after_run3"] = after3
    report["run3_not_regenerated"] = {s: unchanged(after1, after3, s) for s in healthy_stems}
    joint_star = outdir / "corrected_micrographs.star"
    covered = star_micrograph_names(joint_star)
    report["joint_star_coverage"] = {"names": covered,
                                     "expected": sorted(all_stems),
                                     "complete": sorted(covered) == sorted(all_stems)}
    report["run3_checks"] = {
        "zero_exit": report["run3"]["exit_code"] == 0,
        "all_movies_complete": all(after3["per_movie"][s]["complete"] for s in all_stems),
        "formerly_damaged_now_produced": after3["per_movie"][damaged_stem]["complete"],
        "healthy_still_not_regenerated": all(report["run3_not_regenerated"][s]["not_regenerated"]
                                             for s in healthy_stems),
        "joint_star_present": after3["joint"]["corrected_micrographs.star"] is not None,
        "joint_pdf_present": after3["joint"]["logfile.pdf"] is not None,
        "joint_star_covers_all_movies": report["joint_star_coverage"]["complete"],
        "success_marker": report["run3"]["markers"]["RELION_JOB_EXIT_SUCCESS"],
        "failure_marker_absent": not report["run3"]["markers"]["RELION_JOB_EXIT_FAILURE"],
    }

    groups = {k: report[k] for k in ("run1_checks", "run2_checks", "run3_checks")}
    report["summary"] = {g: {"pass": sum(1 for v in c.values() if v is True),
                             "total": len(c),
                             "unmet": [k for k, v in c.items() if v is not True]}
                         for g, c in groups.items()}
    report["overall"] = ("PASS" if all(v is True for c in groups.values() for v in c.values())
                         else "FAIL")

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    print("overall:", report["overall"])
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
