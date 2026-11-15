#!/usr/bin/env python3
"""Score the native N-control runs with the W5 convention (reused code: common.score / common.field / common.rms, ROI y[12:84] x[12:116],
0.885 A/px, frame-zero gauge, limits 0.20/0.40/0.80 A), runtime (MC_DIAG_MODEL_OUT) and STAR separately; compare with the W6 offline replays.
usage: score_ncontrols.py ROOT SRC_ROOT W6_JSON OUT_PREFIX
"""
import json, pathlib, re, sys
import numpy as np
root, src, w6path, outp = (pathlib.Path(a).resolve() for a in sys.argv[1:5])
W5 = pathlib.Path('/tmp/motioncorr-w5-20261025-7b76b848')
sys.path[:0] = [str(W5/'scripts'), str(src/'tools')]
import common as C
from motion_field import read_motion_star
w6 = json.loads(w6path.read_text())['probes']
runs = json.loads((root/'runs/runs.json').read_text())
ARM6 = {'a': 'S-P', 'DCg': 'S-D', 'H2g': 'H-P', 'DCg+H2g': 'H-D'}
rows = []
for r in runs:
    run = root/'runs'/r['tag']; name = r['movie']; N = int(name.split('N')[1]); iv = int(name[3])
    tt = np.load(root/'movies'/f'{name}_truth.npy'); truth = np.broadcast_to(tt[:, None, None], (N, C.NY, C.NX, 2))
    st = read_motion_star(run/name/f'{name}.star'); gS = np.stack((st.global_shift_x, st.global_shift_y), axis=-1)
    rt = json.loads((run/f'{name}.runtime.json').read_text()); gR = np.array(rt['global'])
    row = dict(r, N=N, vel=iv, exit_ok=(r['exit'] == 0))
    for lab, g in (('runtime', gR), ('STAR', gS)):
        row[lab] = C.score(C.field(g), truth)
        row['traj_rms_px_'+lab] = float(C.rms(g - tt))
    row['runtime_minus_STAR_max_px'] = float(np.abs(gR - gS).max())
    txt = (run/f'{name}.stdout').read_text()
    m = re.search(r'\[align\] scope=global iterations=(\d+) max_iter=(\d+) converged=(\d) last_rmsd_px=(\S+)', txt)
    row['iterations'] = int(m.group(1)) if m else None; row['converged'] = bool(int(m.group(3))) if m else None
    g = re.search(r'\[coupled_peak\] scope=global peaks=(\d+) guard_fired=(\d+) \(not_negative_definite=(\d+), offset_gt_1px=(\d+)\)', txt)
    row['guard'] = dict(peaks=int(g.group(1)), fired=int(g.group(2)), not_negative_definite=int(g.group(3)), offset_gt_1px=int(g.group(4))) if g else None
    d = re.search(r'MC_EXPERIMENT_CCF_DC arm=(\w+) cpu.global=(\d+)/(\d+) cpu.local=(\d+)/(\d+)', txt)
    row['dc'] = dict(arm=d.group(1), global_zeroed=int(d.group(2)), global_eligible=int(d.group(3)), local_zeroed=int(d.group(4)), local_eligible=int(d.group(5))) if d else None
    it = 5 if r['stop'] == 'prod' else 50
    row['w6'] = {dom: dict(runtime=w6[f"vel{iv}-N{N}-{r['weight']}-{dom}-{ARM6[r['arm']]}-{it}it"]['runtime'],
                           STAR=w6[f"vel{iv}-N{N}-{r['weight']}-{dom}-{ARM6[r['arm']]}-{it}it"]['STAR'],
                           traj_rms_px=w6[f"vel{iv}-N{N}-{r['weight']}-{dom}-{ARM6[r['arm']]}-{it}it"]['trajectory_error_px']['rms']) for dom in ('double', 'map32')}
    rows.append(row)
key = lambda r: (r['movie'], r['weight'], r['stop'])
by = {}
for r in rows: by.setdefault(key(r), {})[r['arm']] = r
ARMS = ['a', 'DCg', 'H2g', 'DCg+H2g']
# regressions vs a
regs = []
for k, d in by.items():
    for arm in ARMS[1:]:
        for rep in ('runtime', 'STAR'):
            up = [m for m in ('rms', 'p95', 'max') if d[arm][rep][m] > d['a'][rep][m]*(1+1e-9) + 1e-12]
            if up: regs.append(dict(movie=k[0], weight=k[1], stop=k[2], arm=arm, representation=rep, increased=up,
                                    a=[d['a'][rep][m] for m in ('rms', 'p95', 'max')], arm_values=[d[arm][rep][m] for m in ('rms', 'p95', 'max')],
                                    a_verdict=d['a'][rep]['verdict'], arm_verdict=d[arm][rep]['verdict']))
# predictions
p3 = []
for k, d in by.items():
    N = int(k[0].split('N')[1])
    if N in (9, 13, 20):
        base_pass = [rep for rep in ('runtime', 'STAR') if d['a'][rep]['verdict'] == 'PASS']
        cand_fail = [rep for rep in ('runtime', 'STAR') if d['DCg+H2g'][rep]['verdict'] == 'FAIL']
        if base_pass and cand_fail: p3.append(dict(movie=k[0], weight=k[1], stop=k[2], a_pass_in=base_pass, dcgh2g_fail_in=cand_fail,
                                                    a=d['a']['runtime'], dcgh2g=d['DCg+H2g']['runtime']))
n_base_pass = sum(1 for k, d in by.items() if int(k[0].split('N')[1]) in (9, 13, 20) and any(d['a'][rep]['verdict'] == 'PASS' for rep in ('runtime', 'STAR')))
h = by[('vel1_N20', 'iso', 'prod')]; h50 = by[('vel1_N20', 'iso', 'long')]
p4 = dict(a_traj_rms_px=h['a']['traj_rms_px_runtime'], dcgh2g_traj_rms_px=h['DCg+H2g']['traj_rms_px_runtime'],
          holds=h['DCg+H2g']['traj_rms_px_runtime'] <= h['a']['traj_rms_px_runtime'] + 1e-6)
harm = {f'{stop}': {arm: dict(runtime=by[('vel1_N20', 'iso', stop)][arm]['runtime'], STAR=by[('vel1_N20', 'iso', stop)][arm]['STAR'],
                              traj_rms_px=by[('vel1_N20', 'iso', stop)][arm]['traj_rms_px_runtime'],
                              w6_double=by[('vel1_N20', 'iso', stop)][arm]['w6']['double']['runtime'], w6_map32=by[('vel1_N20', 'iso', stop)][arm]['w6']['map32']['runtime'])
                    for arm in ARMS} for stop in ('prod', 'long')}
agree = {dom: {arm: sum(1 for r in rows if r['arm'] == arm and r['runtime']['verdict'] == r['w6'][dom]['runtime']['verdict']) for arm in ARMS} for dom in ('double', 'map32')}
tot = {arm: sum(1 for r in rows if r['arm'] == arm) for arm in ARMS}
agree_star = {dom: {arm: sum(1 for r in rows if r['arm'] == arm and r['STAR']['verdict'] == r['w6'][dom]['STAR']['verdict']) for arm in ARMS} for dom in ('double', 'map32')}
n5 = [dict(movie=k[0], weight=k[1], stop=k[2], runtime=d['DCg+H2g']['runtime']['verdict'], STAR=d['DCg+H2g']['STAR']['verdict']) for k, d in by.items() if k[0].endswith('N5')]
p6 = all(x['runtime'] == 'PASS' and x['STAR'] == 'PASS' for x in n5)
passes = {stop: {arm: sum(1 for r in rows if r['arm'] == arm and r['stop'] == stop and r['runtime']['verdict'] == 'PASS' and r['STAR']['verdict'] == 'PASS') for arm in ARMS} for stop in ('prod', 'long')}
summary = dict(n_rows=len(rows), nonzero_exit_rows=[r['tag']+'/'+r['movie'] for r in rows if not r['exit_ok']], p3_violations=p3, p3_baseline_pass_cells=n_base_pass, p4=p4,
               harmful=harm, verdict_agreement_runtime=agree, verdict_agreement_star=agree_star, rows_per_arm=tot, p6_all_n5_pass=p6, n5=n5, pass_counts_runtime_and_star=passes,
               max_runtime_minus_star_px=max(r['runtime_minus_STAR_max_px'] for r in rows), regressions=regs)
pathlib.Path(str(outp)+'.json').write_text(json.dumps(dict(summary=summary, rows=rows), indent=1, allow_nan=False)+'\n')
f = lambda m: f"{m['rms']:.3f}/{m['p95']:.3f}/{m['max']:.3f} {m['verdict']}"
L = ['| Control | Stop | a | DCg | H2g | DCg+H2g |', '|---|---|---|---|---|---|']
for wt in ('prod', 'iso'):
    for iv in (0, 1):
        for N in (5, 9, 13, 20):
            for stop in ('prod', 'long'):
                d = by[(f'vel{iv}_N{N}', wt, stop)]
                cells = []
                for arm in ARMS:
                    r = d[arm]; flag = '' if r['runtime']['verdict'] == r['STAR']['verdict'] else f" (STAR {r['STAR']['verdict']})"
                    cells.append(f(r['runtime']) + flag)
                L.append(f"| vel{iv}-N{N}-{wt} | {stop} | " + ' | '.join(cells) + ' |')
pathlib.Path(str(outp)+'.md').write_text('\n'.join(L)+'\n')
print(json.dumps({k: summary[k] for k in ('n_rows', 'nonzero_exit_rows', 'p3_baseline_pass_cells', 'p4', 'p6_all_n5_pass', 'pass_counts_runtime_and_star', 'verdict_agreement_runtime', 'rows_per_arm', 'max_runtime_minus_star_px')}, indent=1))
print('P3 violations:', len(p3), '; regressions listed:', len(regs))
