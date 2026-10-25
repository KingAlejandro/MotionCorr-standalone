#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run deliberate fail-closed input controls on the admitted CPU64 Linux host only.

Every case runs once against an isolated temporary copy. The manifest pin is
updated for byte-mutated fixtures so the consumer reaches the intended structural
check instead of failing at the ordinary byte-integrity check.
"""
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def require_cpu64_admission():
    if not sys.platform.startswith("linux"):
        raise SystemExit("REFUSED: structural controls require the CPU64 Linux host")
    if os.environ.get("MOTIONCORR_W4_CPU64_ADMISSION") != "cpu64":
        raise SystemExit("REFUSED: set MOTIONCORR_W4_CPU64_ADMISSION=cpu64 only in the admitted CPU64 lane")


def load_manifest(case):
    path = case / "input-manifest.json"
    return path, json.loads(path.read_text())


def write_manifest(path, manifest):
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def repin(manifest, rel, data):
    target = next((x for x in manifest["files"] if x["path"] == rel), None)
    if target is None:
        raise AssertionError("fixture is not pinned: " + rel)
    target["bytes"] = len(data)
    target["sha256"] = hashlib.sha256(data).hexdigest()


def fresh_case(parent, name):
    case = parent / name
    case.mkdir()
    shutil.copy2(ROOT / "consume_w4_cpu_observations.py", case)
    shutil.copy2(ROOT / "input-manifest.json", case)
    shutil.copytree(ROOT / "inputs", case / "inputs")
    return case


def mutate_missing_selector(case):
    path, m = load_manifest(case)
    del m["selectors"]["3,3"]
    write_manifest(path, m)


def mutate_duplicate_json_selector(case):
    path, m = load_manifest(case)
    raw = path.read_text()
    marker = '    "1,1": {'
    if raw.count(marker) != 1:
        raise AssertionError("could not locate selector 1,1 for duplicate-key fixture")
    duplicate = '    "1,1": ' + json.dumps(m["selectors"]["1,1"], separators=(",", ":")) + ",\n"
    path.write_text(raw.replace(marker, duplicate + marker, 1))


def mutate_missing_star_frame(case):
    path, m = load_manifest(case)
    rel = "inputs/runtime/out/affine.star"
    star = case / rel
    lines = star.read_text().splitlines(keepends=True)
    in_local = False
    removed = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("data_"):
            in_local = stripped == "data_local_shift"
        if in_local and stripped and stripped[0].isdigit():
            fields = stripped.split()
            if len(fields) >= 5 and fields[:3] == ["1", "20.000000", "15.000000"]:
                del lines[i]
                removed = True
                break
    if not removed:
        raise AssertionError("could not remove one pinned STAR centre/frame row")
    data = "".join(lines).encode()
    star.write_bytes(data)
    repin(m, rel, data)
    write_manifest(path, m)


def mutate_final_iteration(case):
    path, m = load_manifest(case)
    rec = m["selectors"]["1,2"]
    rec["available_iterations"] = [1, 2]
    rec["selected_iteration"] = 2
    write_manifest(path, m)


def mutate_bad_length(case):
    path, m = load_manifest(case)
    rel = "inputs/patch-1-2/c2-i1-after.bin"
    p = case / rel
    data = p.read_bytes()[:-1]
    p.write_bytes(data)
    repin(m, rel, data)
    write_manifest(path, m)


def mutate_nonfinite(case):
    path, m = load_manifest(case)
    rel = "inputs/patch-1-2/c2-i1-after.bin"
    p = case / rel
    data = bytearray(p.read_bytes())
    data[16:24] = struct.pack("<d", float("nan"))  # frame 1, x component
    data = bytes(data)
    p.write_bytes(data)
    repin(m, rel, data)
    write_manifest(path, m)


def mutate_gauge(case):
    path, m = load_manifest(case)
    rel = "inputs/patch-1-2/c2-i1-after.bin"
    p = case / rel
    data = bytearray(p.read_bytes())
    data[0:8] = struct.pack("<d", 0.25)  # frame-zero x component
    data = bytes(data)
    p.write_bytes(data)
    repin(m, rel, data)
    write_manifest(path, m)


CASES = [
    ("missing-selector", mutate_missing_selector, "selector set must contain exactly nine unique patches"),
    ("duplicate-json-selector-key", mutate_duplicate_json_selector, "duplicate JSON key 1,1"),
    ("missing-star-frame", mutate_missing_star_frame, "STAR coverage must be exactly 45 centre/frame rows"),
    ("mismatched-final-iteration", mutate_final_iteration, "selected snapshot is not the final captured iteration"),
    ("malformed-after-length", mutate_bad_length, "malformed after bytes length"),
    ("nonfinite-after", mutate_nonfinite, "nonfinite shift"),
    ("frame-zero-gauge", mutate_gauge, "frame-zero gauge is not exactly zero"),
]


def check_original_index_iteration_scope():
    spec = importlib.util.spec_from_file_location("w4_consumer_metadata_scope", ROOT / "consume_w4_cpu_observations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Metadata-only fixture: unrelated CUDA and other source paths have larger K.
    source_files = {
        "runs/cpu-affine-on/capture/c2-i1-after.bin": {},
        "runs/cpu-affine-on/capture/c2-i2-after.bin": {},
        "runs/cuda-affine-on/capture/c2-i5-after.bin": {},
        "runs/cpu-affine-off/capture/c2-i4-after.bin": {},
        "runs/cpu-affine-on/capture/c2-i3-input.bin": {},
    }
    actual = module.source_after_iterations(source_files, "original-index")
    if actual != [1, 2]:
        raise SystemExit(f"FAIL original-index iteration scope expected=[1, 2] actual={actual}")
    print("PASS metadata fixture original-index scope: cpu-affine-on capture iterations [1, 2]")


def main():
    require_cpu64_admission()
    check_original_index_iteration_scope()
    with tempfile.TemporaryDirectory(prefix="motioncorr-w4-structural-") as td:
        parent = Path(td).resolve()
        if not parent.is_relative_to(Path("/tmp")):
            raise SystemExit("REFUSED: temporary control work must remain under /tmp")
        for name, mutate, expected in CASES:
            case = fresh_case(parent, name)
            mutate(case)
            env = os.environ.copy()
            env["MOTIONCORR_W4_STRUCTURAL_TEST_MODE"] = "1"
            proc = subprocess.run(
                [sys.executable, "-I", "consume_w4_cpu_observations.py", "--structural-test"],
                cwd=case, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                check=False,
            )
            output = proc.stdout
            if proc.returncode == 0 or expected not in output:
                raise SystemExit(
                    f"FAIL control={name} rc={proc.returncode} expected={expected!r}\n{output}"
                )
            print(f"PASS structural negative {name}: rc={proc.returncode}; reason={expected}")
    print("PASS all 7 structural negative controls; actual consumer remains UNRUN")


if __name__ == "__main__":
    main()
