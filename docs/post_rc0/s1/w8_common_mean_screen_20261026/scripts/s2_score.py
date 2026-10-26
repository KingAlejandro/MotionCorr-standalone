#!/usr/bin/env python3
"""Stage 2 (scoring only): grade B2 + common-mean correction d with the unchanged 4fa272f6 evaluator.

Usage: s2_score.py SRC RUNS REFIT_JSON SCORE_JSON STAGE1_JSON OUTDIR
Order: (1) baseline gate (stored B2 R_rt and native runtime reproduce score.json within 1e-9 A, 68/80 and 22/80
passes); stop on failure with no repair. (2) counterfactual global = G + d. (3) dMS identity check.
(4) fixed screen rules from PLAN.md.
"""
import csv
import json
import sys
from pathlib import Path
import numpy as np

SRC, RUNS, REFIT, SCORE, S1, OUT = map(Path, sys.argv[1:7])
sys.path[:0] = [str(SRC/'tools'), str(SRC/'test-data')]
import check_realistic_motion as ev      # noqa: E402  (unchanged)
import generate_realistic_motion as gen  # noqa: E402  (unchanged)

LIM = dict(rms=.20, p95=.40, max=.80)
INMODEL = ['dose05', 'dose1', 'dose2', 'dose4', 'pedestal0', 'contrast025', 'contrast4', 'nonsquare']
FAIL12 = [f'dose05-s{s:02d}' for s in (0, 1, 2, 3, 4, 6, 8, 9)] + [f'{c}-s00' for c in ('dose1', 'pedestal0', 'contrast025', 'contrast4')]
SEEDS8 = [0, 1, 2, 3, 4, 6, 8, 9]
TOL_BASE_A, TOL_ID_A2 = 1e-9, 1e-10
med = lambda a: float(np.median(a))
fails = lambda m: [k for k in LIM if m[k] > LIM[k]]


def stop(reason, **extra):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'stage2_STOPPED.json').write_text(json.dumps(dict(stopped=reason, **extra), indent=1)+'\n')
    print('STOPPED:', reason); sys.exit(5)


def lattice_error_mean(r, model):
    """Per-frame lattice-mean error vector (px) of the runtime field, computed exactly as evaluate() does."""
    x, y = np.meshgrid(np.linspace(32, r['nx']-33, 129), np.linspace(32, r['ny']-33, 129))
    x, y = x.ravel(), y.ravel()
    truth = -np.stack([gen.displacement(r, f, x, y) for f in range(r['frames'])])
    e = ev.runtime_field(model, r, x, y) - truth
    return e.mean(1), float(np.sqrt(np.mean(np.sum(e*e, -1))))*r['pixel_size']   # (frame, axis), rms in A


def main():
    refit = json.loads(REFIT.read_text()); sc = {m['movie']: m for m in json.loads(SCORE.read_text())['movies']}
    s1 = json.loads(S1.read_text())['movies']
    names = sorted(refit['movies']); assert len(names) == 100 and sorted(sc) == names and sorted(s1) == names
    fitted = [n for n in names if refit['movies'][n]['status'] == 'REFIT_B2']
    assert len(fitted) == 90
    ctx = {}
    # ---- 1. baseline gate
    gate = dict(max_abs_diff_A=0.0, rows=[])
    for n in fitted:
        cond, seed = n.rsplit('-s', 1); r = gen.recipe(cond, int(seed)); rf = refit['movies'][n]
        coeff = dict(coeff_x=rf['coeff_x'], coeff_y=rf['coeff_y'], local_enabled=True)
        model_old = dict(coeff, **{'global': rf['global_runtime']})
        old = ev.evaluate(r, model_old)['field']['angstrom']
        nat = ev.evaluate(r, json.loads((RUNS/n/'F'/'runtime.json').read_text()))['field']['angstrom']
        dif = max(max(abs(old[k]-sc[n]['R_rt'][k]), abs(nat[k]-sc[n]['native_rt'][k])) for k in LIM)
        ebar, rms_chk = lattice_error_mean(r, model_old)
        assert abs(rms_chk-old['rms']) < 1e-12, (n, rms_chk, old['rms'])   # own error field equals evaluate()
        gate['max_abs_diff_A'] = max(gate['max_abs_diff_A'], dif)
        ctx[n] = dict(r=r, coeff=coeff, rf=rf, old=old, nat=nat, ebar=ebar)
    inm = [n for n in fitted if n.rsplit('-s', 1)[0] in INMODEL]; assert len(inm) == 80
    gate.update(inmodel_passes_B2=sum(not fails(ctx[n]['old']) for n in inm), inmodel_passes_native=sum(not fails(ctx[n]['nat']) for n in inm),
                failing_B2=sorted(n for n in inm if fails(ctx[n]['old'])))
    gate['pass'] = (gate['max_abs_diff_A'] <= TOL_BASE_A and gate['inmodel_passes_B2'] == 68 and gate['inmodel_passes_native'] == 22
                    and gate['failing_B2'] == sorted(FAIL12))
    if not gate['pass']:
        stop('baseline gate failed (no scorer repair, no gate adjustment)', gate=gate)
    # ---- 2/3. counterfactual and identity
    rows = []
    for n in fitted:
        c = ctx[n]; r = c['r']; ps = r['pixel_size']
        d = np.array(s1[n]['d']); assert d.shape == (40, 2) and not d[0].any()
        new = ev.evaluate(r, dict(c['coeff'], **{'global': np.asarray(c['rf']['global_runtime'])+d}))['field']['angstrom']
        dms_direct = new['rms']**2 - c['old']['rms']**2
        dms_ident = ps**2*float(np.mean(np.sum(d*d, -1) + 2*np.sum(d*c['ebar'], -1)))
        cond, seed = n.rsplit('-s', 1)
        rows.append(dict(movie=n, condition=cond, seed=int(seed), set='inmodel' if cond in INMODEL else 'outmodel', status='REFIT_B2',
                         native=c['nat'], B2=c['old'], CM=new, dMS_direct_A2=dms_direct, dMS_identity_A2=dms_ident,
                         identity_abs_diff_A2=abs(dms_direct-dms_ident), d_rms_px=s1[n]['d_rms_px']))
    ident = max(x['identity_abs_diff_A2'] for x in rows)
    by = {x['movie']: x for x in rows}
    # ---- 4. fixed screen
    groups = {}
    for s in SEEDS8:
        members = [m for m in FAIL12 if int(m.rsplit('-s', 1)[1]) == s]
        groups[s] = dict(rows=members, mean_dMS_A2=float(np.mean([by[m]['dMS_direct_A2'] for m in members])))
    assert sum(len(g['rows']) for g in groups.values()) == 12
    rule1_median = med([g['mean_dMS_A2'] for g in groups.values()])
    new_fail = [dict(movie=n, B2=by[n]['B2'], CM=by[n]['CM'], newly_failing=[k for k in LIM if by[n]['CM'][k] > LIM[k]])
                for n in inm if not fails(by[n]['B2']) and fails(by[n]['CM'])]
    regress = [dict(movie=x['movie'], set=x['set'], metric=k, B2=x['B2'][k], CM=x['CM'][k], delta_A=x['CM'][k]-x['B2'][k],
                    B2_passes=not fails(x['B2']), CM_passes=not fails(x['CM']))
               for x in rows for k in LIM if x['CM'][k] > x['B2'][k]]
    verdict = 'NO-GO' if (rule1_median >= 0 or new_fail) else 'NOT_REFUTED_OFFLINE'
    cond_tab = {}
    for c in INMODEL + ['outmodel']:
        xs = [x for x in rows if x['condition'] == c]
        cond_tab[c] = dict(n=len(xs), **{f'median_{k}_{a}': med([x[a][k] for x in xs]) for a in ('B2', 'CM') for k in LIM},
                           passes_B2=sum(not fails(x['B2']) for x in xs), passes_CM=sum(not fails(x['CM']) for x in xs),
                           median_dMS_A2=med([x['dMS_direct_A2'] for x in xs]), mean_dMS_A2=float(np.mean([x['dMS_direct_A2'] for x in xs])),
                           n_rms_regress=sum(x['CM']['rms'] > x['B2']['rms'] for x in xs))
    seed_tab = {}
    for s in range(10):
        xs = [by[n] for n in inm if int(n.rsplit('-s', 1)[1]) == s]
        seed_tab[s] = dict(n=len(xs), mean_dMS_A2=float(np.mean([x['dMS_direct_A2'] for x in xs])), passes_B2=sum(not fails(x['B2']) for x in xs),
                           passes_CM=sum(not fails(x['CM']) for x in xs), mean_rel_rms_change=float(np.mean([(x['CM']['rms']-x['B2']['rms'])/x['B2']['rms'] for x in xs])),
                           n_rms_regress=sum(x['CM']['rms'] > x['B2']['rms'] for x in xs))
    summary = dict(verdict=verdict, rule1_median_of_8_seed_group_mean_dMS_A2=rule1_median, rule1_fires=rule1_median >= 0,
                   rule2_newly_failing=new_fail, rule2_fires=bool(new_fail), seed_groups_failing_rows=groups,
                   inmodel_passes=dict(native=gate['inmodel_passes_native'], B2=gate['inmodel_passes_B2'], CM=sum(not fails(by[n]['CM']) for n in inm)),
                   identity_max_abs_diff_A2=ident, identity_tolerance_A2=TOL_ID_A2, identity_pass=ident <= TOL_ID_A2,
                   n_regressions_any_metric=len(regress), n_movies_with_regression=len({g['movie'] for g in regress}),
                   per_condition=cond_tab, per_seed_cluster_inmodel80=seed_tab,
                   pedestal32=dict(status='NO_LOCAL_RETAINED', n=10, note='unchanged; native global-only field retained; no d'))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'stage2_score.json').write_text(json.dumps(dict(schema='w8-common-mean-s2/1', numpy=np.__version__, baseline_gate=gate, summary=summary,
                                                     regressions=regress, movies=rows), indent=1, allow_nan=False)+'\n')
    with (OUT/'stage2_per_movie.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['movie', 'condition', 'seed', 'set', 'status'] + [f'{a}_{k}_A' for a in ('native', 'B2', 'CM') for k in LIM]
                                      + ['dMS_direct_A2', 'dMS_identity_A2', 'identity_abs_diff_A2', 'd_rms_px', 'B2_passes', 'CM_passes'])
        for n in names:
            if n in by:
                x = by[n]; w.writerow([n, x['condition'], x['seed'], x['set'], 'REFIT_B2'] + [repr(x[a][k]) for a in ('native', 'B2', 'CM') for k in LIM]
                                      + [repr(x['dMS_direct_A2']), repr(x['dMS_identity_A2']), repr(x['identity_abs_diff_A2']), repr(x['d_rms_px']), not fails(x['B2']), not fails(x['CM'])])
            else:
                cond, seed = n.rsplit('-s', 1); nat = sc[n]['native_rt']
                w.writerow([n, cond, int(seed), 'pedestal32', 'NO_LOCAL_RETAINED'] + [repr(nat[k]) for k in LIM] + ['n/a']*6 + ['n/a']*4
                           + [not fails(nat), 'unchanged'])
    print(json.dumps(dict(verdict=verdict, rule1_median=rule1_median, rule2=len(new_fail), identity_max=ident, n_regress=len(regress))))
    if ident > TOL_ID_A2: sys.exit(6)


if __name__ == '__main__':
    main()
