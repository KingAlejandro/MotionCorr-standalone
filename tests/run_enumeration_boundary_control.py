#!/usr/bin/env python3
"""Exercise returned enumeration errors through the production movie runner.

All injections are test-link wrappers; no GPU is poisoned or reset. Result directories
are create-only. Optional mutants must have only the corresponding recording line
removed. A mutant is accepted only if it completes, produces an image/joint STAR and
never emits the fatal refusal, so an unrelated crash cannot satisfy the control.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("movie", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--initialize-mutant", type=Path)
    parser.add_argument("--patch-mutant", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    common = ["--i", str(args.movie.resolve()), "--use_own", "--gpu", "0",
              "--j", "4", "--max_io_threads", "2", "--patch_x", "3", "--patch_y", "3",
              "--bfactor", "150", "--seed", "1", "--max_iter", "1",
              "--dose_weighting", "--dose_per_frame", "1", "--voltage", "300",
              "--angpix", "0.885"]
    rows = []

    def run(name, ordinal=0, code="zero-devices", binary=None):
        destination = args.output / name
        destination.mkdir()
        command = [str((binary or args.binary).resolve()), *common,
                   "--o", str(destination.resolve()) + "/"]
        env = dict(os.environ, MC_FAULT_ORDINAL="0", MC_FAULT_TRACE="1",
                   MC_COUNT_FAULT_ORDINAL=str(ordinal), MC_COUNT_FAULT_CODE=code)
        with (destination / "run.log").open("w") as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=180)
        text = "\n".join(path.read_text(errors="replace")
                         for path in destination.rglob("*.log"))
        row = dict(name=name, command=command, ordinal=ordinal, code=code,
                   exit=result.returncode, images=len(list(destination.rglob("*.mrc"))),
                   joint_stars=len(list(destination.rglob("corrected_micrographs.star"))))
        if ordinal:
            assert f"at cudaGetDeviceCount #{ordinal}; last-error clean" in text, row
        assert "remaining-owned=0 stale-releases=0" in text, row
        rows.append(row)
        return row, text

    def completed(row):
        assert row["exit"] == 0 and row["images"] == 1 and row["joint_stars"] == 1, row

    baseline, text = run("healthy")
    completed(baseline)
    count = max(map(int, re.findall(r"cudaGetDeviceCount #(\d+)", text)))
    markers = {"initialize": "Fatal CUDA session initialization failure",
               "patch": "recorded at cudaPreparePatch:"}
    ordinals = {}
    for ordinal in range(1, min(count, 12) + 1):
        row, text = run(f"discover-{ordinal}", ordinal, "poison")
        for boundary, marker in markers.items():
            if boundary not in ordinals and marker in text:
                assert row["exit"] != 0 and row["images"] == row["joint_stars"] == 0, row
                # No new device allocation is allowed after the returned fatal status.
                tail = (args.output / row["name"] / "run.log").read_text().split(
                    f"at cudaGetDeviceCount #{ordinal}; last-error clean", 1)[1]
                assert "cudaMalloc #" not in tail, row
                ordinals[boundary] = ordinal
        if len(ordinals) == 2:
            break
    assert len(ordinals) == 2, f"Missing production boundary: {ordinals}"
    for boundary, ordinal in ordinals.items():
        for code in ("recoverable", "zero-devices"):
            row, text = run(f"{boundary}-{code}", ordinal, code)
            completed(row)
            assert all(marker not in text for marker in markers.values()), row
        mutant = args.initialize_mutant if boundary == "initialize" else args.patch_mutant
        if mutant:
            row, text = run(f"{boundary}-mutant", ordinal, "poison", mutant)
            completed(row)
            assert all(marker not in text for marker in markers.values()), row
    report = dict(status="PASS", production_ordinals=ordinals, runs=rows,
                  mutation_controls="PASS" if args.initialize_mutant and args.patch_mutant else "UNRUN",
                  scope="Returned error-code injection with clean last-error slot; no real context poisoning")
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
