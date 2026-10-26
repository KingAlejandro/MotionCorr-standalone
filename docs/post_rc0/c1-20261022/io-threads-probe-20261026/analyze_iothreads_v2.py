#!/usr/bin/env python3
"""Analysis v2 (26 Oct 2026, after parent review): applies the frozen plan's eligibility rule that analyze_iothreads.py (v1, retained unchanged) did not apply.
Plan rule: a run carrying a discard flag loses its timing claim. The in-series baseline profile sample P-c6 is flagged (foreign CPU on the payload lane, 0.35 cores), so it
cannot serve as the reference of the phase contrast (c) or of the combined hypothesis H, and full 1/2/4/6 monotonicity cannot be assessed. No rule is rewritten; no rerun.
usage: analyze_iothreads_v2.py evidence iothreads-results.json OUT.json   (reads the retained raw evidence and the v1 output)"""
import json, sys
from pathlib import Path
E = Path(sys.argv[1]); v1 = json.load(open(sys.argv[2]))
R = {r['tag']: r for r in (json.loads(l) for l in open(E / 'work/runs.jsonl'))}
flagged = {tag: r['flags']['discard'] for tag, r in R.items() if r['flags']['discard']}
out = {'schema': 'iothreads-analysis/2', 'supersedes_interpretation_of': 'iothreads-results.json (v1, retained; its H_supported and read_phase_monotone_1_2_4_6 fields used the flagged P-c6 sample and are not valid)',
       'flagged_runs': flagged, 'unflagged_runs': sorted(set(R) - set(flagged))}
# clean unprofiled ABBA effects: (a) repeat side and (b) deviation vs the largest observed AA; none of these runs is flagged
eff = {}
for c, v in v1['variants'].items():
    runs = {'c1': ('T02-c1', 'T03-c1', 'T01-c6', 'T04-c6'), 'c2': ('T06-c2', 'T07-c2', 'T05-c6', 'T08-c6'), 'c4': ('T10-c4', 'T11-c4', 'T09-c6', 'T12-c6')}[c]
    eff[c] = {'runs_flagged': [t for t in runs if t in flagged], 'mean_wall_s': v['mean_wall_s'], 'block_baseline_mean_s': v['block_baseline_mean_s'], 'pair_ratio': v['pair_ratio'],
              'deviation_pct': round(v['deviation_pct'], 1), 'repeat_side_both_runs_vs_both_adjacent_baselines': v['both_runs_same_side_of_both_adjacent_baselines'],
              'exceeds_max_observed_AA': v['exceeds_max_AA']}
out['unprofiled_whole_job_effects'] = {'status': 'REPORTED (criteria (a) repeat side and (b) deviation > observed AA satisfied for caps 1, 2, 4; no run flagged)',
                                       'observed_AA_max_pct': round(v1['aa_max_pct'], 2), 'observed_AA_pct': {k: round(x, 2) for k, x in v1['aa_pct'].items()}, 'variants': eff}
prof = v1['profile_samples']
out['profile_samples'] = {c: {'flagged': p['flagged'], 'read_wall_ms': p['read_wall_ms'], 'read_share': round(p['read_share'], 3)} for c, p in prof.items()}
clean = {c: p['read_wall_ms'] for c, p in prof.items() if not p['flagged']}
out['phase_descriptive_unflagged_caps_1_2_4'] = {'read_wall_ms': {c: clean[c] for c in ('1', '2', '4')}, 'monotone_among_themselves': clean['1'] >= clean['2'] >= clean['4'],
                                                 'note': 'descriptive single samples; not a contrast against a baseline'}
out['phase_comparison_with_cap6_baseline'] = 'UNASSESSED: the in-series baseline profile sample (P-c6) is flagged and lost its timing claim; full 1/2/4/6 monotonicity is unassessed'
out['posthoc_context_only'] = {'earlier_window_baseline_P1_read_ms': 1313.183594,
                               'label': 'post hoc context from another measurement window (same configuration, unflagged); NOT a replacement primary measurement and not part of the frozen rule',
                               'ratios_of_caps_1_2_4_read_phase_to_it': {c: round(clean[c] / 1313.183594, 2) for c in ('1', '2', '4')}}
out['combined_hypothesis_H'] = {'verdict': 'INCONCLUSIVE', 'reason': 'criterion (c), the read-phase contrast against the baseline profile sample, has a flagged reference (P-c6); (a) and (b) alone are met by the unprofiled runs',
                                'v1_H_supported_withdrawn': True}
out['checks'] = {'failures_in_17_processes': len(v1['checks_failures'])}
out['unrun'] = ['cold cache', 'other formats and routes', 'worker layouts', 'caps above 6', 'a clean baseline profile sample (not rerun: the plan forbids reruns to obtain a pass)']
Path(sys.argv[3]).write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps({k: out[k] for k in ('combined_hypothesis_H', 'phase_comparison_with_cap6_baseline', 'phase_descriptive_unflagged_caps_1_2_4')}, indent=1))
print({c: (e['deviation_pct'], e['repeat_side_both_runs_vs_both_adjacent_baselines'], e['exceeds_max_observed_AA']) for c, e in eff.items()}, out['unprofiled_whole_job_effects']['observed_AA_max_pct'])
