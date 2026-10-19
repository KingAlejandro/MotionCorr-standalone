#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate retained observations and report incomplete breadth separately."""
import argparse
import csv
import gzip
import hashlib
import json
import re
import tarfile
from collections import Counter
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('evidence', type=Path)
p.add_argument('--require-complete', action='store_true')
a = p.parse_args()
manifest = json.loads((a.evidence / 'manifest.json').read_text())
movies = {r['id']: r for r in manifest['movies']}
raw_index = json.loads((a.evidence / 'raw_files.json').read_text()) if (a.evidence / 'raw_files.json').is_file() else {}

def raw_text(folder, suffix):
    files = list(folder.glob('*' + suffix))
    if len(files) == 1:
        return gzip.decompress(files[0].read_bytes()).decode()
    prefix = str(folder.relative_to(a.evidence)) + '/'
    keys = [k for k in raw_index if k.startswith(prefix) and k.endswith(suffix)]
    if len(keys) != 1:
        return None
    item = raw_index[keys[0]]
    with tarfile.open(a.evidence / item['archive']) as tar:
        data = tar.extractfile(item['member']).read()
    assert hashlib.sha256(data).hexdigest() == item['sha256']
    return gzip.decompress(data).decode()
corpus = (Path(__file__).resolve().parents[5] / 'docs/workload_corpus/corpus.md').read_text()
expected = dict(re.findall(r"`([^`]+)`\s*\|\s*[\d,]+\s*\|\s*`([0-9a-f]{64})`", corpus))
for row in movies.values():
    if row['relative_path'] in expected:
        assert row['movie_sha256'] == expected[row['relative_path']], row['relative_path']
failures = []
controls = []
runs = []
failed_attempts = []
early_comparator_records = []
binary_hashes = {}
hash_files = list(a.evidence.rglob('binaries.sha256.gz')) + list((a.evidence / 'frozen-builds').glob('*.sha256'))
for path in hash_files:
    text = gzip.decompress(path.read_bytes()).decode() if path.suffix == '.gz' else path.read_text()
    for line in text.splitlines():
        digest, name = line.split(None, 1)
        assert name not in binary_hashes or binary_hashes[name] == digest
        binary_hashes[name] = digest
for path in a.evidence.rglob('run.json'):
    run = json.loads(path.read_text())
    runs.append(run)
    assert binary_hashes[run['binary']] == run['binary_sha256'], path
    if run.get('exit_status') != 0:
        failures.append(dict(record=str(path.relative_to(a.evidence)), reason='native exit is not zero'))
        movie = movies[run['movie']]
        failed_attempts.append(dict(venue=run.get('venue', '4GPUs'), movie_id=run['movie'], family=movie['family'],
                                    movie=movie['relative_path'], movie_sha256=run['movie_sha256'],
                                    grid=int(run['label'].split('-p')[1][0]), backend='CUDA' if run['gpu'] else 'CPU',
                                    native_exit_status=run.get('exit_status', 'not retained'),
                                    backend_gate='UNRUN: native arm failed', relative_rmse='UNRUN',
                                    cpu_converged='UNRUN', cpu_local_shift_rows='UNRUN', cuda_converged='UNRUN',
                                    binary_sha256=run['binary_sha256'], record=str(path.relative_to(a.evidence))))
        if run['gpu']:
            cpu_dir = path.parent.parent / (run['label'].removesuffix('-cuda') + '-cpu')
            cpu_record = cpu_dir / 'run.json'
            if cpu_record.is_file() and json.loads(cpu_record.read_text()).get('exit_status') == 0:
                star = raw_text(cpu_dir / 'Movies', '.star.gz')
                if star and 'data_local_shift' in star:
                    block = star.split('data_local_shift', 1)[1].split('data_', 1)[0]
                    observations = [s.split() for s in block.splitlines()
                                    if s.strip() and not s.strip().startswith(('#', '_', 'loop_'))]
                    centers = Counter((r[1], r[2]) for r in observations)
                    assert all(n == movie['recipe']['frames'] for n in centers.values())
                    failed_attempts[-1].update(cpu_converged=len(centers), cpu_local_shift_rows=len(observations))
    if run['movie_sha256'] != movies[run['movie']]['movie_sha256']:
        failures.append(dict(record=str(path.relative_to(a.evidence)), reason='input identity mismatch'))
    if run['gpu'] and run.get('gpu_witness_uuids') != [run['requested_gpu_uuid']]:
        failures.append(dict(record=str(path.relative_to(a.evidence)), reason='missing or incorrect GPU UUID witness'))
for path in a.evidence.rglob('analysis/*.json'):
    x = json.loads(path.read_text())
    if 'identical' in x:
        controls.append(dict(record=str(path.relative_to(a.evidence)), identical=x['identical'],
                             exact_comparator_exit_status=x['exact_comparator_exit_status']))
    if 'reference' not in x or 'test' not in x or x['reference'] not in x:
        continue
    if 'comparator_sha256' in x:
        assert x['comparator_sha256'] == 'cb37991af515c5529f31ac48adb157771b1ac21b8308ba28735362f36085e46b'
    else:
        cmd = x.get('comparator_argv', x.get('exact_comparator_argv'))
        assert cmd[1] == '/mnt/clathrin/alex-motioncorr-rc0/W-QF/src/tools/compare_motioncorr.py'
        early_comparator_records.append(str(path.relative_to(a.evidence)))
    count = movies[x['movie']]['recipe']['frames']
    for label in (x['reference'], x['test']):
        obs = x[label]
        if obs['local_shift_rows'] != obs['accepted_patches'] * count or any(v != count for v in obs['rows_per_center'].values()):
            failures.append(dict(record=str(path.relative_to(a.evidence)), reason='incomplete local-shift rows'))
rows = list(csv.DictReader((a.evidence.parent / 'per_movie.csv').open()))
for row in rows:
    assert int(row['cuda_global_completion_markers']) >= 1, row['evidence']
    assert int(row['cuda_patch_completion_markers']) >= int(row['grid']) ** 2, row['evidence']
coverage = {}
for family in sorted({r['family'] for r in movies.values()}):
    subset = [r for r in rows if r['family'] == family]
    complete = {r['movie_sha256'] for r in subset if r['grid'] == '5'} & {r['movie_sha256'] for r in subset if r['grid'] == '3'}
    primary = [r for r in subset if r['primary_sample'] == 'True']
    primary_complete = {r['movie_sha256'] for r in primary if r['grid'] == '5'} & {r['movie_sha256'] for r in primary if r['grid'] == '3'}
    coverage[family] = dict(distinct_inputs_both_grids=len(complete), primary_distinct_inputs_both_grids=len(primary_complete),
                           at_least_ten=len(primary_complete) >= 10)
result = dict(validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              native_runs=len(runs), cuda_runs=sum(r['gpu'] for r in runs),
              successful_native_runs=sum(r.get('exit_status') == 0 for r in runs),
              completed_pair_observation_checks_valid=not any(f['reason'] != 'native exit is not zero' for f in failures),
              early_comparator_records_without_per_run_hash=early_comparator_records,
              retained_pairs=len(rows), failures=failures, cpu_controls=controls,
              cpu_controls_all_identical=bool(controls) and all(
                  c['identical'] and c['exact_comparator_exit_status'] == 0 for c in controls),
              coverage=coverage, breadth_at_least_ten_all_families=all(c['at_least_ten'] for c in coverage.values()))
recheck_path = a.evidence / 'comparator-rechecks/equivalence.json'
rechecks = json.loads(recheck_path.read_text()) if recheck_path.is_file() else []
result['early_comparator_rechecks_complete'] = (
    {r['original'] for r in rechecks} == set(early_comparator_records)
    and all(r['all_gate_fields_equal_after_path_normalization'] and r['comparator_sha256'] ==
            'cb37991af515c5529f31ac48adb157771b1ac21b8308ba28735362f36085e46b' for r in rechecks))
cross_path = a.evidence.parent / 'preparation/cross-venue/controls.json'
cross = json.loads(cross_path.read_text()) if cross_path.is_file() else []
scarf_allocations = {r.get('slurm_job_id') for r in runs if r.get('venue') == 'SCARF'}
result['cross_venue_controls_complete'] = bool(scarf_allocations) and all(
    c['identical'] and all(c['checks'].values()) for c in cross) and all(
    {(c['arm']) for c in cross if c.get('allocation') == allocation and c['same_input']} == {'cpu', 'cuda'}
    for allocation in scarf_allocations)
result['cross_venue_controls'] = dict(comparisons=len(cross), identical=sum(c['identical'] for c in cross),
                                     scope='common e10216-00 5x5 movie, complete main MRC byte regions with timestamp normalization and per-movie STAR')
if failed_attempts:
    with (a.evidence.parent / 'failed_attempts.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=list(failed_attempts[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(failed_attempts)
(a.evidence.parent / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k:v for k,v in result.items() if k != 'cpu_controls'}, indent=2))
raise SystemExit(bool(failures) or not result['cpu_controls_all_identical'] or
                 (a.require_complete and not (result['breadth_at_least_ten_all_families'] and result['early_comparator_rechecks_complete'] and result['cross_venue_controls_complete'])))
