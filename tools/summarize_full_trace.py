#!/usr/bin/env python3
"""Summarize all exact checkpoint comparisons, including every peak/frame."""

import argparse
import collections
import json
import pathlib
import re

import numpy as np


def read_peak_pairs(cpu, cuda):
    result = {}
    for source in sorted(cpu.glob("*_peaks.bin")):
        key = source.stem
        other = cuda / source.name
        metadata = json.loads(source.with_suffix(".json").read_text())
        shape = metadata["shape"]
        a = np.fromfile(source, dtype=np.float64).reshape(shape)
        b = np.fromfile(other, dtype=np.float64).reshape(shape)
        shift_error = np.hypot(a[:, 11] - b[:, 11], a[:, 12] - b[:, 12])
        result[key] = {
            "frames": len(a),
            "integer_peak_changed_frames": np.flatnonzero(np.any(a[:, :2] != b[:, :2], axis=1)).tolist(),
            "interpolation_branch_changed_frames": np.flatnonzero(np.any(a[:, 13:15] != b[:, 13:15], axis=1)).tolist(),
            "scaled_shift_error_px_by_frame": shift_error.tolist(),
            "max_scaled_shift_error_px": float(shift_error.max()),
            "rms_scaled_shift_error_px": float(np.sqrt(np.mean(shift_error**2))),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metrics", type=pathlib.Path)
    parser.add_argument("cpu", type=pathlib.Path)
    parser.add_argument("cuda", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError(f"Refusing to overwrite: {args.output}")
    rows = [json.loads(line) for line in args.metrics.read_text().splitlines()]
    groups = collections.defaultdict(list)
    families = collections.defaultdict(list)
    for row in rows:
        key = row["key"]
        group = re.sub(r"_f\d{3}$", "", key)
        groups[group].append(row)
        families[re.sub(r"^p\d+_", "p*_", group)].append(row)

    def aggregate(items):
        finite_l2 = [item for item in items if item["relative_l2"] is not None]
        worst_l2 = max(finite_l2, key=lambda item: item["relative_l2"]) if finite_l2 else None
        worst_abs = max(items, key=lambda item: item["max_abs"])
        return {"checkpoints": len(items),
                "different_checkpoints": sum(bool(item["scalar_different"]) for item in items),
                "byte_different_checkpoints": sum(bool(item["byte_different"]) for item in items),
                "max_relative_l2": worst_l2["relative_l2"] if worst_l2 else None,
                "max_relative_l2_key": worst_l2["key"] if worst_l2 else None,
                "undefined_relative_l2_count": len(items) - len(finite_l2),
                "max_abs": worst_abs["max_abs"], "max_abs_key": worst_abs["key"],
                "nonfinite": sum(item["nonfinite"] for item in items)}

    summary = {"checkpoint_count": len(rows),
               "different_checkpoint_count": sum(bool(item["scalar_different"]) for item in rows),
               "byte_different_checkpoint_count": sum(bool(item["byte_different"]) for item in rows),
               "nonfinite_count": sum(item["nonfinite"] for item in rows),
               "groups": {key: aggregate(items) for key, items in sorted(groups.items())},
               "families": {key: aggregate(items) for key, items in sorted(families.items())},
               "peaks": read_peak_pairs(args.cpu, args.cuda)}
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"checkpoints": summary["checkpoint_count"],
                      "different": summary["different_checkpoint_count"],
                      "nonfinite": summary["nonfinite_count"],
                      "peak_records": len(summary["peaks"])}))


if __name__ == "__main__":
    main()
