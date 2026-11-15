#!/usr/bin/env python3
"""Arm table from the retained eval JSONs. usage: summarize.py V2DIR FROZEN_F_EVAL.json OUT_PREFIX [ARM ...]
Scores are the unchanged eval_v2.py/#267 checker outputs: STAR-serialized field, fixed ROI, limits .20/.40/.80 A.
"""
import json, pathlib, sys
v2, frozen, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
ARMS = sys.argv[4:] or ['a0-base-flagsoff', 'a-cand-flagsoff', 'b-half-prod', 'c-half-long', 'd-gain1-long']
CASES = ['zero', 'integer', 'fractional', 'affine', 'pedestal', 'noisy', 'flat', 'repeated']
ev = {a: {r['case']: r for r in json.loads((v2/f'{a}.eval.json').read_text())} for a in ARMS if (v2/f'{a}.eval.json').exists()}
fz = {r['case']: r for r in json.loads(frozen.read_text())}
m = lambda r: (r['field_angstrom']['rms'], r['field_angstrom']['p95'], r['field_angstrom']['max'])
def status(r): return r['checker_status']
lines, summary = [], {}
for a in ev:
    c = {}
    for r in ev[a].values(): c[status(r)] = c.get(status(r), 0) + 1
    gates = sum(r['field_gate'] == 'PASS' for r in ev[a].values())
    summary[a] = dict(checker_counts=c, field_gate_pass=gates, native_exits=[r['native_exit'] for r in ev[a].values()])
lines.append('| Arm | checker PASS / FAIL / UNIDENTIFIABLE / other | field-gate PASS (of 8) | native exits |')
lines.append('|---|---|---|---|')
for a, s in summary.items():
    c = s['checker_counts']; other = {k: v for k, v in c.items() if k not in ('PASS', 'FAIL', 'UNIDENTIFIABLE')}
    lines.append(f"| {a} | {c.get('PASS',0)} / {c.get('FAIL',0)} / {c.get('UNIDENTIFIABLE',0)} / {other or 0} | {s['field_gate_pass']} | {s['native_exits']} |")
lines += ['', '| Case | ' + ' | '.join(ev) + ' |', '|---|' + '---|' * len(ev)]
for case in CASES:
    cells = []
    for a in ev:
        r = ev[a][case]; x = m(r)
        cells.append(f"{status(r)}/{r['field_gate']} {x[0]:.6f} / {x[1]:.6f} / {x[2]:.6f}")
    lines.append(f'| {case} | ' + ' | '.join(cells) + ' |')
checks = {}
if 'a-cand-flagsoff' in ev and 'a0-base-flagsoff' in ev:
    checks['a_vs_a0_field_exact'] = all(ev['a-cand-flagsoff'][c]['field_angstrom'] == ev['a0-base-flagsoff'][c]['field_angstrom'] and ev['a-cand-flagsoff'][c]['field_px'] == ev['a0-base-flagsoff'][c]['field_px'] for c in CASES)
    checks['a_vs_a0_status_equal'] = all(status(ev['a-cand-flagsoff'][c]) == status(ev['a0-base-flagsoff'][c]) for c in CASES)
if 'a-cand-flagsoff' in ev:
    d = {c: max(abs(x - y) for x, y in zip(m(ev['a-cand-flagsoff'][c]), m(fz[c]))) for c in CASES}
    checks['a_vs_frozenF_evidence_max_abs_diff_A'] = d
    checks['a_vs_frozenF_evidence_exact'] = all(v == 0 for v in d.values())
(pathlib.Path(out + '.md')).write_text('\n'.join(lines) + '\n')
(pathlib.Path(out + '.json')).write_text(json.dumps(dict(summary=summary, checks=checks), indent=1) + '\n')
print('\n'.join(lines)); print(json.dumps(checks, indent=1))
