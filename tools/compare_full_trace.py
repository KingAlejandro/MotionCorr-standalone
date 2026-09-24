#!/usr/bin/env python3
"""Compare every exact CPU/CUDA chunk in an opt-in Issue #36 full trace.

Keep raw traces on the analysis host. This writes only small, per-stage metrics.
"""

import argparse
import hashlib
import json
import math
import pathlib
import struct
import subprocess
import sys


def tutorial_24x5_keys():
    """Exact key schema for the two 24-frame, 5x5, two-iteration runs."""
    keys = {"mapping_source_frame", "mapping_group_start", "mapping_group_size",
            "g_i00_weight", "model_i00_coeffx", "model_i00_coeffy",
            "model_i00_obsframe", "model_i00_obsposx", "model_i00_obsposy",
            "model_i00_obsx", "model_i00_obsy", "dw_i00_dose", "out_i00_sum"}
    for frame in range(24):
        tag = f"f{frame:03d}"
        for stage in ("raw", "gain", "defect", "fft"):
            keys.add(f"pre_i00_{stage}_{tag}")
        keys.add(f"g_i00_ifft_{tag}")
        for stage in ("weightedfft", "ifft"):
            keys.add(f"dw_i00_{stage}_{tag}")
        for stage in ("modelx", "modely", "interp", "cumsum"):
            keys.add(f"out_i00_{stage}_{tag}")
    for scope in ["g"] + [f"p{patch}" for patch in range(1, 26)]:
        if scope != "g":
            for stage in ("bounds", "finalx", "finaly"):
                keys.add(f"{scope}_i00_{stage}")
            for frame in range(24):
                keys.add(f"{scope}_i00_spatial_f{frame:03d}")
            keys.add(f"{scope}_i00_weight")
        for iteration in (1, 2):
            prefix = f"{scope}_i{iteration:02d}"
            for stage in ("fref", "peaks", "rawshiftx", "rawshifty",
                          "deltax", "deltay", "totalx", "totaly"):
                keys.add(f"{prefix}_{stage}")
            for frame in range(24):
                for stage in ("input", "fccs", "iccs", "postshift"):
                    keys.add(f"{prefix}_{stage}_f{frame:03d}")
    if len(keys) != 6385:
        raise AssertionError(f"Unexpected tutorial schema size: {len(keys)}")
    return keys


def replay_audit_keys():
    return {f"g_i{iteration:02d}_replay_{stage}"
            for iteration in (1, 2)
            for stage in ("measured_deltax", "measured_deltay",
                          "phase_shiftx", "phase_shifty")}


def check_replay_audit(directory, metadata):
    result = {}
    for key in sorted(replay_audit_keys()):
        expected = {"key": key, "dtype": "f4", "shape": [24],
                    "bytes": 96, "endian": "native"}
        if metadata[key] != expected:
            raise ValueError(f"Invalid replay audit sidecar: {key}")
        payload = (directory / f"{key}.bin").read_bytes()
        values = struct.unpack("=24f", payload)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Nonfinite replay audit array: {key}")
        result[key] = {"sha256": hashlib.sha256(payload).hexdigest(),
                       "max_abs": max(map(abs, values))}
    return result


def read_manifest(directory, expected_backend):
    if not (directory / "trace_complete").is_file():
        raise ValueError(f"Incomplete trace: {directory}")
    start = dict(line.split("=", 1) for line in (directory / "trace_start").read_text().splitlines())
    if start.get("backend") != expected_backend or start.get("format") != "motioncorr-full-trace-v1":
        raise ValueError(f"Wrong backend or format: {directory}")
    result = {}
    for path in directory.glob("*.json"):
        metadata = json.loads(path.read_text())
        key = metadata["key"]
        if key in result or path.stem != key:
            raise ValueError(f"Duplicate or mismatched key: {path}")
        binary = directory / f"{key}.bin"
        if not binary.is_file() or binary.stat().st_size != metadata["bytes"]:
            raise ValueError(f"Missing or wrong-size binary: {binary}")
        result[key] = metadata
    return result, start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cpu", type=pathlib.Path)
    parser.add_argument("cuda", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--comparator", type=pathlib.Path, required=True)
    parser.add_argument("--require-tutorial-24x5", action="store_true",
                        help="Fail unless both traces contain exactly 6385 expected checkpoints")
    parser.add_argument("--allow-cuda-replay-audit", action="store_true",
                        help="Require and validate the eight counterfactual-only CUDA audit arrays")
    arguments = parser.parse_args()
    cpu, cpu_start = read_manifest(arguments.cpu, "cpu")
    cuda, cuda_start = read_manifest(arguments.cuda, "cuda")
    if cpu_start.get("movie") != cuda_start.get("movie"):
        raise ValueError("CPU/CUDA traces refer to different movie paths")
    audit = {}
    if arguments.allow_cuda_replay_audit:
        if set(cuda) - set(cpu) != replay_audit_keys():
            raise ValueError("Missing or unexpected CUDA replay audit keys")
        audit = check_replay_audit(arguments.cuda, cuda)
        cuda = {key: value for key, value in cuda.items() if key not in replay_audit_keys()}
    cpu_only, cuda_only = sorted(cpu.keys() - cuda.keys()), sorted(cuda.keys() - cpu.keys())
    schema_errors = {}
    if arguments.require_tutorial_24x5:
        expected = tutorial_24x5_keys()
        for backend, found in (("cpu", set(cpu)), ("cuda", set(cuda))):
            schema_errors[backend] = {"missing": sorted(expected - found), "extra": sorted(found - expected)}
        if any(value["missing"] or value["extra"] for value in schema_errors.values()):
            print(json.dumps({"schema_errors": schema_errors}), file=sys.stderr)
    if cpu_only or cuda_only:
        print(json.dumps({"cpu_only": cpu_only, "cuda_only": cuda_only}), file=sys.stderr)
    if arguments.output.exists():
        raise ValueError(f"Refusing to overwrite: {arguments.output}")
    count = 0
    raw_input_differences = 0
    with arguments.output.open("x") as report:
        for key in sorted(cpu.keys() & cuda.keys()):
            if cpu[key]["shape"] != cuda[key]["shape"] or cpu[key]["endian"] != cuda[key]["endian"]:
                raise ValueError(f"Metadata differ at {key}: {cpu[key]} vs {cuda[key]}")
            command = [str(arguments.comparator), str(arguments.cpu / f"{key}.bin"),
                       str(arguments.cuda / f"{key}.bin"), cpu[key]["dtype"], cuda[key]["dtype"]]
            completed = subprocess.run(command, capture_output=True, text=True)
            if completed.returncode:
                raise RuntimeError(f"Comparison failed at {key}: {completed.stderr} exit={completed.returncode}")
            metrics = json.loads(completed.stdout)
            metrics["byte_different"] = metrics["cpu_sha256"] != metrics["cuda_sha256"]
            metrics.update({"key": key, "shape": cpu[key]["shape"]})
            report.write(json.dumps(metrics, separators=(",", ":")) + "\n")
            if key.startswith("pre_i00_raw_f") and metrics["byte_different"]:
                raw_input_differences += 1
            count += 1
            if count % 250 == 0:
                print(f"Compared {count}/{len(cpu)} chunks", flush=True)
    print(json.dumps({"paired_checkpoints": count, "cpu_only": len(cpu_only), "cuda_only": len(cuda_only),
                      "raw_input_differences": raw_input_differences,
                      "replay_audit": audit,
                      "tutorial_schema_checked": arguments.require_tutorial_24x5,
                      "tutorial_schema_pass": (not any(value["missing"] or value["extra"] for value in schema_errors.values())
                                               if arguments.require_tutorial_24x5 else None),
                      "report": str(arguments.output)}))
    if raw_input_differences:
        raise ValueError("CPU/CUDA raw input frames differ; paired run is invalid")
    if cpu_only or cuda_only:
        raise ValueError("Checkpoint key sets differ; common checkpoints were compared")
    if any(value["missing"] or value["extra"] for value in schema_errors.values()):
        raise ValueError("Required tutorial stage/frame/patch schema is incomplete")


if __name__ == "__main__":
    main()
