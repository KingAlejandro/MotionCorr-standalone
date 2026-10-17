#!/usr/bin/env python3
"""Summarise raw/runs.jsonl from paired_driver.py with tools/profiling/lib/stats.py.

usage: analyse.py RUNS_JSONL STATS_PY OUT_DIR

Per (family, comparison): retained pairs are the latest undisturbed attempt of each round
(a pair is disturbed when either run had foreign load above 0.25 core on the lane or a
settle timeout). d = B - A in seconds (null: second - first, both A). The verdict comes
from stats.paired (95 % sign-test CI of the median excludes 0 and |median| > noise); the
GO test additionally requires |median| > null_max, where null_max is the largest |d| of the
family's AA null pairs.
"""
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

runs_path, stats_path, out_dir = sys.argv[1:4]
spec = importlib.util.spec_from_file_location('mc_stats', stats_path)
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)

recs = [json.loads(l) for l in Path(runs_path).read_text().splitlines()]
PR = {'179': '#179', '183': '#183'}
FAM_ORDER = ['tutorial', 'e10216', 'e10641', 'e10474f4']


def pair_records(fid, comp):
    """-> (retained pairs, dropped list) for one comparison."""
    by_round = defaultdict(lambda: defaultdict(dict))      # round -> attempt -> pos -> rec
    for r in recs:
        if r['family'] == fid and r['comp'] == comp and r['role'] == 'pair':
            by_round[r['round']][r['attempt']][r['pos']] = r      # later duplicates override
    pairs, dropped = [], []
    for rnd in sorted(by_round):
        good = None
        for att in sorted(by_round[rnd]):
            runs = by_round[rnd][att]
            if len(runs) < 2:
                continue
            first, second = runs[0], runs[1]
            bad = first['flag_foreign'] or second['flag_foreign']
            if bad:
                dropped.append({'round': rnd, 'attempt': att, 'wall_s': [first['wall_s'], second['wall_s']],
                                'foreign_lane_cores': [first['foreign_lane_cores'], second['foreign_lane_cores']]})
            else:
                good = (rnd, att, first, second)
        if good:
            rnd, att, first, second = good
            if comp == 'null':
                a, b, order, ra, rb = first, second, 'AA', first, second
            else:
                ra, rb = (first, second) if first['arm'] == 'A' else (second, first)
                order = 'AB' if first['arm'] == 'A' else 'BA'
            pairs.append({'a': ra['wall_s'], 'b': rb['wall_s'], 'order': order, 'round': rnd, 'attempt': att,
                          'a_cpu': ra['user_s'] + ra['sys_s'], 'b_cpu': rb['user_s'] + rb['sys_s'],
                          'identical': ra['identical'] and rb['identical'],
                          'b_identical': rb['identical']})
    return pairs, dropped


def summarise(fid, comp):
    pairs, dropped = pair_records(fid, comp)
    out = {'family': fid, 'comp': comp, 'n_pairs': len(pairs), 'dropped_disturbed': dropped,
           'pairs': pairs}
    if not pairs:
        return out
    p = stats.paired([{k: x[k] for k in ('a', 'b', 'order')} for x in pairs])
    out['stats'] = {k: p[k] for k in p if k not in ('diffs_s', 'positional')}
    out['diffs_s'] = p['diffs_s']
    out['positional'] = p.get('positional')
    cpu = stats.paired([{'a': x['a_cpu'], 'b': x['b_cpu'], 'order': x['order']} for x in pairs])
    out['cpu_time'] = {k: cpu.get(k) for k in ('median_diff_s', 'relative_median_diff', 'ci', 'resolved', 'verdict')}
    return out


summary = {'families': {}}
rows = []
for fid in FAM_ORDER:
    fam_recs = [r for r in recs if r['family'] == fid]
    if not fam_recs:
        continue
    comps = sorted({r['comp'] for r in fam_recs if r['role'] == 'pair' and r['comp'] != 'null'})
    null = summarise(fid, 'null')
    nd = null.get('diffs_s', [])
    null_max = max((abs(d) for d in nd), default=None)
    fam = {'null': {'n_pairs': null['n_pairs'], 'null_max_s': null_max,
                    'median_diff_s': null.get('stats', {}).get('median_diff_s'),
                    'noise_s': null.get('stats', {}).get('noise_s'),
                    'dropped_disturbed': null['dropped_disturbed'], 'diffs_s': nd}}
    for comp in comps:
        s = summarise(fid, comp)
        st = s.get('stats', {})
        ci = st.get('ci')
        med = st.get('median_diff_s')
        rel = st.get('relative_median_diff')
        enough = s['n_pairs'] >= stats.MIN_PAIRS and null['n_pairs'] >= stats.MIN_PAIRS
        beyond_null = med is not None and null_max is not None and abs(med) > null_max
        resolved_go = bool(st.get('resolved')) and beyond_null and enough
        arm_runs = [r for r in fam_recs if r['arm'] == comp]
        a_runs = [r for r in fam_recs if r['arm'] == 'A']
        s['summary'] = {
            'median_a_s': st.get('median_a_s'), 'median_b_s': st.get('median_b_s'),
            'median_diff_s': med, 'relative_median_diff': rel,
            'ci_s': None if not ci else [ci['low_s'], ci['high_s']], 'ci_confidence': None if not ci else ci['confidence'],
            'noise_s': st.get('noise_s'), 'null_max_s': null_max, 'null_pairs': null['n_pairs'],
            'n_pairs': s['n_pairs'], 'stats_verdict': st.get('verdict'), 'stats_resolved': st.get('resolved'),
            'beyond_null': beyond_null, 'resolved_beyond_null': resolved_go,
            'identical_runs': sum(1 for r in arm_runs if r['identical']), 'total_runs': len(arm_runs),
            'a_identical_runs': sum(1 for r in a_runs if r['identical']), 'a_total_runs': len(a_runs),
            'sign_test': st.get('sign_test'), 'positional': s.get('positional'),
            'cpu_time': s.get('cpu_time'),
            'dropped': len(s['dropped_disturbed']),
            'sensitivity_all_attempts': None,
        }
        # sensitivity: every completed pair attempt, flagged ones included (latest attempt per round)
        alls = defaultdict(dict)
        for r in fam_recs:
            if r['comp'] == comp and r['role'] == 'pair':
                alls[(r['round'], r['attempt'])][r['pos']] = r
        latest = {}
        for (rnd, att), v in alls.items():
            if len(v) == 2 and (rnd not in latest or att > latest[rnd][0]):
                latest[rnd] = (att, v)
        allp = [{'a': (v[0] if v[0]['arm'] == 'A' else v[1])['wall_s'], 'b': (v[1] if v[0]['arm'] == 'A' else v[0])['wall_s'],
                 'order': 'AB' if v[0]['arm'] == 'A' else 'BA'} for _, v in latest.values()]
        if allp:
            q = stats.paired(allp)
            s['summary']['sensitivity_all_attempts'] = {'n': len(allp), 'relative_median_diff': q.get('relative_median_diff'),
                                                        'verdict': q['verdict']}
        fam[comp] = s
    summary['families'][fid] = fam

Path(out_dir).mkdir(parents=True, exist_ok=True)
(Path(out_dir) / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')


def pct(x):
    return 'n/a' if x is None else '%+.2f %%' % (100 * x)


def secs(x):
    return 'n/a' if x is None else '%+.3f' % x


lines = []
for comp in ('179', '183'):
    lines.append('### %s\n' % PR[comp])
    lines.append('| family | pairs | median A (s) | median B (s) | median ΔT (s) | 95 % CI (s) | % change | noise (s) | null_max (s) | stats verdict | beyond null | products identical (B / A runs) |')
    lines.append('|---|---|---|---|---|---|---|---|---|---|---|---|')
    for fid in FAM_ORDER:
        f = summary['families'].get(fid, {}).get(comp)
        if not f:
            continue
        s = f['summary']
        ci = 'n/a' if not s['ci_s'] else '[%+.3f, %+.3f]' % tuple(s['ci_s'])
        lines.append('| %s | %d (+%d null) | %.3f | %.3f | %s | %s | %s | %.3f | %s | %s | %s | %d/%d, %d/%d |' % (
            fid, s['n_pairs'], s['null_pairs'], s['median_a_s'] or 0, s['median_b_s'] or 0, secs(s['median_diff_s']), ci,
            pct(s['relative_median_diff']), s['noise_s'] or 0, 'n/a' if s['null_max_s'] is None else '%.3f' % s['null_max_s'],
            s['stats_verdict'], 'yes' if s['beyond_null'] else 'no',
            s['identical_runs'], s['total_runs'], s['a_identical_runs'], s['a_total_runs']))
    lines.append('')
(Path(out_dir) / 'tables.md').write_text('\n'.join(lines) + '\n')
print('\n'.join(lines))
for fid, fam in summary['families'].items():
    n = fam['null']
    print(fid, 'null: pairs=%d null_max=%s median=%s dropped=%d' % (n['n_pairs'], n['null_max_s'], n['median_diff_s'], len(n['dropped_disturbed'])))
