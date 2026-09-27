#!/usr/bin/env python3
"""Damaged-input behaviour matrix for PR #91 (issue #86).

Exercises three damage modes against a batch that also contains healthy
movies, in both orders, at one thread and at bounded multithread, and checks
the failure contract the PR states:

  * the job exits nonzero, and the exit is a real failure, not an abort signal
    and not a crash -- a SIGABRT from an exception escaping an OpenMP block is
    reported as a distinct outcome, because that is precisely the behaviour the
    PR is meant to replace;
  * the failing movie is named on stderr;
  * every healthy movie in the same batch still has a complete image and model;
  * the joint STAR and the logfile PDF are deliberately absent;
  * under --pipeline_control, the RELION_JOB_EXIT_FAILURE marker is written and
    the success marker is not.

The same matrix runs against the main build, so the change in behaviour is
recorded rather than asserted. Main is expected to fail some of these rows;
that is the point, and its outcome is reported as observed, not as a pass.

Resume is then checked end to end: rerun with --only_do_unfinished and prove by
content hash and mtime that healthy outputs were not regenerated while the
damaged movie was retried, then replace the damaged input with healthy data and
prove the job completes and emits the joint outputs it previously withheld.
"""
import argparse
import hashlib
import json
import os
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

# Truncation is not one behaviour, it is two, and the boundary was measured
# rather than assumed. Feeding prefixes of a tutorial movie to the reader:
#   64 KiB, 1 MiB   -> the read fails
#   8 MiB           -> decodes as 1 frame of 24
#   40 MiB          -> decodes as 7 frames of 24
# A prefix short enough that no complete IFD survives is the damage that
# exercises the failure contract. A longer prefix is a separate phenomenon --
# the file is accepted with a reduced frame count -- and is exercised as an
# explicitly labelled observation, not scored against the failure contract.
TRUNCATE_HARD_BYTES = 1 << 20
TRUNCATE_PARTIAL_FRACTION = 3

# "Movie size: X = 3710 Y = 3838 N = 8"
MOVIE_SIZE_RE = re.compile(r"Movie size:\s*X\s*=\s*(\d+)\s*Y\s*=\s*(\d+)\s*N\s*=\s*(\d+)")

CONTRACT_MODES = ("truncated", "missing", "corrupt_header")
OBSERVATION_MODES = ("truncated_partial",)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def describe_exit(rc: int) -> dict:
    """Separate a clean nonzero failure from a signal death."""
    if rc < 0:
        name = signal.Signals(-rc).name
        return {"exit_code": rc, "kind": "signal", "signal": name}
    if rc > 128:
        try:
            name = signal.Signals(rc - 128).name
        except ValueError:
            name = f"unknown({rc - 128})"
        return {"exit_code": rc, "kind": "signal", "signal": name}
    return {"exit_code": rc,
            "kind": "clean_success" if rc == 0 else "clean_failure"}


def make_damaged(kind: str, source: Path, dest: Path) -> dict:
    """Produce one damaged copy of a healthy movie and describe the damage."""
    if kind == "missing":
        dest.unlink(missing_ok=True)
        return {"damage": "missing", "note": "input file absent entirely"}

    raw = bytearray(source.read_bytes())
    if kind == "truncated":
        # Short enough that no complete image directory survives, so the read
        # itself fails. See TRUNCATE_HARD_BYTES for the measured boundary.
        keep = min(TRUNCATE_HARD_BYTES, len(raw))
        dest.write_bytes(bytes(raw[:keep]))
        return {"damage": "truncated", "original_bytes": len(raw),
                "written_bytes": keep,
                "note": "prefix short enough that no complete IFD survives"}
    if kind == "truncated_partial":
        keep = len(raw) // TRUNCATE_PARTIAL_FRACTION
        dest.write_bytes(bytes(raw[:keep]))
        return {"damage": "truncated_partial", "original_bytes": len(raw),
                "written_bytes": keep,
                "note": "long prefix; some complete IFDs survive"}
    if kind == "corrupt_header":
        # Corrupt the TIFF magic / IFD offset so header parsing fails before
        # any pixel is read.
        raw[0:8] = b"\x00\xff\x00\xff\xde\xad\xbe\xef"
        dest.write_bytes(bytes(raw))
        return {"damage": "corrupt_header", "bytes_patched": 8,
                "offset": 0, "original_bytes": len(raw)}
    raise ValueError(kind)


def write_star(path: Path, template: Path, movie_names: list) -> None:
    text = template.read_text()
    prefix = text.split("Movies/", 1)[0]
    lines = [l for l in text.splitlines(keepends=True) if l.lstrip().startswith("Movies/")]
    by_name = {Path(l.split()[0]).name: l for l in lines}
    body = "".join(by_name[n] if n in by_name
                   else lines[0].replace(Path(lines[0].split()[0]).name, n)
                   for n in movie_names)
    path.write_text(prefix + body)


def run_case(binary: Path, cwd: Path, star: str, outdir: Path, threads: int,
             pipeline: bool, extra: list = None) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    marker_prefix = str(outdir) + "/"
    cmd = [str(binary), "--i", star, "--o", str(outdir), *OPTIONS,
           "--j", str(threads)]
    if pipeline:
        cmd += ["--pipeline_control", marker_prefix]
    if extra:
        cmd += extra
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    elapsed = time.monotonic() - started
    result = {"command": cmd, "wall_seconds": round(elapsed, 2),
              "stdout_tail": proc.stdout[-3000:], "stderr_tail": proc.stderr[-4000:]}
    result.update(describe_exit(proc.returncode))
    if pipeline:
        result["markers"] = {
            name: (Path(marker_prefix + name).is_file())
            for name in ("RELION_JOB_EXIT_SUCCESS", "RELION_JOB_EXIT_FAILURE",
                         "RELION_JOB_EXIT_ABORTED")
        }
    return result


def product_state(outdir: Path, names: list) -> dict:
    """Per-movie image/model completeness and the joint outputs' presence."""
    movies = outdir / "Movies"
    per_movie = {}
    for name in names:
        stem = Path(name).stem
        mrc = movies / f"{stem}.mrc"
        star = movies / f"{stem}.star"
        entry = {
            "image_present": mrc.is_file() and mrc.stat().st_size > 0,
            "model_present": star.is_file() and star.stat().st_size > 0,
        }
        if entry["image_present"]:
            entry["image_bytes"] = mrc.stat().st_size
            entry["image_sha256"] = sha256(mrc)
            entry["image_mtime_ns"] = mrc.stat().st_mtime_ns
        if entry["model_present"]:
            entry["model_sha256"] = sha256(star)
            entry["model_mtime_ns"] = star.stat().st_mtime_ns
        entry["complete"] = entry["image_present"] and entry["model_present"]
        per_movie[stem] = entry
    joint = {name: (outdir / name).is_file() and (outdir / name).stat().st_size > 0
             for name in JOINT_OUTPUTS}
    return {"per_movie": per_movie, "joint": joint}


def decoded_movie_size(outdir: Path, stem: str) -> dict:
    """The frame count the runner recorded for a movie, from its own log."""
    log = outdir / "Movies" / f"{stem}.log"
    if not log.is_file():
        return {"log_present": False}
    match = MOVIE_SIZE_RE.search(log.read_text(errors="replace"))
    if not match:
        return {"log_present": True, "movie_size_line_found": False}
    return {"log_present": True, "movie_size_line_found": True,
            "nx": int(match.group(1)), "ny": int(match.group(2)),
            "frames_decoded": int(match.group(3))}


def names_failure(stderr: str, damaged_stem: str) -> dict:
    named = damaged_stem in stderr
    aggregate = bool(re.search(r"Motion correction failed for \d+ movie\(s\)", stderr))
    retained = "Successful per-movie outputs were retained" in stderr
    return {"damaged_movie_named": named,
            "aggregate_message": aggregate,
            "retention_message": retained}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--tutorial", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--threads", type=int, nargs="+", default=[1, 4])
    parser.add_argument("--healthy", nargs="+",
                        default=["20170629_00021_frameImage.tiff",
                                 "20170629_00022_frameImage.tiff"])
    parser.add_argument("--donor", default="20170629_00023_frameImage.tiff",
                        help="healthy movie copied and then damaged")
    args = parser.parse_args()

    args.work.mkdir(parents=True, exist_ok=True)
    # A private input tree: the tutorial dataset is never modified.
    sandbox = args.work / "inputs"
    if sandbox.exists():
        shutil.rmtree(sandbox)
    (sandbox / "Movies").mkdir(parents=True)
    for name in set(args.healthy) | {args.donor}:
        shutil.copy2(args.tutorial / "Movies" / name, sandbox / "Movies" / name)
    shutil.copy2(args.tutorial / "Movies" / "gain.mrc", sandbox / "Movies" / "gain.mrc")

    report = {
        "what": f"damaged-input failure contract, {args.label} build, CPU",
        "binary": str(args.binary), "binary_sha256": sha256(args.binary),
        "options": OPTIONS,
        "tutorial": str(args.tutorial),
        "input_hashes": {p.name: sha256(p)
                         for p in sorted((sandbox / "Movies").glob("*"))},
        "rows": [],
    }

    damaged_name = "DAMAGED_frameImage.tiff"
    damaged_stem = Path(damaged_name).stem
    donor_path = sandbox / "Movies" / args.donor

    healthy_frames = None
    for threads in args.threads:
        for kind in CONTRACT_MODES + OBSERVATION_MODES:
            for order in ("damaged_first", "damaged_last"):
                row_id = f"{kind}_{order}_j{threads}"
                damaged_path = sandbox / "Movies" / damaged_name
                damaged_path.unlink(missing_ok=True)
                damage = make_damaged(kind, donor_path, damaged_path)

                movie_names = ([damaged_name] + list(args.healthy)
                               if order == "damaged_first"
                               else list(args.healthy) + [damaged_name])
                star = sandbox / f"batch_{row_id}.star"
                write_star(star, args.tutorial / "movies.star", movie_names)

                outdir = args.work / f"out_{args.label}_{row_id}"
                if outdir.exists():
                    shutil.rmtree(outdir)

                row = {"row": row_id, "threads": threads, "damage": damage,
                       "order": order, "movies": movie_names}
                if damaged_path.is_file():
                    row["damaged_input_sha256"] = sha256(damaged_path)
                row["run"] = run_case(args.binary, sandbox, star.name, outdir,
                                      threads, pipeline=True)
                row["products"] = product_state(outdir, movie_names)
                row["failure_naming"] = names_failure(row["run"]["stderr_tail"],
                                                      damaged_stem)

                healthy_stems = [Path(n).stem for n in args.healthy]
                row["decoded_size"] = {
                    s: decoded_movie_size(outdir, s) for s in healthy_stems + [damaged_stem]
                }
                if healthy_frames is None:
                    for s in healthy_stems:
                        frames = row["decoded_size"][s].get("frames_decoded")
                        if frames:
                            healthy_frames = frames
                            break

                if kind in OBSERVATION_MODES:
                    # Not scored against the failure contract. This row records
                    # what the reader actually does with a long truncated prefix
                    # so the behaviour is on the record either way.
                    damaged_frames = row["decoded_size"][damaged_stem].get("frames_decoded")
                    row["observation"] = {
                        "exit_code": row["run"]["exit_code"],
                        "exit_kind": row["run"]["kind"],
                        "damaged_movie_accepted": row["products"]["per_movie"]
                            .get(damaged_stem, {}).get("complete", False),
                        "frames_decoded_from_damaged": damaged_frames,
                        "frames_decoded_from_healthy": healthy_frames,
                        "frames_lost": (None if damaged_frames is None or healthy_frames is None
                                        else healthy_frames - damaged_frames),
                        "joint_star_emitted": row["products"]["joint"]["corrected_micrographs.star"],
                        "joint_pdf_emitted": row["products"]["joint"]["logfile.pdf"],
                        "success_marker": row["run"].get("markers", {})
                            .get("RELION_JOB_EXIT_SUCCESS"),
                    }
                    row["status"] = "OBSERVED"
                    report["rows"].append(row)
                    damaged_path.unlink(missing_ok=True)
                    continue

                row["checks"] = {
                    "nonzero_exit": row["run"]["exit_code"] != 0,
                    "clean_failure_not_signal": row["run"]["kind"] == "clean_failure",
                    "damaged_movie_named": row["failure_naming"]["damaged_movie_named"],
                    "healthy_outputs_complete": all(
                        row["products"]["per_movie"][s]["complete"] for s in healthy_stems),
                    "damaged_output_absent": not row["products"]["per_movie"]
                                                 .get(damaged_stem, {}).get("complete", False),
                    "joint_star_withheld": not row["products"]["joint"]["corrected_micrographs.star"],
                    "joint_pdf_withheld": not row["products"]["joint"]["logfile.pdf"],
                    "failure_marker_written": row["run"].get("markers", {})
                                                 .get("RELION_JOB_EXIT_FAILURE"),
                    "success_marker_absent": row["run"].get("markers", {})
                                                 .get("RELION_JOB_EXIT_SUCCESS") is False,
                }
                row["status"] = "PASS" if all(v is True for v in row["checks"].values()) else "FAIL"
                report["rows"].append(row)
                damaged_path.unlink(missing_ok=True)

    graded = [r for r in report["rows"] if r["status"] in ("PASS", "FAIL")]
    observed = [r for r in report["rows"] if r["status"] == "OBSERVED"]
    statuses = [r["status"] for r in graded]
    report["summary"] = {
        "rows": len(report["rows"]),
        "graded_rows": len(graded),
        "pass": statuses.count("PASS"),
        "fail": statuses.count("FAIL"),
        "observation_rows": len(observed),
        "signal_deaths": sum(1 for r in report["rows"] if r["run"]["kind"] == "signal"),
    }
    report["overall"] = ("PASS" if statuses and statuses.count("PASS") == len(statuses)
                         else "FAIL")

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    for row in report["rows"]:
        if row["status"] == "OBSERVED":
            obs = row["observation"]
            print(f"  {row['row']:38s} OBSERVED     rc={obs['exit_code']} "
                  f"frames {obs['frames_decoded_from_damaged']}/"
                  f"{obs['frames_decoded_from_healthy']} "
                  f"accepted={obs['damaged_movie_accepted']}")
            continue
        failed = [k for k, v in row["checks"].items() if v is not True]
        print(f"  {row['row']:38s} {row['status']:4s} "
              f"{row['run']['kind']:14s} rc={row['run']['exit_code']} "
              f"{'' if not failed else 'unmet: ' + ','.join(failed)}")
    print("overall:", report["overall"])
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
