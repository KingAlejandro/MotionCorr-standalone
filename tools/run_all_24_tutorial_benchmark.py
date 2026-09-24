#!/usr/bin/env python3
"""Run or evaluate the 24 tutorial movies in six sequential four-movie batches.

The run uses a fixed CPU build and --seed 1. RELION 5.1 output from the
unchanged tutorial inputs can be supplied as the comparator. Evaluation fails
closed if a batch, movie output, or comparator result is missing or incomplete.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path


OPTIONS = (
    "--use_own", "--dose_weighting", "--dose_per_frame", "1.277",
    "--patch_x", "5", "--patch_y", "5", "--bfactor", "150",
    "--gainref", "Movies/gain.mrc",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def movie_lines(star: Path) -> list[str]:
    return [line for line in star.read_text().splitlines(keepends=True)
            if line.lstrip().startswith("Movies/")]


def movie_name(line: str) -> str:
    return Path(line.split()[0]).stem


def checked_movies(tutorial: Path) -> list[str]:
    lines = movie_lines(tutorial / "movies.star")
    names = [movie_name(line) for line in lines]
    if len(names) != 24 or len(set(names)) != 24:
        raise ValueError(f"Expected 24 unique tutorial movies, found {len(names)}")
    return names


def command_for(binary: Path, run_root: Path, threads: int, index: int) -> list[str]:
    label = f"standalone_j{threads}_chunk_{index}"
    return [str(binary), "--i", f"movies_chunk_{index}.star", "--o",
            str(run_root / label), *OPTIONS, "--j", str(threads), "--seed", "1"]


def prepare_chunks(tutorial: Path, run_root: Path) -> None:
    star = tutorial / "movies.star"
    text = star.read_text()
    prefix = text.split("Movies/", 1)[0]
    lines = movie_lines(star)
    run_root.mkdir(parents=True, exist_ok=True)
    movies_link = run_root / "Movies"
    if movies_link.exists() or movies_link.is_symlink():
        if movies_link.resolve() != (tutorial / "Movies").resolve():
            raise ValueError(f"Unexpected Movies link: {movies_link}")
    else:
        movies_link.symlink_to((tutorial / "Movies").resolve(), target_is_directory=True)
    for index in range(6):
        target = run_root / f"movies_chunk_{index}.star"
        content = prefix + "".join(lines[index * 4:(index + 1) * 4])
        if target.exists() and target.read_text() != content:
            raise ValueError(f"Existing chunk STAR differs from tutorial input: {target}")
        target.write_text(content)


def execute(tutorial: Path, run_root: Path, binary: Path) -> None:
    prepare_chunks(tutorial, run_root)
    for threads in (1, 4):
        for index in range(6):
            label = f"standalone_j{threads}_chunk_{index}"
            output = run_root / label
            log = run_root / f"{label}.log"
            if output.exists() or log.exists():
                raise FileExistsError(f"Refusing to overwrite existing run: {label}")
            cmd = ["/usr/bin/time", "-v", *command_for(binary, run_root, threads, index)]
            print(f"Running {label}", flush=True)
            with log.open("w") as stream:
                subprocess.run(cmd, cwd=run_root, stdout=stream,
                               stderr=subprocess.STDOUT, check=True)


def execute_repeats(tutorial: Path, run_root: Path, binary: Path, count: int) -> None:
    """Time one representative movie without overlapping the two thread settings."""
    if count < 1:
        return
    prepare_chunks(tutorial, run_root)
    first = movie_lines(tutorial / "movies.star")[0]
    one_star = run_root / "movies_timing_one.star"
    content = (tutorial / "movies.star").read_text().split("Movies/", 1)[0] + first
    if one_star.exists() and one_star.read_text() != content:
        raise ValueError(f"Existing timing STAR differs from tutorial input: {one_star}")
    one_star.write_text(content)
    for repeat in range(count):
        order = (1, 4) if repeat % 2 == 0 else (4, 1)
        for threads in order:
            label = f"timing_j{threads}_rep{repeat + 1}"
            output, log = run_root / label, run_root / f"{label}.log"
            if output.exists() or log.exists():
                raise FileExistsError(f"Refusing to overwrite existing timing run: {label}")
            cmd = ["/usr/bin/time", "-v", str(binary), "--i", one_star.name,
                   "--o", str(output), *OPTIONS, "--j", str(threads), "--seed", "1"]
            print(f"Running {label}", flush=True)
            with log.open("w") as stream:
                subprocess.run(cmd, cwd=run_root, stdout=stream,
                               stderr=subprocess.STDOUT, check=True)


def time_metrics(log: Path) -> dict:
    if not log.is_file():
        raise FileNotFoundError(log)
    text = log.read_text(errors="replace")
    patterns = {
        "elapsed": r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*([^\n\r]+)",
        "user_seconds": r"User time \(seconds\):\s*([\d.]+)",
        "system_seconds": r"System time \(seconds\):\s*([\d.]+)",
        "max_rss_kb": r"Maximum resident set size \(kbytes\):\s*(\d+)",
        "exit_status": r"Exit status:\s*(\d+)",
    }
    values = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if not match:
            raise ValueError(f"Missing {key} in {log}")
        values[key] = match.group(1).strip()
    values["exit_status"] = int(values["exit_status"])
    if values["exit_status"] != 0 or "Command terminated by signal" in text:
        raise ValueError(f"Failed process recorded in {log}")
    parts = [float(part) for part in values["elapsed"].split(":")]
    values["elapsed_seconds"] = sum(part * 60 ** index
                                    for index, part in enumerate(reversed(parts)))
    for key in ("user_seconds", "system_seconds"):
        values[key] = float(values[key])
    values["max_rss_kb"] = int(values["max_rss_kb"])
    actual_command = re.search(r'Command being timed:\s*"([^"\n]+)"', text)
    if not actual_command:
        raise ValueError(f"Missing timed command in {log}")
    values["command"] = actual_command.group(1)
    return values


def validate_command(actual: str, binary: Path, input_star: str,
                     output: Path, threads: int, *, seed: bool, cwd: Path) -> None:
    tokens = shlex.split(actual)
    if not tokens or Path(tokens[0]).resolve() != binary:
        raise ValueError(f"Benchmark log names a different binary: {actual}")
    required = {
        "--i": input_star, "--j": str(threads),
        "--dose_per_frame": "1.277", "--patch_x": "5", "--patch_y": "5",
        "--bfactor": "150", "--gainref": "Movies/gain.mrc",
    }
    if seed:
        required["--seed"] = "1"
    for flag in ("--use_own", "--dose_weighting"):
        if flag not in tokens:
            raise ValueError(f"Benchmark log lacks {flag}: {actual}")
    for flag, value in required.items():
        if flag not in tokens or tokens.index(flag) + 1 >= len(tokens) or tokens[tokens.index(flag) + 1] != value:
            raise ValueError(f"Benchmark log has unexpected {flag}: {actual}")
    if "--o" not in tokens or tokens.index("--o") + 1 >= len(tokens):
        raise ValueError(f"Benchmark log lacks --o: {actual}")
    actual_output = Path(tokens[tokens.index("--o") + 1])
    if (cwd / actual_output).resolve() != output.resolve():
        raise ValueError(f"Benchmark log names a different output: {actual}")


def output_pair(directory: Path, name: str) -> tuple[Path, Path]:
    movies = directory / "Movies"
    pair = (movies / f"{name}.mrc", movies / f"{name}.star")
    for path in pair:
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Missing or empty output: {path}")
    return pair


def compare(tool: Path, reference: tuple[Path, Path], test: tuple[Path, Path],
            gate: str, json_path: Path) -> dict:
    cmd = [sys.executable, str(tool), "--ref-mrc", str(reference[0]),
           "--test-mrc", str(test[0]), "--ref-star", str(reference[1]),
           "--test-star", str(test[1]), "--gate", gate,
           "--json-out", str(json_path)]
    json_path.unlink(missing_ok=True)
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode not in (0, 1) or not json_path.is_file():
        raise RuntimeError(f"Comparator did not produce a valid result: {shlex.join(cmd)}\n"
                           f"{completed.stderr[-1000:]}")
    data = json.loads(json_path.read_text())
    status = data.get("overall_status")
    expected_returncode = 0 if status == "PASS" else 1
    if status not in ("PASS", "FAIL") or completed.returncode != expected_returncode:
        raise ValueError(f"Comparator exit and status disagree: {json_path}")
    if data.get("coverage", {}).get("complete") is not True:
        raise ValueError(f"Comparator coverage incomplete: {json_path}")
    checks = data.get("checks", {})
    for section in ("motion_trajectory", "corrected_image", "star_fields"):
        if section not in checks or checks[section].get("passed") is None:
            raise ValueError(f"Missing {section} check: {json_path}")
    if (status == "PASS") != all(checks[section]["passed"] for section in
                                  ("motion_trajectory", "corrected_image", "star_fields")):
        raise ValueError(f"Comparator status disagrees with its subchecks: {json_path}")
    trajectory = checks["motion_trajectory"]
    image = checks["corrected_image"]
    stars = checks["star_fields"]
    return {
        "status": status,
        "gate": gate,
        "trajectory_rms_px": trajectory["coord_rms_error"],
        "max_shift_px": trajectory["max_shift_error"],
        "image_rmse": image["rmse"],
        "relative_image_rmse": image["relative_rmse"],
        "max_pixel_error": image["max_abs_pixel_error"],
        "pixel_identical": image["pixel_identical"],
        "star_differences": stars["num_differences"],
        "trajectory_pass": trajectory["passed"],
        "image_pass": image["passed"],
        "star_pass": stars["passed"],
        "fail_reasons": (trajectory.get("fail_reasons", []) +
                         image.get("fail_reasons", []) +
                         stars.get("fail_reasons", [])),
        "command": shlex.join(cmd),
    }


def aggregate_star_rows(paths: list[Path]) -> dict[str, dict]:
    rows = {}
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        labels = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line == "loop_":
                labels = []
            elif line.startswith("_"):
                labels.append(line.split()[0])
            elif labels and line and not line.startswith("#"):
                cells = line.split()
                if len(cells) != len(labels):
                    continue
                entry = dict(zip(labels, cells))
                name = entry.get("_rlnMicrographName")
                if name:
                    stem = Path(name).stem
                    if stem in rows:
                        raise ValueError(f"Duplicate joint STAR row: {stem}")
                    rows[stem] = entry
    return rows


def joint_star_differences(ref: dict, test: dict, names: list[str]) -> list[str]:
    diffs = []
    fields = ("_rlnAccumMotionTotal", "_rlnAccumMotionEarly", "_rlnAccumMotionLate")
    for name in names:
        if name not in ref or name not in test:
            diffs.append(f"{name}: missing joint STAR row")
            continue
        for field in fields:
            try:
                a, b = float(ref[name][field]), float(test[name][field])
            except (KeyError, ValueError):
                diffs.append(f"{name}: missing or invalid {field}")
                continue
            if abs(a - b) > 1e-4:
                diffs.append(f"{name}: {field} {a} vs {b}")
    return diffs


def checksum_manifest(tutorial: Path, names: list[str]) -> dict:
    expected = {}
    checksum_file = tutorial / "Movies" / "SHA256SUMS.txt"
    if checksum_file.is_file():
        for line in checksum_file.read_text().splitlines():
            fields = line.split()
            if len(fields) == 2:
                expected[Path(fields[1].lstrip("* ")).name] = fields[0]
    paths = [tutorial / "movies.star", tutorial / "Movies" / "gain.mrc"]
    paths += [tutorial / "Movies" / f"{name}.tiff" for name in names]
    checksums = {}
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256(path)
        expected_hash = expected.get(path.name)
        if expected_hash and actual.lower() != expected_hash.lower():
            raise ValueError(f"Input checksum mismatch: {path}")
        checksums[path.name] = {"actual_sha256": actual,
                                "expected_sha256": expected_hash,
                                "matches_expected": expected_hash is None or actual.lower() == expected_hash.lower()}
    return checksums


def git_sha(path: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path,
                                   text=True).strip()


def assert_tracked_clean(path: Path) -> None:
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=path, text=True)
    if dirty.strip():
        raise ValueError(f"Tracked source changes prevent an unambiguous benchmark commit: {path}")


def cmake_build_type(binary: Path) -> str:
    cache = binary.parent / "CMakeCache.txt"
    if not cache.is_file():
        return "unknown"
    for line in cache.read_text(errors="replace").splitlines():
        if line.startswith("CMAKE_BUILD_TYPE:STRING="):
            return line.split("=", 1)[1]
    return "unknown"


def build_report(manifest: dict) -> str:
    movies = manifest["movies"]
    metrics = manifest["process_metrics"]
    j1 = metrics["standalone_j1"]["sum_elapsed_seconds"]
    j4 = metrics["standalone_j4"]["sum_elapsed_seconds"]
    exact = sum(m["j1_vs_relion_j1_exact"]["status"] == "PASS" for m in movies)
    upstream_relaxed = sum(m["j1_vs_relion_j1_relaxed"]["status"] == "PASS" for m in movies)
    j4_exact = sum(m["j4_vs_j1_exact"]["status"] == "PASS" for m in movies)
    j4_relaxed = sum(m["j4_vs_j1_relaxed"]["status"] == "PASS" for m in movies)
    j4_upstream = sum(m["j4_vs_relion_j4_relaxed"]["status"] == "PASS" for m in movies)
    prior_cpu = sum(m.get("j1_vs_pr25_cpu_exact", {}).get("status") == "PASS" for m in movies)
    lines = [
        "# RELION SPA tutorial: fixed-code 24-movie CPU validation", "",
        f"Run date: {manifest['metadata']['created_at']}",
        f"Host: `{manifest['metadata']['hostname']}`",
        f"Standalone source: `{manifest['metadata']['standalone_commit']}`",
        f"RELION 5.1 source: `{manifest['metadata']['relion_commit']}`", "",
        "## Results", "",
        f"- Standalone `j=1` versus RELION `j=1`, **exact gate: {exact}/24 pass**; **relaxed Gate 2: {upstream_relaxed}/24 pass**.",
        f"- Standalone `j=4` versus standalone `j=1`, **exact gate: {j4_exact}/24 pass**; **relaxed Gate 2: {j4_relaxed}/24 pass**.",
        f"- Standalone `j=4` versus saved RELION `j=4`, relaxed Gate 2: {j4_upstream}/24 pass (contextual comparison).",
        *([f"- Standalone `j=1` versus the fixed-seed CPU reference used for PR #25: **{prior_cpu}/24 exact pass**."]
          if manifest["metadata"].get("prior_cpu_source_commit") else []),
        f"- Six sequential four-movie batches: `j=1` {j1:.2f} s; `j=4` {j4:.2f} s; ratio **{j1 / j4:.2f}x**. These totals include six process startups per setting and do not measure one uninterrupted 24-movie job. The `j=1` batches ran first, so cache order may affect this ratio; the alternating-order repeats below provide a separate timing check.",
        f"- Joint STAR differences, standalone `j=1` versus RELION `j=1`: {len(manifest['joint_star']['j1_vs_relion_j1'])}.",
        f"- Joint STAR differences, standalone `j=4` versus standalone `j=1`: {len(manifest['joint_star']['j4_vs_j1'])}.",
        "", "The pre-fix four-thread image differences and the earlier 3.46x timing claim are superseded by this rerun. The fix in PR #24 serializes defect replacement and resets the random seed per movie. Numerical gates remain unchanged.",
        "The historical PR #23 run recorded 24/24 exact single-thread matches before PR #24. That result describes the older binary; the fixed-code result above is the current result.",
        "", "## Reproduction and provenance", "",
        "Each setting ran six four-movie jobs **sequentially** on 4-gpu-vm with `--seed 1`, gain correction, dose weighting, 5 × 5 patches, and B factor 150. The prior RELION 5.1 outputs were reused after verifying the input SHA256 values and complete upstream artifacts. See [the manifest](spa_24_movies_manifest.json) for actual input hashes, binary hashes, exact commands, per-movie metrics, and exit status. New process logs are in [benchmark_logs](benchmark_logs/).", "",
        "The four-thread comparison with the saved RELION four-thread output is contextual: that upstream output predates the determinism fix and is not the CPU reproducibility gate.",
    ]
    repeats = manifest.get("timing_repeats", {})
    if repeats:
        lines += ["", "## Isolated repeat timing", "",
                  f"Representative movie: `{repeats['movie']}`. Runs alternated thread order, with no overlapping MotionCorr jobs.", "",
                  "| Threads | Wall seconds by repeat | Median wall seconds |",
                  "| ---: | --- | ---: |"]
        for threads in (1, 4):
            group = repeats[f"j{threads}"]
            times = [item["elapsed_seconds"] for item in group]
            lines.append(f"| {threads} | {', '.join(f'{value:.2f}' for value in times)} | {statistics.median(times):.2f} |")
        j1_median = statistics.median(item["elapsed_seconds"] for item in repeats["j1"])
        j4_median = statistics.median(item["elapsed_seconds"] for item in repeats["j4"])
        lines += ["", f"Median single-movie speed ratio: **{j1_median / j4_median:.2f}x**. This is a representative-movie measurement; the six-batch total above is the dataset measurement."]
        repeat_checks = manifest.get("timing_repeat_checks", [])
        if repeat_checks:
            passed = sum(item["status"] == "PASS" for item in repeat_checks)
            lines.append(f"Exact repeat-output comparisons: **{passed}/{len(repeat_checks)} pass**.")
    if exact != len(movies):
        first_failure = next(m for m in movies if m["j1_vs_relion_j1_exact"]["status"] == "FAIL")
        lines += ["", f"**Exact upstream parity remains unresolved.** `{first_failure['movie']}` is a reproducible case for [Issue #20](https://github.com/KingAlejandro/MotionCorr-standalone/issues/20), which tracks defect-correction RNG changes. The per-movie seed reset is a candidate cause; the metrics below establish the difference without assigning a cause."]
    lines += ["", "## Per-movie comparison", "",
        "### Standalone `j=1` versus RELION 5.1 `j=1`", "",
        "| Movie | Exact gate | Relaxed Gate 2 | vs PR #25 CPU | Shift RMS (px) | Max shift (px) | Image RMSE | Relative RMSE | Max pixel error | Exact STAR differences |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in movies:
        result = item["j1_vs_relion_j1_exact"]
        lines.append(
            f"| `{item['movie']}` | {result['status']} | {item['j1_vs_relion_j1_relaxed']['status']} | {item.get('j1_vs_pr25_cpu_exact', {}).get('status', '—')} | {result['trajectory_rms_px']:.6f} | "
            f"{result['max_shift_px']:.6f} | {result['image_rmse']:.6g} | "
            f"{result['relative_image_rmse']:.6g} | {result['max_pixel_error']:.6g} | "
            f"{result['star_differences']} |"
        )
    lines += ["", "### Standalone `j=4` versus standalone `j=1`", "",
              "| Movie | Exact gate | Relaxed Gate 2 | Shift RMS (px) | Max shift (px) | Image RMSE | Relative RMSE | Max pixel error | STAR differences |",
              "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for item in movies:
        result = item["j4_vs_j1_relaxed"]
        lines.append(
            f"| `{item['movie']}` | {item['j4_vs_j1_exact']['status']} | {result['status']} | "
            f"{result['trajectory_rms_px']:.6f} | {result['max_shift_px']:.6f} | "
            f"{result['image_rmse']:.6g} | {result['relative_image_rmse']:.6g} | "
            f"{result['max_pixel_error']:.6g} | {result['star_differences']} |"
        )
    lines += ["", "## Gate interpretation", "",
              "Every table status comes from the comparator's overall status with complete trajectory, image, and STAR coverage. A trajectory pass alone is not a full Gate 2 pass. The exact STAR-difference column includes derived motion fields; the relaxed comparator intentionally excludes those fields. Per-movie failure reasons and exact comparator commands are recorded in the manifest.", "",
              "The fixed-seed standalone `j=1` output is the CPU reference for CUDA comparisons. RELION 5.1 is the separate upstream reference for extraction parity. Matching the current CPU reference does not establish matching RELION.", ""]
    return "\n".join(lines)


def evaluate(args: argparse.Namespace) -> dict:
    if args.repeat_count < 0:
        raise ValueError("--repeat-count must be nonnegative")
    assert_tracked_clean(args.source_repo.resolve())
    assert_tracked_clean(args.relion_repo.resolve())
    if args.prior_cpu_repo:
        assert_tracked_clean(args.prior_cpu_repo.resolve())
    tutorial = args.tutorial.resolve()
    run_root = args.run_root.resolve()
    artifact_dir = args.artifact_dir.resolve()
    binary = args.standalone_bin.resolve()
    relion_bin = args.relion_bin.resolve()
    for path in (binary, relion_bin):
        if not path.is_file():
            raise FileNotFoundError(path)
    names = checked_movies(tutorial)
    if args.execute:
        execute(tutorial, run_root, binary)
        execute_repeats(tutorial, run_root, binary, args.repeat_count)
    if not run_root.is_dir():
        raise FileNotFoundError(run_root)
    for index in range(6):
        actual = [movie_name(line) for line in movie_lines(run_root / f"movies_chunk_{index}.star")]
        if actual != names[index * 4:(index + 1) * 4]:
            raise ValueError(f"Chunk {index} does not match tutorial movie order")
    chunk_hashes = {f"movies_chunk_{index}.star": sha256(run_root / f"movies_chunk_{index}.star")
                    for index in range(6)}
    if (run_root / "Movies").resolve() != (tutorial / "Movies").resolve():
        raise ValueError("Run input Movies link differs from tutorial dataset")

    inputs = checksum_manifest(tutorial, names)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    copied_logs = artifact_dir / "benchmark_logs"
    copied_logs.mkdir(exist_ok=True)
    process_metrics = {}
    commands = {}
    for threads in (1, 4):
        label = f"standalone_j{threads}"
        chunks = []
        for index in range(6):
            chunk = f"{label}_chunk_{index}"
            log = run_root / f"{chunk}.log"
            metrics = time_metrics(log)
            validate_command(metrics["command"], binary, f"movies_chunk_{index}.star",
                             run_root / chunk, threads, seed=True, cwd=run_root)
            chunks.append(metrics)
            commands[chunk] = metrics["command"]
            shutil.copy2(log, copied_logs / log.name)
        process_metrics[label] = {
            "chunks": chunks,
            "sum_elapsed_seconds": sum(item["elapsed_seconds"] for item in chunks),
            "sum_user_seconds": sum(item["user_seconds"] for item in chunks),
            "sum_system_seconds": sum(item["system_seconds"] for item in chunks),
        }

    repeat_timings = {}
    if args.repeat_count:
        first_name = names[0]
        repeat_timings["movie"] = first_name
        for threads in (1, 4):
            repeat_timings[f"j{threads}"] = []
            for repeat in range(1, args.repeat_count + 1):
                label = f"timing_j{threads}_rep{repeat}"
                log = run_root / f"{label}.log"
                metrics = time_metrics(log)
                validate_command(metrics["command"], binary, "movies_timing_one.star",
                                 run_root / label, threads, seed=True, cwd=run_root)
                repeat_timings[f"j{threads}"].append(metrics)
                output_pair(run_root / label, first_name)
                shutil.copy2(log, copied_logs / log.name)
                commands[label] = metrics["command"]

    reference_j1 = args.relion_j1_dir.resolve()
    reference_j4 = args.relion_j4_dir.resolve()
    prior_cpu_root = args.prior_cpu_root.resolve() if args.prior_cpu_root else None
    reference_logs = {
        "relion_j1": args.relion_j1_log.resolve(),
        "relion_j4": args.relion_j4_log.resolve(),
    }
    reference_metrics = {}
    for key, log in reference_logs.items():
        reference_metrics[key] = time_metrics(log)
        threads = 1 if key == "relion_j1" else 4
        output = reference_j1 if threads == 1 else reference_j4
        validate_command(reference_metrics[key]["command"], relion_bin, "movies.star",
                         output, threads, seed=False, cwd=tutorial)
        shutil.copy2(log, copied_logs / log.name)
    tool = args.compare_tool.resolve()
    if not tool.is_file():
        raise FileNotFoundError(tool)
    movies = []
    reference_hashes = {}
    repeat_checks = []
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        if args.repeat_count:
            first_name = names[0]
            for threads in (1, 4):
                baseline = output_pair(run_root / f"timing_j{threads}_rep1", first_name)
                for repeat in range(2, args.repeat_count + 1):
                    test = output_pair(run_root / f"timing_j{threads}_rep{repeat}", first_name)
                    check = compare(tool, baseline, test, "exact",
                                    scratch / f"timing_j{threads}_rep{repeat}.json")
                    repeat_checks.append({"reference": f"j{threads}_rep1",
                                          "test": f"j{threads}_rep{repeat}", **check})
            if args.repeat_count >= 1:
                baseline = output_pair(run_root / "timing_j1_rep1", first_name)
                test = output_pair(run_root / "timing_j4_rep1", first_name)
                check = compare(tool, baseline, test, "exact", scratch / "timing_j1_vs_j4.json")
                repeat_checks.append({"reference": "j1_rep1", "test": "j4_rep1", **check})
        for index, name in enumerate(names):
            chunk = index // 4
            j1 = output_pair(run_root / f"standalone_j1_chunk_{chunk}", name)
            j4 = output_pair(run_root / f"standalone_j4_chunk_{chunk}", name)
            r1 = output_pair(reference_j1, name)
            r4 = output_pair(reference_j4, name)
            reference_hashes[name] = {
                "relion_j1_mrc": sha256(r1[0]),
                "relion_j1_star": sha256(r1[1]),
                "relion_j4_mrc": sha256(r4[0]),
                "relion_j4_star": sha256(r4[1]),
            }
            movie = {"movie": name, "chunk": chunk}
            for key, ref, test, gate in (
                ("j1_vs_relion_j1_exact", r1, j1, "exact"),
                ("j1_vs_relion_j1_relaxed", r1, j1, "relaxed"),
                ("j4_vs_j1_exact", j1, j4, "exact"),
                ("j4_vs_j1_relaxed", j1, j4, "relaxed"),
                ("j4_vs_relion_j4_relaxed", r4, j4, "relaxed"),
            ):
                movie[key] = compare(tool, ref, test, gate, scratch / f"{name}_{key}.json")
            if prior_cpu_root:
                prior_cpu = output_pair(prior_cpu_root / f"cpu_chunk_{chunk}", name)
                movie["j1_vs_pr25_cpu_exact"] = compare(
                    tool, prior_cpu, j1, "exact", scratch / f"{name}_j1_vs_pr25_cpu.json")
            movies.append(movie)
            print(f"{index + 1:02d}/24 {name}: exact={movie['j1_vs_relion_j1_exact']['status']} "
                  f"j4_exact={movie['j4_vs_j1_exact']['status']} "
                  f"j4_relaxed={movie['j4_vs_j1_relaxed']['status']}", flush=True)

    joint_ref = aggregate_star_rows([reference_j1 / "corrected_micrographs.star"])
    joint_j1 = aggregate_star_rows([run_root / f"standalone_j1_chunk_{index}" /
                                    "corrected_micrographs.star" for index in range(6)])
    joint_j4 = aggregate_star_rows([run_root / f"standalone_j4_chunk_{index}" /
                                    "corrected_micrographs.star" for index in range(6)])
    manifest = {
        "metadata": {
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "hostname": platform.node(),
            "platform": platform.platform(),
            "compiler": subprocess.check_output(["c++", "--version"], text=True).splitlines()[0],
            "cpu_count": os.cpu_count(),
            "python_version": sys.version.split()[0],
            "evaluation_command": shlex.join([sys.executable, *sys.argv]),
            "standalone_commit": git_sha(args.source_repo.resolve()),
            "relion_commit": git_sha(args.relion_repo.resolve()),
            "standalone_binary_sha256": sha256(binary),
            "standalone_build_type": cmake_build_type(binary),
            "relion_binary_sha256": sha256(relion_bin),
            "input_tutorial_dir": str(tutorial),
            "run_root": str(run_root),
            "relion_j1_dir": str(reference_j1),
            "relion_j4_dir": str(reference_j4),
            "prior_cpu_source_commit": git_sha(args.prior_cpu_repo.resolve()) if args.prior_cpu_repo else None,
            "prior_cpu_binary_sha256": (
                sha256(args.prior_cpu_repo.resolve() / "build-cpu" / "motioncorr")
                if args.prior_cpu_repo else None),
            "prior_cpu_root": str(prior_cpu_root) if prior_cpu_root else None,
            "comparison_tool_sha256": sha256(tool),
            "runner_sha256": sha256(Path(__file__)),
            "batching": "six sequential jobs of four movies per thread setting",
            "seed": 1,
        },
        "input_checksums": inputs,
        "chunk_star_sha256": chunk_hashes,
        "commands": commands,
        "process_metrics": process_metrics,
        "timing_repeats": repeat_timings,
        "timing_repeat_checks": repeat_checks,
        "reused_relion_process_metrics": reference_metrics,
        "reused_relion_output_sha256": reference_hashes,
        "joint_star": {
            "j1_vs_relion_j1": joint_star_differences(joint_ref, joint_j1, names),
            "j4_vs_j1": joint_star_differences(joint_j1, joint_j4, names),
        },
        "movies": movies,
    }
    (artifact_dir / "spa_24_movies_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (artifact_dir / "spa_24_movies_validation.md").write_text(build_report(manifest))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tutorial", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--standalone-bin", type=Path, required=True)
    parser.add_argument("--relion-bin", type=Path, required=True)
    parser.add_argument("--relion-j1-dir", type=Path, required=True)
    parser.add_argument("--relion-j4-dir", type=Path, required=True)
    parser.add_argument("--relion-j1-log", type=Path, required=True)
    parser.add_argument("--relion-j4-log", type=Path, required=True)
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--relion-repo", type=Path, required=True)
    parser.add_argument("--compare-tool", type=Path, required=True)
    parser.add_argument("--prior-cpu-root", type=Path,
                        help="Optional fixed-seed CPU outputs from the PR #25 validation")
    parser.add_argument("--prior-cpu-repo", type=Path,
                        help="Source checkout for --prior-cpu-root provenance")
    parser.add_argument("--execute", action="store_true", help="Run new CPU batches; refuse existing outputs")
    parser.add_argument("--repeat-count", type=int, default=0,
                        help="Require and report this many isolated timing repeats per thread setting")
    args = parser.parse_args()
    if bool(args.prior_cpu_root) != bool(args.prior_cpu_repo):
        parser.error("--prior-cpu-root and --prior-cpu-repo must be supplied together")
    try:
        result = evaluate(args)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Benchmark incomplete: {error}", file=sys.stderr)
        return 2
    primary_ok = all(movie["j1_vs_relion_j1_exact"]["status"] == "PASS" and
                     movie["j4_vs_j1_relaxed"]["status"] == "PASS" and
                     movie.get("j1_vs_pr25_cpu_exact", {"status": "PASS"})["status"] == "PASS"
                     for movie in result["movies"]) and all(
                         check["status"] == "PASS" for check in result["timing_repeat_checks"])
    return 0 if primary_ok else 1


if __name__ == "__main__":
    sys.exit(main())
