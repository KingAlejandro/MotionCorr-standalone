#!/usr/bin/env python3
"""Read-only reduction of retained timing receipts; never substitutes missing rows."""
import argparse, hashlib, json, pathlib, statistics, sys

PRIMARY = ('ingest_ready_device_wall_s', 'checked_exit_monotonic_s')

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', type=pathlib.Path, required=True)
    ap.add_argument('--out', type=pathlib.Path, required=True)
    a = ap.parse_args()
    root = a.run.resolve()
    progress = root / 'pairs/progress.json'
    complete = root / 'pairs/summary.json'
    state = json.loads((complete if complete.exists() else progress).read_text())
    result = {
        'run_root': str(root), 'state': state['status'],
        'error': state.get('error'), 'recorded_process_rows': len(state['runs']),
        'complete_files': len(state['inputs']), 'metrics': {}, 'files': [],
        'timing_claim': state['timing_claim'],
        'scope': 'Standalone warm-cache real U8 LZW native-device ingest; no application, real U16, safety or licensing result',
        'sign': 'Positive compact minus nvTIFF is saving, seconds/movie',
        'overall_definition': 'Equal-file mean of five paired medians; envelope = means of file bounds, not pooled confidence; null = maximum per-file magnitude',
        'source_receipts': {str(p): digest(p) for p in (progress, complete, root / 'pairs/identities.json') if p.exists()},
    }
    # Verify published row associations/hashes independently of the driver.
    for r in state['runs']:
        for key in ('raw_receipt', 'accounted_receipt'):
            path = pathlib.Path(r[key])
            if digest(path) != r[key + '_sha256']:
                raise RuntimeError('retained row identity changed: ' + str(path))
    for item in state['inputs']:
        if len(item['pairs']) != 12 or len(item['null_rows']) != 24:
            raise RuntimeError('incomplete per-file schedule')
        f = {'id': item['id'], 'recipe': item['recipe'], 'driver_verdict': item['verdict'], 'metrics': {}}
        for metric, row in item['metrics'].items():
            deltas = [p['A']['metrics'][metric] - p['B']['metrics'][metric] for p in item['pairs']]
            null = []
            null_by_arm = {}
            for arm in ('compact', 'nvtiff'):
                rows = [r for r in item['null_rows'] if r['arm'] == arm]
                values = [rows[i+1]['metrics'][metric] - rows[i]['metrics'][metric] for i in range(0, 12, 2)]
                null_by_arm[arm] = values
                null.extend(values)
            median = statistics.median(deltas)
            noise = max(map(abs, null))
            if abs(median + row['paired_median_delta_s']) > 1e-12 or abs(noise-row['max_abs_null_s']) > 1e-12:
                raise RuntimeError('independent paired/null calculation differs')
            lo, hi = row['balanced_bootstrap_descriptive_95_s']
            f['metrics'][metric] = {
                'compact_median_s': row['A_median_s'], 'nvtiff_median_s': row['B_median_s'],
                'paired_savings_s': deltas, 'paired_median_saving_s': median,
                'descriptive_saving_interval_s': [-hi, -lo],
                'null_right_minus_left_by_arm_s': null_by_arm,
                'null_band_s': [-noise, noise], 'required_saving_s': max(.15, noise),
                'resolved_at_declared_minimum': row['resolved_at_declared_minimum'],
            }
        result['files'].append(f)
    full = (state['status'] == 'COMPLETE' and len(state['runs']) == 250 and len(state['inputs']) == 5
            and all(r['qualification'] == 'PASS' for r in state['runs']))
    if full:
        for metric in state['inputs'][0]['metrics']:
            rows = [f['metrics'][metric] for f in result['files']]
            noise = max(r['null_band_s'][1] for r in rows)
            interval = [statistics.mean(r['descriptive_saving_interval_s'][i] for r in rows) for i in (0, 1)]
            result['metrics'][metric] = {
                'equal_file_compact_median_mean_s': statistics.mean(r['compact_median_s'] for r in rows),
                'equal_file_nvtiff_median_mean_s': statistics.mean(r['nvtiff_median_s'] for r in rows),
                'equal_file_paired_median_mean_saving_s': statistics.mean(r['paired_median_saving_s'] for r in rows),
                'descriptive_envelope_s': interval, 'conservative_null_band_s': [-noise, noise],
                'required_saving_s': max(.15, noise), 'resolved_at_declared_minimum': interval[0] > max(.15, noise),
            }
        overall_go = all(result['metrics'][m]['resolved_at_declared_minimum'] for m in PRIMARY)
        every_file_go = all(f['metrics'][m]['resolved_at_declared_minimum'] for f in result['files'] for m in PRIMARY)
        # Deliberately do not relabel an unresolved interval a resolved NO-GO.
        below = any(result['metrics'][m]['descriptive_envelope_s'][1] < .15 for m in PRIMARY)
        result['verdict'] = 'GO' if overall_go and every_file_go else ('NO-GO' if below else 'UNRESOLVED')
        result['every_file_meets_go'] = every_file_go
    else:
        result['verdict'] = 'UNRESOLVED'
    for name in ('exit.txt', 'timing-exit.txt', 'acceptance-exit.txt', 'resources.json', 'release.json', 'compute-before.csv', 'compute-after.csv', 'compute-apps-start.csv', 'compute-apps-end.csv', 'thp.txt', 'start.utc', 'started.utc', 'end.utc', 'ended.utc', 'hostname.txt'):
        p = root / name
        if p.exists():
            result.setdefault('run_metadata', {})[name] = p.read_text().strip()
            result['source_receipts'][str(p)] = digest(p)
    a.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('verdict', 'state', 'recorded_process_rows', 'complete_files', 'metrics')}, indent=2))

if __name__ == '__main__':
    main()
