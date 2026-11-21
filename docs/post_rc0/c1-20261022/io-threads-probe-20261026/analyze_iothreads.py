#!/usr/bin/env python3
"""Analysis of the IO-thread probe per IO_THREADS_PLAN.md (stdlib only). usage: analyze_iothreads.py evidence OUT.json"""
import json, sys
from pathlib import Path
E = Path(sys.argv[1])
R = {r['tag']: r for r in (json.loads(l) for l in open(E / 'work/runs.jsonl'))}
C = json.load(open(E / 'work/checks.json'))['checks']
t = {k: v['wall_s'] for k, v in R.items()}
pct = lambda a, b: 100 * abs(a - b) / ((a + b) / 2)
out = {'timed': {k: {'cap': v['cap'], 'wall_s': v['wall_s'], 'cpu_s': v['cpu_s'], 'peak_rss_gib': v['peak_rss_bytes'] / 2**30, 'flags': v['flags']['discard']} for k, v in R.items() if v['kind'] != 'profile'}}
aa = {'B(T04,T05)': pct(t['T04-c6'], t['T05-c6']), 'B(T08,T09)': pct(t['T08-c6'], t['T09-c6']), 'c1': pct(t['T02-c1'], t['T03-c1']),
      'c2': pct(t['T06-c2'], t['T07-c2']), 'c4': pct(t['T10-c4'], t['T11-c4'])}
out['aa_pct'] = aa; out['aa_max_pct'] = max(aa.values())
Bs = [t[k] for k in t if k.startswith('T') and k.endswith('c6')]
out['baseline_timed'] = {'walls': Bs, 'min': min(Bs), 'max': max(Bs), 'range_pct_of_min': 100 * (max(Bs) - min(Bs)) / min(Bs)}
blocks = {'c1': ('T02-c1', 'T03-c1', 'T01-c6', 'T04-c6'), 'c2': ('T06-c2', 'T07-c2', 'T05-c6', 'T08-c6'), 'c4': ('T10-c4', 'T11-c4', 'T09-c6', 'T12-c6')}
prof = {}
for cap in ('1', '2', '4', '6'):
    tag = 'P-c' + cap
    L = [json.loads(l) for l in open(E / 'work/runs' / tag / 'profile.jsonl')]
    m = [x for x in L if x['type'] == 'movie'][0]; p = [x for x in L if x['type'] == 'process'][0]
    st = {s['name']: s for s in m['stages']}
    prof[cap] = {'flagged': R[tag]['flags']['discard'], 'process_wall_s_kit': R[tag]['wall_s'], 'movie_wall_ms': m['wall_ms'], 'run_wall_ms': p['run_wall_ms'],
                 'read_wall_ms': st['host read movie']['wall_ms'], 'read_cpu_ms_main_thread': st['host read movie']['cpu_ms'], 'read_minflt_main_thread': st['host read movie']['minflt'],
                 'read_share': st['host read movie']['wall_ms'] / m['wall_ms'], 'gain_and_sum_ms': st['gain and sum']['wall_ms'], 'teardown_ms': st['movie teardown']['wall_ms'],
                 'unweighted_sums_ms': st['unweighted sums']['wall_ms'], 'process_minflt': p['process_minflt'], 'process_cpu_ms': p['process_cpu_ms']}
out['profile_samples'] = prof
ref_read = 1313.183594   # earlier baseline-profile P1 read phase (other window, same configuration), used only as a bridge if P-c6 is flagged
res = {}
for c, (a, b, pre, post) in blocks.items():
    m = (t[a] + t[b]) / 2; bm = (t[pre] + t[post]) / 2
    same = all(t[x] > t[y] for x in (a, b) for y in (pre, post)) or all(t[x] < t[y] for x in (a, b) for y in (pre, post))
    cap = c[1:]
    rd = prof[cap]['read_wall_ms']; rb = prof['6']['read_wall_ms']
    res[c] = {'mean_wall_s': m, 'block_baseline_mean_s': bm, 'pair_ratio': m / bm, 'deviation_pct': 100 * (m / bm - 1), 'both_runs_same_side_of_both_adjacent_baselines': same,
              'exceeds_max_AA': abs(100 * (m / bm - 1)) > out['aa_max_pct'],
              'read_phase_ms_profile_sample': rd, 'read_phase_baseline_profile_sample_ms': rb, 'read_phase_ratio_vs_in_series_baseline_sample': rd / rb,
              'read_phase_ratio_vs_earlier_window_P1': rd / ref_read, 'phase_direction_same_as_wall': (rd > rb) == (m > bm)}
    res[c]['H_supported'] = bool(res[c]['both_runs_same_side_of_both_adjacent_baselines'] and res[c]['exceeds_max_AA'] and res[c]['phase_direction_same_as_wall'])
out['variants'] = res
rm = [prof[c]['read_wall_ms'] for c in ('1', '2', '4', '6')]
out['read_phase_monotone_1_2_4_6'] = all(rm[i] >= rm[i + 1] for i in range(3))
out['checks_failures'] = {k: v for k, v in C.items() if v['rc'] != 0 or v['n_files'] != 14 or not v['mrc_finite'] or not v['mrc_nonconstant'] or v['witness'] != ['movie.mrcs float'] or not v['identity_vs_T01']['identical']}
out['all_17_processes'] = len(R)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str) + '\n')
for k in ('aa_pct', 'aa_max_pct', 'baseline_timed'): print(k, out[k])
for c, v in res.items(): print(c, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()})
for c, v in prof.items(): print(c, {a: (round(b, 1) if isinstance(b, float) else b) for a, b in v.items()})
print('monotone', out['read_phase_monotone_1_2_4_6'], 'check failures', len(out['checks_failures']))
