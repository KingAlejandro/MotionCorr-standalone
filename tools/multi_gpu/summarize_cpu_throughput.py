#!/usr/bin/env python3
"""Describe paired diagnostic layouts; never upgrade host certification."""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'profiling'))
from lib import stats


def finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [finite(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--compare', action='append', required=True)
    parser.add_argument('--out', required=True, type=Path)
    a = parser.parse_args()
    rows = json.loads(a.results.read_text())
    report = {'certified': False, 'input': str(a.results), 'layouts': {}, 'comparisons': {},
              'scope': 'within this explicitly diagnostic fallback series; no native ownership, isolation or NUMA verdict',
              'skips_and_errors': [row for row in rows if row.get('skip') or row.get('error')]}
    positions = {id(row): index for index, row in enumerate(rows)}
    for name in [a.reference, *a.compare]:
        kept = [row for row in rows if row['name'] == name and not row['warmup']
                and row.get('diagnostic_complete') and row.get('products_identical')]
        report['layouts'][name] = {'n_retained': len(kept)}
        if kept:
            report['layouts'][name].update(
                median_dataset_wall_s=statistics.median(row['dataset_wall_s'] for row in kept),
                dataset_walls_s=[row['dataset_wall_s'] for row in kept],
                median_worker_phase_s=statistics.median(row['worker_phase_wall_s'] for row in kept),
                median_movies_per_s=statistics.median(row['movies_per_s'] for row in kept),
                max_sum_individual_worker_rss_kib=max(row['sum_worker_peak_rss_kib'] for row in kept))
    refs = {row['replicate']: row for row in rows if row['name'] == a.reference and not row['warmup']}
    for name in a.compare:
        pairs = []
        for row in rows:
            if row['name'] != name or row['warmup']:
                continue
            ref = refs.get(row['replicate'])
            if not ref or not all(item.get('diagnostic_complete') and item.get('products_identical') for item in (ref, row)):
                continue
            pairs.append({'a': ref['dataset_wall_s'], 'b': row['dataset_wall_s'],
                          'replicate': row['replicate'], 'order': 'AB' if positions[id(ref)] < positions[id(row)] else 'BA'})
        report['comparisons'][name] = {'reference': a.reference, 'pairs': pairs,
                                        'descriptive_paired_statistics': stats.paired(pairs)}
    a.out.write_text(json.dumps(finite(report), indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
