#!/usr/bin/env python3
"""Score the H6 arms against the frozen predictions. usage: analyze_h6.py RESULTS_DIR OUT_PREFIX
Control: DCg+H2g (dcgh2g-prod-rt / dcgh2g-long-rt from the H4 round, reused). STAR = eval_v2, runtime = eval_runtime_v2.
"""
import json, pathlib, re, sys
R = pathlib.Path(sys.argv[1]); out = sys.argv[2]
CASES = ['zero', 'integer', 'fractional', 'affine', 'pedestal', 'noisy', 'flat', 'repeated']
ARMS = {'DCg+H2g (control)': ('dcgh2g-prod-rt', 'dcgh2g-long-rt'), 'DCb+H2a': ('dcbh2a-prod', 'dcbh2a-long'),
        'DCb+H2g': ('dcbh2g-prod', 'dcbh2g-long'), 'DCg+H2a': ('dcgh2a-prod', 'dcgh2a-long')}
def load(n):
    st = {r['case']: r for r in json.loads((R/'v2'/f'{n}.eval.json').read_text())}
    rt = {r['case']: r for r in json.loads((R/'v2'/f'{n}.runtime-eval.json').read_text())}
    return st, rt
data = {(a, stop): load(ARMS[a][i]) for a in ARMS for i, stop in enumerate(('prod', 'long'))}
m3 = lambda m: (m['rms'], m['p95'], m['max'])
f = lambda m: f"{m['rms']:.4f} / {m['p95']:.4f} / {m['max']:.4f}"
L = []
for stop in ('prod', 'long'):
    L += [f'### {"Production stop (5 iterations / 0.5 px)" if stop == "prod" else "50 iterations / 1e-9"}', '',
          '| Case | ' + ' | '.join(ARMS) + ' |', '|---|' + '---|'*len(ARMS)]
    for c in CASES:
        cells = []
        for a in ARMS:
            st, rt = data[(a, stop)]
            cells.append(f"runtime {f(rt[c]['field_angstrom'])} {rt[c]['runtime_gate']}<br>STAR {f(st[c]['field_angstrom'])} {st[c]['checker_status']}")
        L.append(f'| {c} | ' + ' | '.join(cells) + ' |')
    L.append('')
open(out + '_arm_table.md', 'w').write('\n'.join(L) + '\n')
ctl = 'DCg+H2g (control)'
# regressions vs control (any increase in rms/p95/max, runtime or STAR, no threshold)
regs = []
for a in ARMS:
    if a == ctl: continue
    for stop in ('prod', 'long'):
        for c in CASES:
            for rep, idx in (('runtime', 1), ('STAR', 0)):
                x = data[(a, stop)][idx][c]['field_angstrom']; y = data[(ctl, stop)][idx][c]['field_angstrom']
                up = [k for k in ('rms', 'p95', 'max') if x[k] > y[k]*(1+1e-9) + 1e-12]
                if up:
                    gate = 'runtime_gate' if rep == 'runtime' else 'field_gate'
                    regs.append(dict(arm=a, stop=stop, case=c, rep=rep, increased=up, control=[y[k] for k in ('rms', 'p95', 'max')], arm_values=[x[k] for k in ('rms', 'p95', 'max')],
                                     control_gate=data[(ctl, stop)][idx][c][gate], arm_gate=data[(a, stop)][idx][c][gate]))
# prediction 3: integer/fractional identical to control, every arm, both stops, both representations
p3 = {}
for a in ARMS:
    if a == ctl: continue
    for stop in ('prod', 'long'):
        for c in ('integer', 'fractional'):
            for rep, idx in (('runtime', 1), ('STAR', 0)):
                p3[f'{a}|{stop}|{c}|{rep}'] = data[(a, stop)][idx][c]['field_angstrom'] == data[(ctl, stop)][idx][c]['field_angstrom']
# prediction 2
def ped(a, stop, idx): return data[(a, stop)][idx]['pedestal']['field_angstrom']
p2 = {}
for stop in ('prod', 'long'):
    for rep, idx in (('runtime', 1), ('STAR', 0)):
        c0, ab, gb = ped(ctl, stop, idx), ped('DCb+H2a', stop, idx), ped('DCb+H2g', stop, idx)
        p2[f'{stop}|{rep}'] = dict(control=m3(c0), dcb_h2a=m3(ab), dcb_h2g=m3(gb), dcg_h2a=m3(ped('DCg+H2a', stop, idx)),
                                   lower_rms=ab['rms'] < c0['rms'], share_of_improvement_by_patch_dc=((c0['rms'] - gb['rms'])/(c0['rms'] - ab['rms'])) if c0['rms'] != ab['rms'] else None)
# prediction 4
p4 = {rep: dict(prod=dict(zip(('rms', 'p95', 'max'), m3(data[('DCb+H2a', 'prod')][idx]['affine']['field_angstrom'])), verdict=data[('DCb+H2a', 'prod')][idx]['affine']['runtime_gate' if rep == 'runtime' else 'checker_status']),
              control=data[(ctl, 'prod')][idx]['affine']['runtime_gate' if rep == 'runtime' else 'checker_status']) for rep, idx in (('runtime', 1), ('STAR', 0))}
# manipulation control and guard counts from each case's stdout; noisy edge patches from noisy.log
def counts(arm):
    tot = dict(global_zeroed=0, global_eligible=0, local_zeroed=0, local_eligible=0); g = dict(global_=[0, 0], patch=[0, 0]); dcarm = set()
    for c in CASES:
        t = (R/'v2'/arm/f'{c}.stdout').read_text()
        m = re.search(r'MC_EXPERIMENT_CCF_DC arm=(\w+) cpu.global=(\d+)/(\d+) cpu.local=(\d+)/(\d+)', t)
        dcarm.add(m.group(1)); tot['global_zeroed'] += int(m.group(2)); tot['global_eligible'] += int(m.group(3)); tot['local_zeroed'] += int(m.group(4)); tot['local_eligible'] += int(m.group(5))
        for sc, pk, fired in re.findall(r'\[coupled_peak\] scope=(\w+) peaks=(\d+) guard_fired=(\d+)', t):
            k = 'global_' if sc == 'global' else 'patch'; g[k][0] += int(fired); g[k][1] += int(pk)
    return dict(dc_arm=sorted(dcarm), **tot, guard_fired_over_peaks=dict(global_=g['global_'], patch=g['patch']))
manip = {}
for a in ARMS:
    for i, stop in enumerate(('prod', 'long')):
        manip[f'{a}|{stop}'] = counts(ARMS[a][i])
def edge(arm):
    log = (R/'v2'/arm/'noisy'/'noisy.log').read_text().splitlines(); after = False; label = None; pat = {}
    for ln in log:
        if ln.startswith('Patches:'): after = True; continue
        if not after: continue
        m = re.match(r'Patch \((\d+), (\d+)\):', ln)
        if m: label = f'{m.group(1)},{m.group(2)}'; pat[label] = []; continue
        m = re.match(r'\s*Iteration (\d+): RMSD = (\S+) px', ln)
        if m and label: pat[label].append(float(m.group(2)))
    return {k: dict(iterations=len(v), last_rmsd=v[-1] if v else None, converged=bool(v and v[-1] < 0.5)) for k, v in pat.items()}
edges = {f'{a}|{stop}': edge(ARMS[a][i]) for a in ARMS for i, stop in enumerate(('prod', 'long'))}
res = dict(prediction_2=p2, prediction_3=dict(all_identical=all(p3.values()), cells=p3), prediction_4=p4, regressions_vs_control=regs, manipulation=manip, noisy_patch_convergence=edges)
pathlib.Path(out + '.json').write_text(json.dumps(res, indent=1, allow_nan=False) + '\n')
print('P2', json.dumps(p2, indent=1)); print('P3 all identical:', all(p3.values()), [k for k, v in p3.items() if not v]); print('P4', json.dumps(p4))
print('manipulation:'); [print(' ', k, v) for k, v in manip.items()]
print('noisy edge patches (1,3),(2,3):'); [print(' ', k, {p: (edges[k][p]['converged'], edges[k][p]['iterations'], round(edges[k][p]['last_rmsd'], 2)) for p in ('1,3', '2,3')}) for k in edges]
print('regressions:', len(regs))
