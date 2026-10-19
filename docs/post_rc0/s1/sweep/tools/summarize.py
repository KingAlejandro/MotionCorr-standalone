#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate per-movie CSV and family counts from retained comparator records."""
import argparse
import csv
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("evidence", type=Path)
a = p.parse_args()
manifest = json.loads((a.evidence / "manifest.json").read_text())
inputs = {r["id"]: r for r in manifest["movies"]}
rows = []
for path in sorted((a.evidence / "analysis").glob("*-F-cuda.json")):
    x = json.loads(path.read_text())
    gate = json.loads(path.with_name(path.stem + "-backend.json").read_text())
    ref, test = x[x["reference"]], x[x["test"]]
    inp = inputs[x["movie"]]
    grid = int(x["test"].split("-p")[1][0])
    image = gate["checks"]["corrected_image"]
    traj = gate["checks"]["motion_trajectory"]
    rows.append(dict(family=inp["family"], movie_id=x["movie"], movie=inp["relative_path"], grid=grid,
                     cpu_rows=ref["local_shift_rows"], cuda_rows=test["local_shift_rows"],
                     cpu_converged=ref["accepted_patches"], cuda_converged=test["accepted_patches"],
                     cpu_only=json.dumps(x["cpu_only_patches"]), cuda_only=json.dumps(x["test_only_patches"]),
                     backend_status=x["backend_status"], comparator_exit_status=x["comparator_exit_status"],
                     relative_rmse=x["relative_rmse"], absolute_rmse=image["rmse"], max_pixel_error=image["max_abs_pixel_error"],
                     global_coord_rms=traj["coord_rms_error"], global_max_error=traj["max_shift_error"],
                     large_s1_screen=x["relative_rmse"] >= .1,
                     any_nonconvergence=min(ref["accepted_patches"], test["accepted_patches"]) < grid*grid,
                     differing_accepted_sets=bool(x["cpu_only_patches"] or x["test_only_patches"])))
with (a.evidence.parent / "per_movie.csv").open("w") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
summary = {}
for family in sorted({r["family"] for r in rows}):
    summary[family] = {}
    for grid in (5, 3):
        subset = [r for r in rows if r["family"] == family and r["grid"] == grid]
        if not subset:
            continue
        summary[family][str(grid)] = dict(movies=len(subset), backend_fail=sum(r["backend_status"] == "FAIL" for r in subset),
                                        large_s1=sum(r["large_s1_screen"] for r in subset),
                                        any_nonconvergence=sum(r["any_nonconvergence"] for r in subset),
                                        differing_sets=sum(r["differing_accepted_sets"] for r in subset),
                                        relative_rmse_range=[min(r["relative_rmse"] for r in subset), max(r["relative_rmse"] for r in subset)])
(a.evidence.parent / "family_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
