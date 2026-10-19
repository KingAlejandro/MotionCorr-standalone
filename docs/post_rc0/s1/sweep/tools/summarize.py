#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate per-movie CSV and family counts from retained comparator records."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import tarfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("evidence", type=Path)
a = p.parse_args()
manifest = json.loads((a.evidence / "manifest.json").read_text())
inputs = {r["id"]: r for r in manifest["movies"]}
rows = []
raw_index = json.loads((a.evidence / 'raw_files.json').read_text()) if (a.evidence / 'raw_files.json').is_file() else {}
archive_logs = {}

def movie_log(folder):
    logs = list(folder.glob('*.log.gz'))
    if logs:
        assert len(logs) == 1
        return gzip.decompress(logs[0].read_bytes()).decode()
    prefix = str(folder.relative_to(a.evidence)) + '/'
    keys = [k for k in raw_index if k.startswith(prefix) and k.endswith('.log.gz')]
    assert len(keys) == 1, folder
    item = raw_index[keys[0]]
    if item['archive'] not in archive_logs:
        archive_logs[item['archive']] = {}
        with tarfile.open(a.evidence / item['archive']) as tar:
            for member in tar:
                if '/Movies/' in member.name and member.name.endswith('.log.gz'):
                    archive_logs[item['archive']][member.name] = gzip.decompress(tar.extractfile(member).read()).decode()
    return archive_logs[item['archive']][item['member']]
def primary_venue(inp):
    if inp['family'] in ('e10216', 'e10474f3'):
        return 'SCARF'
    if inp['family'] == 'e10474f4':
        return '4GPUs' if inp['rank'] < 2 else 'SCARF'
    if inp['family'] == 'e10164':
        return '4GPUs' if inp['rank'] == 0 else 'SCARF'
    return '4GPUs'

for path in sorted(a.evidence.rglob("*-F-cuda.json")):
    x = json.loads(path.read_text())
    gate = json.loads(path.with_name(path.stem + "-backend.json").read_text())
    ref, test = x[x["reference"]], x[x["test"]]
    venue_root = path.parent.parent
    arms = [json.loads((venue_root / "runs" / label / "run.json").read_text())
            for label in (x["reference"], x["test"])]
    venue = x.get("venue", "4GPUs")
    host_basis = 'per-arm records'
    if venue == '4GPUs' and any('hostname' not in r for r in arms):
        inventory = json.loads((a.evidence / 'collection-host.json').read_text())
        host = next(r['stdout'].strip() for r in inventory if r['command'] == 'hostname' and r['exit_status'] == 0)
        assert all(r['cwd'].startswith('/mnt/clathrin/alex-motioncorr-s1/sweep/') for r in arms)
        hosts = [r.get('hostname', host) for r in arms]
        host_basis = 'scratch paths and collection host inventory; early records omit hostname'
    else:
        hosts = [r['hostname'] for r in arms]
    assert hosts[0] == hosts[1], "cross-host backend pair"
    assert arms[0]['cpu_mask'] == arms[1]['cpu_mask']
    inp = inputs[x["movie"]]
    grid = int(x["test"].split("-p")[1][0])
    image = gate["checks"]["corrected_image"]
    traj = gate["checks"]["motion_trajectory"]
    cuda_log = movie_log(venue_root / 'runs' / x['test'] / 'Movies')
    assert all(r["movie_sha256"] == inp["movie_sha256"] for r in arms)
    assert all(r['exit_status'] == 0 for r in arms)
    rows.append(dict(family=inp["family"], venue=venue, hostname=hosts[0], host_basis=host_basis,
                     allocation=arms[1].get('slurm_job_id', ''), cpu_mask=arms[0]['cpu_mask'],
                     cuda_gpu_uuid=arms[1]['requested_gpu_uuid'],
                     primary_sample=venue == primary_venue(inp),
                     movie_id=x["movie"], movie=inp["relative_path"], movie_sha256=inp["movie_sha256"], grid=grid,
                     evidence=str(path.relative_to(a.evidence)),
                     cuda_global_completion_markers=cuda_log.count('[CUDA Global Alignment] completed'),
                     cuda_patch_completion_markers=cuda_log.count('[CUDA Patch Alignment] completed'),
                     cpu_rows=ref["local_shift_rows"], cuda_rows=test["local_shift_rows"],
                     cpu_converged=ref["accepted_patches"], cuda_converged=test["accepted_patches"],
                     cpu_only=json.dumps(x["cpu_only_patches"]), cuda_only=json.dumps(x["test_only_patches"]),
                     backend_status=x["backend_status"], comparator_exit_status=x["comparator_exit_status"],
                     relative_rmse=x["relative_rmse"], absolute_rmse=image["rmse"], max_pixel_error=image["max_abs_pixel_error"],
                     global_coord_rms=traj["coord_rms_error"], global_max_error=traj["max_shift_error"],
                     large_s1_screen=x["relative_rmse"] >= .1,
                     both_accept_zero=ref['accepted_patches'] == test['accepted_patches'] == 0,
                     global_trajectory_failed=not traj['passed'],
                     any_nonconvergence=min(ref["accepted_patches"], test["accepted_patches"]) < grid*grid,
                     differing_accepted_sets=bool(x["cpu_only_patches"] or x["test_only_patches"])))
with (a.evidence.parent / "per_movie.csv").open("w") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
def aggregate(subset):
    assert len(subset) == len({r['movie_sha256'] for r in subset}), 'duplicate input in incidence denominator'
    return dict(movies=len(subset), backend_fail=sum(r['backend_status'] == 'FAIL' for r in subset),
                large_s1=sum(r['large_s1_screen'] for r in subset),
                any_nonconvergence=sum(r['any_nonconvergence'] for r in subset),
                differing_sets=sum(r['differing_accepted_sets'] for r in subset),
                large_s1_with_nonconvergence=sum(r['large_s1_screen'] and r['any_nonconvergence'] for r in subset),
                large_s1_with_differing_sets=sum(r['large_s1_screen'] and r['differing_accepted_sets'] for r in subset),
                large_s1_both_accept_zero=sum(r['large_s1_screen'] and r['both_accept_zero'] for r in subset),
                large_s1_global_trajectory_failed=sum(r['large_s1_screen'] and r['global_trajectory_failed'] for r in subset),
                relative_rmse_range=[min(r['relative_rmse'] for r in subset), max(r['relative_rmse'] for r in subset)])

summary = {}
for family in sorted({r['family'] for r in rows}):
    selected = [r for r in rows if r['family'] == family]
    completed = {r['movie_sha256'] for r in selected if r['grid'] == 5} & {r['movie_sha256'] for r in selected if r['grid'] == 3}
    summary[family] = dict(distinct_inputs_both_grids=len(completed), primary={}, venues={})
    for grid in (5, 3):
        subset = [r for r in selected if r['grid'] == grid and r['primary_sample']]
        if subset:
            summary[family]['primary'][str(grid)] = aggregate(subset)
    for venue in sorted({r['venue'] for r in selected}):
        summary[family]['venues'][venue] = {}
        for grid in (5, 3):
            subset = [r for r in selected if r['grid'] == grid and r['venue'] == venue]
            if subset:
                summary[family]['venues'][venue][str(grid)] = aggregate(subset)
(a.evidence.parent / 'family_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
