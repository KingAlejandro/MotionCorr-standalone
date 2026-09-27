#!/usr/bin/env python3
"""Run the declared issue #83 support matrix and record raw per-case verdicts.

For every declared row this executes an uninterrupted run and then the declared
schedules -- identical repeat, per-movie batch, and non-prefix resume -- and
requires the corrected pixels and metadata of every movie to be identical
across schedules. Equality is decided by ``tools/compare_motioncorr.py --gate
exact``, invoked as a subprocess so its thresholds stay exactly as merged.

Nothing here converts an exit status or a count into a pixel claim: a row is
only recorded ``pass`` when every movie has a complete product inventory, a
readable header, original-pixel metadata, a native-execution witness, and an
exact comparator verdict for every declared schedule.

Usage (CUDA):

    python3 tools/validation_issue83/run_matrix.py \
        --binary build-cuda/motioncorr --gpu 0 \
        --fixtures-dir /path/to/known_motion --outdir evidence/matrix

Omitting ``--gpu`` selects the CPU backend; that is recorded as a separate
diagnostic verdict and never as native CUDA evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matrix as declared  # noqa: E402
import products as prod  # noqa: E402
from products import output_stem  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Native-execution witness strings. These are the same markers
#: ``tools/run_known_motion_gates.py`` already uses; they are not redefined.
CUDA_STARTUP = "Using CUDA acceleration on GPU device "
CUDA_COMPLETED = "[CUDA "


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ------------------------------------------------------------------ fixtures

def write_mrc(path: Path, data: List[List[float]], mode: int = 2) -> None:
    """Write a minimal 2D float32 MRC, used for generated gain references."""
    ny = len(data)
    nx = len(data[0])
    header = bytearray(1024)
    struct.pack_into("<4i", header, 0, nx, ny, 1, mode)
    struct.pack_into("<3i", header, 28, nx, ny, 1)
    struct.pack_into("<3f", header, 40, float(nx), float(ny), 1.0)
    struct.pack_into("<3i", header, 64, 1, 2, 3)
    header[208:212] = b"MAP "
    struct.pack_into("<i", header, 212, 0x00004144)
    with path.open("wb") as handle:
        handle.write(header)
        for row in data:
            handle.write(struct.pack(f"<{nx}f", *row))


def build_aux_fixtures(work: Path, nx: int, ny: int) -> Dict[str, str]:
    """Unity gain, a non-unity gain and a small defect file for this geometry."""
    work.mkdir(parents=True, exist_ok=True)
    unity = work / "gain_unity.mrc"
    write_mrc(unity, [[1.0] * nx for _ in range(ny)])

    # A smooth, strictly positive, non-unity multiplicative field.
    nonunity = work / "gain_nonunity.mrc"
    write_mrc(nonunity, [[0.90 + 0.20 * ((x + y) % 7) / 6.0 for x in range(nx)]
                         for y in range(ny)])

    # MotionCor2-style defect list: "x y w h", 0-indexed, inside the canvas.
    defect = work / "defects.txt"
    defect.write_text(f"{nx // 4} {ny // 4} 3 3\n{nx // 2} {ny // 2} 1 5\n")
    return {"@GAIN_UNITY@": str(unity), "@GAIN_NONUNITY@": str(nonunity),
            "@DEFECT_FILE@": str(defect)}


def build_dataset(work: Path, fixture: str, fixtures_dir: Path, n_movies: int,
                  geometry: Dict[str, Any]) -> Dict[str, Any]:
    """Materialise an ``n_movies``-movie dataset from one declared fixture.

    The same movie payload appears under distinct names. That is intentional:
    these rows test scheduling, completion and product inventory, so identical
    content makes any cross-movie mix-up visible rather than hiding it.
    """
    movies_dir = work / "Movies"
    movies_dir.mkdir(parents=True, exist_ok=True)
    source = fixtures_dir / f"{fixture}.mrcs"
    if not source.exists():
        raise SystemExit(f"fixture movie not found: {source}")

    names, stems = [], []
    for index in range(n_movies):
        name = f"{fixture}_m{index + 1:02d}"
        target = movies_dir / f"{name}.mrcs"
        if not target.exists():
            shutil.copyfile(source, target)
        names.append(name)
        # The runner keeps the movie's relative directory in the output path,
        # so products land under <outdir>/Movies/<name>.*, not at the top level.
        stems.append(output_stem(f"Movies/{name}.mrcs"))

    star = work / "movies.star"
    lines = [
        "# version 30001", "", "data_optics", "", "loop_",
        "_rlnOpticsGroupName #1", "_rlnOpticsGroup #2",
        "_rlnMicrographOriginalPixelSize #3", "_rlnVoltage #4",
        "_rlnSphericalAberration #5", "_rlnAmplitudeContrast #6",
        f"opticsGroup1 1 {geometry['angpix']:.6f} {geometry['voltage']} 2.7 0.1",
        "", "", "# version 30001", "", "data_movies", "", "loop_",
        "_rlnMicrographMovieName #1", "_rlnOpticsGroup #2",
    ]
    lines += [f"Movies/{name}.mrcs 1" for name in names]
    star.write_text("\n".join(lines) + "\n")

    # A second STAR holding only the middle movie, used to create a non-prefix
    # completion state before resuming the full dataset.
    middle_index = len(names) // 2
    single = work / "movies_nonprefix.star"
    single.write_text(
        "\n".join(lines[:-n_movies] + [f"Movies/{names[middle_index]}.mrcs 1"]) + "\n")
    middle = stems[middle_index]

    return {"star": star, "nonprefix_star": single, "stems": stems,
            "nonprefix_stem": middle, "movie_sha256": sha256(source)}


# ----------------------------------------------------------------- execution

def backend_witness(stdout: str, out_dir: Path, stems: List[str],
                    gpu: Optional[int]) -> Dict[str, Any]:
    """Observe which backend actually ran, per movie.

    Mirrors the markers in ``tools/run_known_motion_gates.py``. CPU runs must
    show no CUDA marker at all, so a CPU masquerade cannot pass as native.
    """
    per_movie = {}
    for stem in stems:
        log = out_dir / f"{stem}.log"
        text = log.read_text(errors="replace") if log.exists() else ""
        per_movie[stem] = {
            "log_present": log.exists(),
            "cuda_stage_marker": CUDA_COMPLETED in text and "] completed;" in text,
        }
    if gpu is None:
        return {
            "requested": "cpu",
            "startup_marker_found": False,
            "unexpected_cuda_marker": (CUDA_STARTUP in stdout
                                       or any(m["cuda_stage_marker"] for m in per_movie.values())),
            "per_movie": per_movie,
            "native_cuda_proven": False,
        }
    startup = f"{CUDA_STARTUP}{gpu} for global alignment." in stdout
    all_stages = bool(per_movie) and all(m["cuda_stage_marker"] for m in per_movie.values())
    return {
        "requested": "cuda", "gpu": gpu,
        "startup_marker_found": startup,
        "per_movie": per_movie,
        "native_cuda_proven": bool(startup and all_stages),
    }


def run_binary(binary: Path, cwd: Path, star: Path, out_dir: Path,
               args: List[str], gpu: Optional[int],
               extra: Optional[List[str]] = None) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(binary), "--i", str(star), "--o", f"{out_dir}{os.sep}"]
    cmd += args + (extra or [])
    if gpu is not None:
        cmd += ["--gpu", str(gpu)]
    start = time.time()
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return {
        "command": cmd, "cwd": str(cwd), "returncode": proc.returncode,
        "elapsed_sec": round(time.time() - start, 3),
        "stdout": proc.stdout, "stderr": proc.stderr,
    }


def product_hashes(out_dir: Path, stems: List[str], suffixes: List[str]) -> Dict[str, str]:
    """Digest every declared product, keyed by its path relative to ``out_dir``."""
    digests = {}
    for stem in stems:
        for suffix in suffixes:
            relative = f"{stem}.star" if suffix == ".star" else f"{stem}{suffix}"
            path = out_dir / relative
            if path.exists():
                digests[relative] = sha256(path)
    return digests


def report_name(stem: str, schedule: str) -> str:
    """Flatten a movie stem that may contain directories into a report filename."""
    return f"{stem.replace('/', '__')}_{schedule}.json"


def compare_pair(compare_tool: Path, ref_dir: Path, test_dir: Path, stem: str,
                 report_path: Path, image_only: bool = False) -> Dict[str, Any]:
    """Per-product exact comparison, delegated verbatim to the merged comparator.

    ``image_only`` compares just the image, for auxiliary products such as
    ``_noDW``/``_EVN``/``_ODD``/``_PS`` that have no STAR of their own.
    """
    cmd = [sys.executable, str(compare_tool),
           "--ref-mrc", str(ref_dir / f"{stem}.mrc"),
           "--test-mrc", str(test_dir / f"{stem}.mrc")]
    if not image_only:
        cmd += ["--ref-star", str(ref_dir / f"{stem}.star"),
                "--test-star", str(test_dir / f"{stem}.star")]
    cmd += ["--gate", "exact", "--json-out", str(report_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    entry: Dict[str, Any] = {"command": cmd, "returncode": proc.returncode}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
        except json.JSONDecodeError as exc:
            entry["error"] = f"unreadable comparator report: {exc}"
            return entry
        entry["overall_status"] = report.get("overall_status")
        entry["checks"] = {name: check.get("passed")
                           for name, check in report.get("checks", {}).items()}
        entry["coverage_complete"] = report.get("coverage", {}).get("complete")
    else:
        entry["error"] = "comparator produced no report"
        entry["stderr_tail"] = proc.stderr[-2000:]
    # PASS requires the tool's own top-level verdict and a zero exit; neither
    # alone is accepted.
    entry["passed"] = bool(entry.get("overall_status") == "PASS" and proc.returncode == 0)
    return entry


# ----------------------------------------------------------------- schedules

def expected_star(row: declared.Row, geometry: Dict[str, Any]) -> Dict[str, Any]:
    args = row.args
    def value_of(flag: str, default: Any) -> Any:
        return args[args.index(flag) + 1] if flag in args else default

    bin_factor = float(value_of("--bin_factor", 1))
    first_frame = int(value_of("--first_frame_sum", 1))
    last_frame = int(value_of("--last_frame_sum", -1))
    total = int(geometry["frames"])
    last = total if last_frame <= 0 else min(last_frame, total)
    dose_on = "--dose_weighting" in args
    return {
        "original_pixel_size": geometry["angpix"],
        "binning": bin_factor,
        "first_frame": first_frame,
        "dose_per_frame": float(value_of("--dose_per_frame", 1)) if dose_on else None,
        "pre_exposure": float(value_of("--preexposure", 0)),
        # The trajectory spans the whole movie; frames outside the summed window
        # are written as NOT_OBSERVED rather than omitted.
        "n_trajectory_rows": total,
        "n_observed_frames": last - first_frame + 1,
    }


def expected_geometry(row: declared.Row, geometry: Dict[str, Any]) -> Optional[tuple]:
    args = row.args
    if "--bin_factor" not in args:
        return int(geometry["nx"]), int(geometry["ny"])
    factor = float(args[args.index("--bin_factor") + 1])
    if factor == 1:
        return int(geometry["nx"]), int(geometry["ny"])
    # Non-unit binning: the output size depends on the program's own rounding
    # rule, which this validation does not restate. Geometry is then recorded
    # from the run instead of asserted.
    return None


def run_row(row: declared.Row, opts: argparse.Namespace, fixtures_dir: Path,
            base_work: Path, compare_tool: Path) -> Dict[str, Any]:
    geometry = declared.FIXTURES[row.fixture]
    work = base_work / row.row_id
    work.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "row_id": row.row_id, "fixture": row.fixture, "axes": row.axes,
        "notes": row.notes, "backend": "cuda" if opts.gpu is not None else "cpu",
        "schedules": {}, "errors": [], "status": "unrun",
    }

    aux = build_aux_fixtures(work / "aux", int(geometry["nx"]), int(geometry["ny"]))
    args = [aux.get(token, token) for token in row.args]
    common = list(declared.COMMON_ARGS)
    if row.expect_reject == "j":
        common[common.index("8")] = "0"
    args = common + args

    dataset = build_dataset(work, row.fixture, fixtures_dir, row.n_movies, geometry)
    result["dataset"] = {"movies": dataset["stems"],
                         "movie_sha256": dataset["movie_sha256"]}

    # ------------------------------------------------ option-rejection rows
    if row.expect_reject:
        run = run_binary(opts.binary, work, dataset["star"], work / "reject",
                         args, opts.gpu)
        message = (run["stdout"] + run["stderr"]).lower()
        named = row.expect_reject.lower() in message
        result["schedules"]["reject"] = {
            "returncode": run["returncode"], "option_named": named,
            "message_tail": (run["stdout"] + run["stderr"])[-600:],
        }
        ok = run["returncode"] != 0 and named
        result["status"] = "pass" if ok else "fail"
        if not ok:
            result["errors"].append(
                f"expected nonzero exit naming '{row.expect_reject}', "
                f"got rc={run['returncode']} named={named}")
        return result

    suffixes = row.products
    star_expect = expected_star(row, geometry)
    geom_expect = expected_geometry(row, geometry)

    # ------------------------------------------------------ uninterrupted run
    base_dir = work / "base"
    base_run = run_binary(opts.binary, work, dataset["star"], base_dir, args, opts.gpu)
    witness = backend_witness(base_run["stdout"], base_dir, dataset["stems"], opts.gpu)
    inventory = prod.check_products(base_dir, dataset["stems"], suffixes,
                                    star_expect, geom_expect)
    result["schedules"]["base"] = {
        "returncode": base_run["returncode"], "elapsed_sec": base_run["elapsed_sec"],
        "command": base_run["command"], "backend_evidence": witness,
        "inventory": inventory,
        "stderr_tail": base_run["stderr"][-1500:],
    }
    (base_dir / "run-stdout.txt").write_text(base_run["stdout"])
    (base_dir / "run-stderr.txt").write_text(base_run["stderr"])

    if base_run["returncode"] != 0:
        result["errors"].append(f"base run exited {base_run['returncode']}")
        result["status"] = "fail"
        return result
    if opts.gpu is not None and not witness["native_cuda_proven"]:
        result["errors"].append("no native CUDA execution witness on the base run")
    if witness.get("unexpected_cuda_marker"):
        result["errors"].append("CPU run produced a CUDA marker")
    result["errors"].extend(inventory["errors"])

    # --------------------------------------------------------- other schedules
    for schedule in row.schedules:
        sched_dir = work / schedule
        entry: Dict[str, Any] = {"runs": []}

        if schedule == "repeat":
            run = run_binary(opts.binary, work, dataset["star"], sched_dir, args, opts.gpu)
            entry["runs"].append({"returncode": run["returncode"],
                                  "elapsed_sec": run["elapsed_sec"]})
            entry["backend_evidence"] = backend_witness(
                run["stdout"], sched_dir, dataset["stems"], opts.gpu)

        elif schedule == "batch":
            for _ in dataset["stems"]:
                run = run_binary(opts.binary, work, dataset["star"], sched_dir, args,
                                 opts.gpu, ["--do_at_most", "1", "--only_do_unfinished"])
                entry["runs"].append({"returncode": run["returncode"],
                                      "elapsed_sec": run["elapsed_sec"]})
                if run["returncode"] != 0:
                    break
            entry["backend_evidence"] = backend_witness(
                run["stdout"], sched_dir, dataset["stems"], opts.gpu)

        elif schedule == "resume":
            # Non-prefix completion: finish the middle movie first, then resume
            # the full dataset and require the already-good outputs to survive
            # byte-for-byte.
            first = run_binary(opts.binary, work, dataset["nonprefix_star"], sched_dir,
                               args, opts.gpu)
            entry["runs"].append({"stage": "nonprefix_seed",
                                  "returncode": first["returncode"],
                                  "elapsed_sec": first["elapsed_sec"]})
            # Byte identity is the right test here: it shows the completed
            # products were left untouched, not merely rewritten to the same
            # pixels. A rewrite would change the MRC label timestamp.
            seeded = product_hashes(sched_dir, [dataset["nonprefix_stem"]], suffixes)
            entry["seeded_movie"] = dataset["nonprefix_stem"]
            entry["seeded_hashes"] = seeded
            second = run_binary(opts.binary, work, dataset["star"], sched_dir, args,
                                opts.gpu, ["--only_do_unfinished"])
            entry["runs"].append({"stage": "resume", "returncode": second["returncode"],
                                  "elapsed_sec": second["elapsed_sec"]})
            after = product_hashes(sched_dir, [dataset["nonprefix_stem"]], suffixes)
            entry["preserved_seeded_outputs"] = (seeded == after and bool(seeded))
            if not entry["preserved_seeded_outputs"]:
                result["errors"].append(
                    f"{schedule}: previously completed movie "
                    f"{dataset['nonprefix_stem']} was not preserved across resume")
            entry["backend_evidence"] = backend_witness(
                second["stdout"], sched_dir, dataset["stems"], opts.gpu)
        else:
            result["errors"].append(f"unknown schedule {schedule}")
            continue

        bad_rc = [r for r in entry["runs"] if r["returncode"] != 0]
        if bad_rc:
            entry["passed"] = False
            result["errors"].append(f"{schedule}: nonzero exit {bad_rc}")
            result["schedules"][schedule] = entry
            continue

        entry["inventory"] = prod.check_products(sched_dir, dataset["stems"], suffixes,
                                                 star_expect, geom_expect)
        result["errors"].extend(f"{schedule}: {e}" for e in entry["inventory"]["errors"])

        reports = sched_dir / "compare"
        reports.mkdir(exist_ok=True)
        comparisons = {}
        for stem in dataset["stems"]:
            comparisons[stem] = compare_pair(compare_tool, base_dir, sched_dir, stem,
                                             reports / report_name(stem, "exact"))
        entry["comparisons"] = comparisons
        entry["movies_compared"] = len(comparisons)
        entry["movies_passed"] = sum(1 for c in comparisons.values() if c["passed"])

        # Auxiliary products must match too, so even/odd, noDW and PS images are
        # compared rather than assumed identical. They go through the same
        # comparator as the main image: a raw digest would flag the MRC label
        # timestamp, which the comparator normalizes away, as a difference.
        extra_suffixes = [s for s in suffixes if s not in (".mrc", ".star")]
        extra: Dict[str, Any] = {}
        for stem in dataset["stems"]:
            for suffix in extra_suffixes:
                name = f"{stem}{suffix}"
                extra_stem = name[:-len(".mrc")] if name.endswith(".mrc") else name
                if not (base_dir / name).exists():
                    continue
                if not (sched_dir / name).exists():
                    extra[name] = {"passed": False, "error": "missing in this schedule"}
                    continue
                extra[name] = compare_pair(compare_tool, base_dir, sched_dir,
                                           extra_stem,
                                           reports / report_name(extra_stem, "exact"),
                                           image_only=True)
        entry["extra_products"] = extra
        extra_failed = sorted(name for name, c in extra.items() if not c["passed"])
        if extra_failed:
            result["errors"].append(
                f"{schedule}: auxiliary products differ from base: "
                f"{', '.join(extra_failed)}")

        entry["passed"] = (
            entry["movies_compared"] == len(dataset["stems"])
            and entry["movies_passed"] == entry["movies_compared"]
            and entry["inventory"]["inventory_complete"]
            and not extra_failed
            and entry.get("preserved_seeded_outputs", True)
        )
        if not entry["passed"]:
            result["errors"].append(
                f"{schedule}: {entry['movies_passed']}/{entry['movies_compared']} "
                "movies exact")
        result["schedules"][schedule] = entry

    schedules_ok = all(result["schedules"][s].get("passed") for s in row.schedules) \
        if row.schedules else True
    native_ok = (opts.gpu is None) or witness["native_cuda_proven"]
    result["status"] = "pass" if (schedules_ok and native_ok
                                  and inventory["inventory_complete"]
                                  and not result["errors"]) else "fail"
    return result


# ---------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--fixtures-dir", type=Path, required=True,
                        help="Directory holding the generated known-motion .mrcs")
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--gpu", type=int, default=None,
                        help="CUDA device index; omit to run the CPU backend")
    parser.add_argument("--rows", default="all",
                        help="Comma-separated row ids, or 'all'")
    parser.add_argument("--include-heavy", action="store_true",
                        help="Include rows whose fixture is marked heavy")
    parser.add_argument("--compare-tool", type=Path,
                        default=REPO_ROOT / "tools" / "compare_motioncorr.py")
    parser.add_argument("--json", type=Path, help="Write the aggregate report here")
    opts = parser.parse_args()

    if opts.gpu is not None and opts.gpu < 0:
        parser.error("--gpu must be a nonnegative CUDA device index")
    if not opts.binary.exists():
        parser.error(f"binary not found: {opts.binary}")
    if not opts.compare_tool.exists():
        parser.error(f"comparator not found: {opts.compare_tool}")

    selected = declared.ROWS
    if opts.rows != "all":
        wanted = {r.strip() for r in opts.rows.split(",") if r.strip()}
        known = declared.rows_by_id()
        unknown = wanted - set(known)
        if unknown:
            parser.error(f"unknown row ids: {', '.join(sorted(unknown))}")
        selected = [known[r] for r in wanted]
    if not opts.include_heavy:
        selected = [r for r in selected if not declared.FIXTURES[r.fixture]["heavy"]]

    opts.outdir.mkdir(parents=True, exist_ok=True)
    work = opts.outdir / "work"

    provenance = {
        "binary": str(opts.binary.resolve()),
        "binary_sha256": sha256(opts.binary),
        "comparator": str(opts.compare_tool.resolve()),
        "comparator_sha256": sha256(opts.compare_tool),
        "matrix_sha256": sha256(Path(__file__).resolve().parent / "matrix.py"),
        "products_sha256": sha256(Path(__file__).resolve().parent / "products.py"),
        "runner_sha256": sha256(Path(__file__).resolve()),
        "gpu": opts.gpu,
        "hostname": os.uname().nodename,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    results = []
    for row in selected:
        print(f"[issue83] {row.row_id} ...", flush=True)
        try:
            entry = run_row(row, opts, opts.fixtures_dir.resolve(), work,
                            opts.compare_tool.resolve())
        except Exception as exc:  # a harness fault must not read as a pass
            entry = {"row_id": row.row_id, "status": "error", "errors": [repr(exc)]}
        results.append(entry)
        print(f"[issue83] {row.row_id}: {entry['status']}", flush=True)

    declared_ids = {r.row_id for r in declared.ROWS}
    attempted_ids = {r.row_id for r in selected}
    report = {
        "schema": "issue83-support-matrix/1",
        "provenance": provenance,
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "declared_rows": sorted(declared_ids),
        "unrun_rows": sorted(declared_ids - attempted_ids),
        "results": results,
        "counts": {
            "declared": len(declared_ids),
            "attempted": len(results),
            "pass": sum(1 for r in results if r["status"] == "pass"),
            "fail": sum(1 for r in results if r["status"] == "fail"),
            "error": sum(1 for r in results if r["status"] == "error"),
        },
    }
    # The aggregate is only "complete" when nothing declared was skipped.
    report["matrix_complete"] = not report["unrun_rows"] and report["counts"]["fail"] == 0 \
        and report["counts"]["error"] == 0

    if opts.json:
        opts.json.parent.mkdir(parents=True, exist_ok=True)
        opts.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["counts"], indent=2))
    if report["unrun_rows"]:
        print(f"UNRUN rows: {', '.join(report['unrun_rows'])}")
    return 0 if report["matrix_complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
