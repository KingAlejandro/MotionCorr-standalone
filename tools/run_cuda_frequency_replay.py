#!/usr/bin/env python3
"""Run the native dependency proof and optional separately compiled replay mutants.

No builds, source edits, remote launches or GPU allocation are performed here.
The caller supplies the allocated environment and any prebuilt mutant binaries.
An execution failure is never accepted as a successful mutation control.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


CASES = {
    "cropped_motion", "full_support", "nonsquare", "automatic_B",
    "automatic_B_changed", "same_geometry_changed_input", "early_convergence",
    "max_iter_exhaustion", "single_frame", "zero_tied_peaks", "weak_signal",
    "cropped_motion_repeat",
}
SOURCE_FILES = (
    "CMakeLists.txt", "src/acc/cuda/cuda_alignpatch.cu", "src/acc/cuda/cuda_alignpatch.h",
    "src/acc/cuda/cuda_alignpatch_frequency_support.h", "tests/cuda_frequency_replay.cpp",
    "tests/test_cuda_frequency_support.cpp", "tools/run_cuda_frequency_replay.py",
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(binary, args, name, output):
    binary = binary.resolve(strict=True)
    command = [str(binary), *args]
    record = {"binary": str(binary), "binary_sha256": sha256(binary), "command": command}
    started = time.monotonic()
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, timeout=180, check=False)
        record["returncode"] = completed.returncode
        log = completed.stdout
    except subprocess.TimeoutExpired as error:
        record["returncode"] = None
        record["timeout"] = True
        log = error.stdout or ""
        if isinstance(log, bytes):
            log = log.decode("utf-8", errors="replace")
    record["elapsed_seconds"] = time.monotonic() - started
    # This elapsed interval is operational evidence, not a benchmark result.
    log_path = output / (name + ".log")
    log_path.write_text(log)
    record["log"] = str(log_path)
    return record, log


def source_snapshot(root):
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True).stdout
    return {
        "root": str(root), "revision": git("rev-parse", "HEAD").decode().strip(),
        "dirty_diff_sha256": hashlib.sha256(git("diff", "--binary", "HEAD")).hexdigest(),
        "status_porcelain": git("status", "--porcelain").decode(),
        "files_sha256": {name: sha256(root / name) for name in SOURCE_FILES},
        "scope": "Run-time source snapshot; not an attestation that supplied binaries were built from it. Retain build/mutant commands separately.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--skip-replay-binary", type=Path)
    parser.add_argument("--corrupt-replay-binary", type=Path)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    # Refuse a reused directory so an old native trace cannot certify a failed run.
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema": 1, "kind": "correctness_dependency_experiment_not_benchmark",
        "host": platform.node(), "platform": platform.platform(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "runner_sha256": sha256(Path(__file__)), "native": None,
        "compiled_mutants": {}, "status": "FAIL",
    }
    try:
        manifest["source_snapshot"] = source_snapshot(args.source_root.resolve(strict=True))
        trace_path = output / "native-trace.json"
        record, log = run(args.binary, ["--json", str(trace_path)], "native", output)
        manifest["native"] = record
        if record["returncode"] != 0:
            raise RuntimeError("Native suite failed; absence of a GPU is not a skipped pass")
        trace = json.loads(trace_path.read_text())
        cases = trace.get("cases", [])
        if ({row.get("name") for row in cases} != CASES or len(cases) != len(CASES)
                or any(row.get("exact") is not True or row.get("shipped_entry_exact") is not True for row in cases)
                or trace.get("comparator_mutations_rejected") != 19
                or trace.get("backend") != "native_cuda" or not trace.get("device_uuid_hex")
                or not trace.get("runtime_version") or not trace.get("driver_version")):
            raise RuntimeError("Native trace lacks complete case, device or comparison evidence")
        manifest["native_trace_sha256"] = sha256(trace_path)
        manifest["device"] = {key: trace[key] for key in
                              ("device_uuid_hex", "pci_bus_id", "runtime_version", "driver_version")}
        record["status"] = "PASS"
        for name, binary in (("skip_replay", args.skip_replay_binary),
                             ("corrupt_replay", args.corrupt_replay_binary)):
            if binary is None:
                manifest["compiled_mutants"][name] = {"status": "UNRUN"}
                continue
            record, log = run(binary, ["--case", "cropped_motion"], name, output)
            manifest["compiled_mutants"][name] = record
            intended = "FAIL FREQUENCY_REPLAY_MISMATCH case=cropped_motion field=full Fourier payload"
            if record["returncode"] != 1 or intended not in log:
                record["status"] = "FAIL"
                raise RuntimeError(name + " did not fail the intended full-spectrum comparison")
            record["status"] = "REJECTED_AS_EXPECTED"
        manifest["acceptance_complete"] = all(
            row.get("status") == "REJECTED_AS_EXPECTED" for row in manifest["compiled_mutants"].values())
        manifest["status"] = "PASS" if manifest["acceptance_complete"] else "INCOMPLETE"
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        manifest["acceptance_complete"] = False
        manifest["error"] = str(error)
        print("FAIL:", error, file=sys.stderr)
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": manifest["status"], "manifest": str(output / "manifest.json"),
                      "compiled_mutants": {k: v["status"] for k, v in manifest["compiled_mutants"].items()}}))
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[manifest["status"]]


if __name__ == "__main__":
    sys.exit(main())
