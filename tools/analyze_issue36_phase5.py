#!/usr/bin/env python3
"""Summarize the fixed-weight and common-trajectory Issue 36 controls."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_gate(path):
    gate = json.loads(path.read_text())
    if not gate["coverage"]["complete"]:
        raise ValueError(f"Incomplete image gate: {path}")
    return {"status": gate["overall_status"],
            "relative_image_rmse": gate["checks"]["corrected_image"]["relative_rmse"],
            "trajectory_rmse_px": gate["checks"]["motion_trajectory"]["coord_rms_error"],
            "star_differences": gate["checks"]["star_fields"]["num_differences"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movie", choices=("00021", "00046"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--comparator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Refusing to overwrite summary")
    m, root = args.movie, args.root
    cpu = root / f"release_{m}_cpu/trace"
    weight = root / f"issue36_phase5/weight_{m}/trace"
    common = root / f"issue36_phase5/trajectory_{m}/trace"
    legacy_common = root / f"issue36_phase5/legacy_trajectory_{m}/trace"
    groups = ("g_i01_postshift", "g_i02_postshift", "g_i00_ifft",
              "out_i00_modelx", "out_i00_modely", "out_i00_interp",
              "out_i00_cumsum")
    paired = {}
    for group in groups:
        identical = []
        for frame in range(24):
            key = f"{group}_f{frame:03d}.bin"
            identical.append(sha(common / key) == sha(legacy_common / key))
        paired[group] = {"frames": 24, "byte_identical_frames": sum(identical)}
    paired["out_i00_sum"] = {"byte_identical":
                              sha(common / "out_i00_sum.bin") ==
                              sha(legacy_common / "out_i00_sum.bin")}
    weight_hash = {"cpu": sha(cpu / "g_i00_weight.bin"),
                   "exact_cuda": sha(weight / "g_i00_weight.bin")}
    weight_hash["byte_identical"] = weight_hash["cpu"] == weight_hash["exact_cuda"]
    spectrum = []
    ccf = []
    for frame in range(24):
        for stage, destination, dtype in (("fccs", spectrum, "c8"), ("iccs", ccf, "f4")):
            key = f"g_i01_{stage}_f{frame:03d}.bin"
            result = subprocess.run([str(args.comparator), str(cpu / key), str(weight / key),
                                     dtype, dtype], check=True, capture_output=True, text=True)
            metrics = json.loads(result.stdout)
            destination.append({"frame": frame, "rmse": metrics["rmse"],
                                "max_abs": metrics["max_abs"],
                                "scalar_different": metrics["scalar_different"]})
    gates = {name: checked_gate(root / f"issue36_phase5/{name}_{m}/gate2.json")
             for name in ("weight", "trajectory", "legacy_trajectory")}
    gates["original"] = checked_gate(root / f"release_{m}_gate2.json")
    reproduction = json.loads((root / f"issue36_phase5/cpu_repro_{m}.json").read_text())
    common_summary = json.loads((root / f"issue36_phase5/trajectory_{m}/summary.json").read_text())
    result = {"movie": m, "cpu_reproduction": {
        "all_replay_arrays_identical": reproduction["all_replay_arrays_identical"],
        "corrected_payload_identical": reproduction["corrected_payload_identical"]},
        "global_weight_sha256": weight_hash,
        "first_iteration_fccs": {"frames": spectrum,
                                 "max_rmse": max(item["rmse"] for item in spectrum),
                                 "max_abs": max(item["max_abs"] for item in spectrum)},
        "first_iteration_iccs": {"frames": ccf,
                                 "max_rmse": max(item["rmse"] for item in ccf)},
        "trajectory_weight_control": paired, "gates": gates,
        "common_trajectory_stage_groups": {key: common_summary["groups"][key]
                                           for key in ("g_i01_postshift", "g_i02_fref",
                                                       "g_i02_postshift", "g_i00_ifft",
                                                       "out_i00_modelx", "out_i00_modely",
                                                       "out_i00_interp", "out_i00_cumsum",
                                                       "out_i00_sum")},
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    if not weight_hash["byte_identical"] or not all(
            item.get("byte_identical", item.get("byte_identical_frames") == 24)
            for item in paired.values()):
        raise SystemExit("Weight or common-trajectory control did not match exactly")


if __name__ == "__main__":
    main()
