"""A3: compare own re-evaluation (a2) with the sealed stage-2 result; recompute increases, margins and the primary criterion."""
import json, sys
from pathlib import Path
P = Path('/tmp/mc-lfw-b2-crossfeed-20261026-r1').resolve(); A = Path(sys.argv[1])
s2 = json.loads((P / 'out/stage2_result.json').read_text()); me = json.loads((A / 'results/a2_reeval.json').read_text())
LIM = {'rms': .20, 'p95': .40, 'max': .80}; MARG = 0.01313142874082845 * .885
CASES = ['noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional', 'flat', 'repeated']
gate = lambda m: 'PASS' if all(m[k] <= LIM[k] for k in LIM) else 'FAIL'
R = {}
dn = max(abs(me['native'][k][f][m] - s2['native'][k][f][m]) for k in me['native'] for f in ('runtime', 'STAR') for m in LIM)
do = {k: max(abs(me['offline'][k]['angstrom'][m] - s2['offline'][k]['angstrom'][m]) for m in LIM) for k in me['offline']}
R['max_abs_diff_native_A'] = dn; R['max_abs_diff_offline_A'] = max(do.values()); R['offline_entries_compared'] = len(do)
R['gate_disagreements'] = [k for k in me['offline'] if me['offline'][k]['gate'] != s2['offline'][k]['gate']]
R['missing_in_stage2'] = [k for k in me['offline'] if k not in s2['offline']]
# local-disabled cases: stage2 copies native fields
R['local_disabled_stage2_equals_native'] = all(s2['offline'][f'{c}/{a}/{fi}/R_{g}']['angstrom'] == s2['native'][f'{c}/{a}']['runtime' if g == 'rt' else 'STAR'] for c in CASES[3:] for a in ('OFF', 'ON') for fi in ('legacy', 'B2') for g in ('rt', 'hyb'))
R['local_disabled_npatch_zero'] = {f'{c}/{a}': me['native'][f'{c}/{a}']['n_patches'] == 0 and not me['native'][f'{c}/{a}']['local_enabled'] for c in CASES[3:] for a in ('OFF', 'ON')}
# full B2+full-width row, own numbers
tab = {}
for c in CASES:
    for g, nat in (('rt', 'runtime'), ('hyb', 'STAR')):
        b2 = me['offline'][f'{c}/ON/B2/R_{g}']['angstrom'] if c in ('noisy', 'affine', 'pedestal') else me['native'][f'{c}/ON'][nat]
        tab[f'{c}/R_{g}'] = {'B2_ON': b2, 'gate': gate(b2), 'native_ON': me['native'][f'{c}/ON'][nat], 'native_OFF': me['native'][f'{c}/OFF'][nat]}
R['B2_fullwidth_table'] = tab
R['primary_six_pass_both'] = all(tab[f'{c}/R_{g}']['gate'] == 'PASS' for c in CASES[:6] for g in ('rt', 'hyb'))
R['five_retained'] = {f'{c}/R_{g}': tab[f'{c}/R_{g}']['gate'] for c in ('affine', 'pedestal', 'zero', 'integer', 'fractional') for g in ('rt', 'hyb')}
R['noisy_fail_each_limit'] = {g: {k: tab[f'noisy/R_{g}']['B2_ON'][k] > LIM[k] for k in LIM} for g in ('rt', 'hyb')}
inc, ties = [], []
for key, t in tab.items():
    for ref in ('native_ON', 'native_OFF'):
        for k in LIM:
            if t['B2_ON'][k] > t[ref][k]: inc.append([key, ref, k, t[ref][k], t['B2_ON'][k], gate(t[ref]) + '->' + t['gate']])
            elif t['B2_ON'][k] == t[ref][k] and key.split('/')[0] in ('noisy', 'affine', 'pedestal'): ties.append([key, ref, k])
R['own_increases'] = inc; R['own_ties_local_cases'] = ties
R['stage2_increases'] = [[i['case'], i['field'], i['metric'], i['versus'], i['native'], i['B2_fullwidth'], i['gate_transition']] for i in s2['increases_B2_fullwidth']]
R['increase_count_match'] = len(inc) == len(s2['increases_B2_fullwidth'])
R['margin_sensitive_B2_ON'] = {k: [m for m in LIM if abs(v['B2_ON'][m] - LIM[m]) <= MARG] for k, v in tab.items() if any(abs(v['B2_ON'][m] - LIM[m]) <= MARG for m in LIM)}
R['margin_sensitive_any_offline'] = {k: v['margin_sensitive'] for k, v in me['offline'].items() if v['margin_sensitive']}
R['margin_sensitive_any_native'] = {f'{k}/{f}': [m for m in LIM if abs(v[f][m] - LIM[m]) <= MARG] for k, v in me['native'].items() for f in ('runtime', 'STAR') if any(abs(v[f][m] - LIM[m]) <= MARG for m in LIM)}
R['closest_B2_ON_distance_to_limit_A'] = min((abs(v['B2_ON'][m] - LIM[m]), k, m) for k, v in tab.items() for m in LIM if k.split('/')[0] not in ('flat', 'repeated'))
R['stage2_status'] = s2['status']; R['stage2_control_ok'] = s2['control_ok']
R['directional_noisy_own'] = {g: {k: [tab[f'noisy/R_{g}']['native_ON'][k], tab[f'noisy/R_{g}']['B2_ON'][k]] for k in LIM} for g in ('rt', 'hyb')}
R['flat_repeated_native'] = {k: me['native'][k] for k in ('flat/OFF', 'flat/ON', 'repeated/OFF', 'repeated/ON')}
R['flat_repeated_stage2_labels'] = {k: v for k, v in s2.items() if 'flat' in json.dumps(k)}
# B2 vs legacy at OFF/ON for local cases, own numbers
R['local_grid_own'] = {k: [round(v['angstrom'][m], 6) for m in LIM] + [v['gate']] for k, v in me['offline'].items()}
R['control_stage2'] = s2['control']
json.dump(R, sys.stdout, indent=1, default=str); print()
