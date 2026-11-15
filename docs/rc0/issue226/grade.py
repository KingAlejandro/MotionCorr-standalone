#!/usr/bin/env python3
"""Grade retained #226 balloon results; absence of a required row is failure."""
import argparse
import json
from pathlib import Path

D2_BANDS = {'e10441': [37.5, 38, 38.5], 'e10474f4': [19, 19.5], 'e10216': [8.5]}
D2_NEIGHBOURS = {'e10441': [36.5, 37, 39], 'e10474f4': [18.5, 20], 'e10216': [7.5, 8, 8.75, 16]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['d2', 'd3'])
    p.add_argument('data', type=Path)
    p.add_argument('--candidate', required=True)
    args = p.parse_args()
    data = json.loads(args.data.read_text())
    base = {r['spec']: r for r in data['runs-base']}
    candidate = {r['spec']: r for r in data[args.candidate]}
    checks = []

    def check(spec, must_complete, changed):
        errors = []
        a, b = base.get(spec), candidate.get(spec)
        if a is None or b is None:
            checks.append({'spec': spec, 'errors': ['missing required row']})
            return
        if b['timed_out'] or not b['balloon_gone'] or b['gpu_apps_after']:
            errors.append('timeout or incomplete GPU/balloon cleanup')
        if must_complete:
            if b['exit'] != 0 or not b['all_products'] or b['compare'].get('products_rc') != 0:
                errors.append('movie did not complete with identical products')
            if not changed:
                if a['exit'] != 0:
                    errors.append('neighbour was not a passing before-control')
                if b['local_admission'] or b['retry_admission']:
                    errors.append('previously passing neighbour changed local admission')
                if [w.split()[-1] for w in a['witness']] != [w.split()[-1] for w in b['witness']]:
                    errors.append('previously passing neighbour changed ingest route')
                if a['batch_chunks'] != b['batch_chunks']:
                    errors.append('previously passing neighbour changed patch batch route')
                if a['cpu_preprocessing'] != b['cpu_preprocessing']:
                    errors.append('previously passing neighbour changed preprocessing route')
            elif a['exit'] != 1:
                errors.append('band did not reproduce the unfixed failure')
        else:
            if a['exit'] != 1 or a['early_oom']:
                errors.append('before-control did not reproduce the late failure')
            if b['exit'] != 1 or not b['early_oom'] or b['incompatible'] or b['joint_star']:
                errors.append('missing early named OOM or changed failure/publication behaviour')
            if any(v.get('.mrc') or v.get('.star') for v in b['stray_products'].values()):
                errors.append('failed movie published products')
        checks.append({'spec': spec, 'errors': errors})

    if args.mode == 'd2':
        for family, points in D2_BANDS.items():
            for value in points:
                check(f'{family}-L-auto@{value:g}', True, True)
        for family, points in D2_NEIGHBOURS.items():
            for value in points:
                check(f'{family}-L-auto@{value:g}', True, False)
    else:
        for config in ['G', 'L']:
            for ingest in ['auto', 'float']:
                for value in [16, 21]:
                    check(f'e10441-{config}-{ingest}@{value}', False, True)
                check(f'e10441-{config}-{ingest}@22', True, False)
    report = {'mode': args.mode, 'candidate': args.candidate,
              'verdict': 'FAIL' if any(r['errors'] for r in checks) else 'PASS',
              'checks': checks}
    print(json.dumps(report, indent=2))
    return report['verdict'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
