#!/usr/bin/env python3
"""Summarize the retained fallback measurements without certifying isolation."""
import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/profiling'))
from lib import stats


def summary(path):
    data = json.loads(path.read_text())
    complete = {c['rep']: c for c in data['comparisons']}
    pairs, rss = [], []
    for rep in sorted(r for r in complete if r >= 0):
        runs = [r for r in data['runs'] if r['rep'] == rep]
        by_arm = {r['arm']: r for r in runs}
        if len(runs) != 2 or set(by_arm) != {'base', 'candidate'}:
            raise ValueError('incomplete or duplicate pair')
        if any(r['rc'] for r in runs) or not complete[rep]['identical']:
            continue
        base, candidate = by_arm['base'], by_arm['candidate']
        pairs.append({'rep': rep, 'a': base['wall_s'], 'b': candidate['wall_s'],
                      'order': 'AB' if runs[0]['arm'] == 'base' else 'BA'})
        rss.append({'rep': rep, 'base_kib': base['peak_rss_kib'],
                    'candidate_kib': candidate['peak_rss_kib'],
                    'delta_kib': candidate['peak_rss_kib'] - base['peak_rss_kib'],
                    'relative_delta': candidate['peak_rss_kib'] / base['peak_rss_kib'] - 1})
    def extent(values):
        return {'median': statistics.median(values), 'min': min(values), 'max': max(values)}
    return {
        'results': str(path), 'limitation': data['limitation'],
        'strict_identity_all_pairs_including_warmup': all(c['identical'] for c in complete.values()),
        'comparisons_including_warmup': len(complete),
        'mrc_comparisons_including_warmup': sum(c['mrc_compared'] for c in complete.values()),
        'pairs': pairs,
        'wall_descriptive_statistics_only': stats.paired(pairs),
        'rss_pairs': rss,
        'rss_base_kib': extent([r['base_kib'] for r in rss]),
        'rss_candidate_kib': extent([r['candidate_kib'] for r in rss]),
        'rss_relative_delta': extent([r['relative_delta'] for r in rss]),
        'cpu_base_s': extent([r['user_s'] + r['sys_s'] for r in data['runs']
                              if r['rep'] >= 0 and r['arm'] == 'base']),
        'cpu_candidate_s': extent([r['user_s'] + r['sys_s'] for r in data['runs']
                                   if r['rep'] >= 0 and r['arm'] == 'candidate']),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('results', type=Path, nargs='+')
    args = parser.parse_args()
    args.out.write_text(json.dumps({'scope': 'fallback observations, not a clean mcprof verdict',
                                    'configurations': [summary(p) for p in args.results]},
                                   indent=2, allow_nan=False) + '\n')
