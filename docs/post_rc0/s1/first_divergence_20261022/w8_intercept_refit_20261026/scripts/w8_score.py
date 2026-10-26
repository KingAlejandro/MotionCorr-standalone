#!/usr/bin/env python3
"""W8 census stage 2: score stage-1 refits with the unchanged evaluator (../PLAN.md, amendment 1).

Usage: w8_score.py SRC RUNS refit.json OUT.json TABLES.md
Truth enters only here, after every fit is fixed in refit.json.
Arms (offline reconstructions, never native applied fields):
  R-rt   runtime full-precision global + full-precision B2 coefficients
  R-hyb  STAR read-back global + full-precision B2 coefficients (hybrid; NOT a serialised field)
A full global + coefficient STAR round trip of the refit is UNRUN (no pinned writer is invoked offline).
"""
import json
import sys
from pathlib import Path
import numpy as np

SRC, RUNS, REFIT, OUT, MD = map(Path, sys.argv[1:6])
sys.path.insert(0, str(Path(__file__).resolve().parent))
from w8_refit import read_star                        # noqa: E402
sys.path[:0] = [str(SRC/'tools'), str(SRC/'test-data')]
import check_realistic_motion as ev                   # noqa: E402  (unchanged)
import generate_realistic_motion as gen               # noqa: E402  (unchanged)
from motion_field import read_motion_star             # noqa: E402

NF = 40
LIM = dict(rms=.20, p95=.40, max=.80)
INMODEL = ['dose05', 'dose1', 'dose2', 'dose4', 'pedestal0', 'contrast025', 'contrast4', 'nonsquare']
DOSE1_FAMILY = ['dose1', 'pedestal0', 'contrast025', 'contrast4']
CONDS = INMODEL + ['outmodel', 'pedestal32']


def close(a, b, path=''):
    if isinstance(a, dict):
        return [m for k in b for m in close(a.get(k), b[k], f'{path}/{k}')] if isinstance(b, dict) else [path]
    if isinstance(a, list):
        if not isinstance(b, list) or len(a) != len(b): return [path]
        return [m for i, (x, y) in enumerate(zip(a, b)) for m in close(x, y, f'{path}[{i}]')]
    if isinstance(a, float) or isinstance(b, float):
        return [] if abs(a-b) <= 1e-12*max(abs(a), abs(b), 1e-300) else [path]
    return [] if a == b else [path]


def fails(m):
    return [k for k in LIM if m[k] > LIM[k]]


def pearson(a, b):
    a, b = np.ravel(a), np.ravel(b)
    return float(np.corrcoef(a, b)[0, 1])


def movie(name, rf):
    cond, seed = name.rsplit('-s', 1); r = gen.recipe(cond, int(seed))
    d = RUNS/name/'F'
    met = json.loads((d/'metrics.json').read_text()); rt = json.loads((d/'runtime.json').read_text())
    g2 = close(ev.evaluate(r, rt, read_motion_star(d/'output/movie.star')), {k: met[k] for k in ('field', 'global_trajectory', 'local_component', 'border', 'serialized_field')})
    out = dict(movie=name, condition=cond, seed=int(seed), status=rf['status'], G2_mismatches=g2,
               native_rt=met['field']['angstrom'], native_ser=met['serialized_field']['angstrom'])
    if rf['status'] != 'REFIT_B2':
        return out
    coeff = dict(coeff_x=rf['coeff_x'], coeff_y=rf['coeff_y'], local_enabled=True)
    out['R_rt'] = ev.evaluate(r, dict(coeff, **{'global': rf['global_runtime']}))['field']['angstrom']
    out['R_hyb'] = ev.evaluate(r, dict(coeff, **{'global': rf['global_star']}))['field']['angstrom']
    # T4 intercept correlation. Frozen target d = mean_g[obs - (Tc - G)], which contains the +0.5 R(1)
    # convention term; secondary (reported only): both sides with 0.5 R(1) removed.
    _, _, _, keys, obs = read_star(d/'output/movie.star')
    assert np.array_equal(keys, np.array(rf['patch_centres']))
    G = np.asarray(rf['global_runtime'])
    Tc = np.stack([-gen.displacement(r, f, keys[:, 0], keys[:, 1]) for f in range(NF)], 1)
    R = Tc - G[None]
    target = (obs - R).mean(1)                                     # (patch, 2)
    c = np.stack([rf['intercept_x'], rf['intercept_y']], -1)
    half = 0.5*R[:, 1]
    out['T4'] = dict(r=pearson(c, target), r_without_half_R1=pearson(c-half, target-half),
                     target_rms_px=float(np.sqrt(np.mean(np.sum(target**2, -1)))), half_R1_rms_px=float(np.sqrt(np.mean(np.sum(half**2, -1)))))
    return out


def main():
    refit = json.loads(REFIT.read_text())
    assert refit['gates']['pass'] and not refit['gates']['truth_modules_imported']
    res = [movie(n, rf) for n, rf in sorted(refit['movies'].items())]
    assert all(not m['G2_mismatches'] for m in res), [m['movie'] for m in res if m['G2_mismatches']]
    by = {c: [m for m in res if m['condition'] == c] for c in CONDS}
    inm = [m for c in INMODEL for m in by[c]]
    med = lambda a: float(np.median(a))
    S = {}
    for arm, nat in (('R_rt', 'native_rt'), ('R_hyb', 'native_ser')):
        S[arm] = dict(
            vs=nat, n_inmodel=len(inm),
            P1_dose1_family_median_rms=med([m[arm]['rms'] for c in DOSE1_FAMILY for m in by[c]]),
            P2_inmodel_passes=sum(not fails(m[arm]) for m in inm), native_inmodel_passes=sum(not fails(m[nat]) for m in inm),
            median_rel_improvement=med([(m[nat]['rms']-m[arm]['rms'])/m[nat]['rms'] for m in inm]),
            regressions=[dict(movie=m['movie'], native=m[nat], refit=m[arm], newly_failing=[k for k in LIM if m[nat][k] <= LIM[k] < m[arm][k]])
                         for m in res if m['status'] == 'REFIT_B2' and (m[arm]['rms'] > m[nat]['rms'] or any(m[nat][k] <= LIM[k] < m[arm][k] for k in LIM))])
    S['median_r_inmodel'] = med([m['T4']['r'] for m in inm])
    S['median_r_without_half_R1_inmodel'] = med([m['T4']['r_without_half_R1'] for m in inm])
    rt = S['R_rt']
    S['verdict'] = dict(P1=rt['P1_dose1_family_median_rms'] <= .15, P2=rt['P2_inmodel_passes'] > 22,
                        refuted_improvement_lt_20pct=rt['median_rel_improvement'] < .20, refuted_r_lt_0p5=S['median_r_inmodel'] < .5)
    OUT.write_text(json.dumps(dict(schema='w8-score/1', numpy=np.__version__, summary=S, movies=res), indent=1, allow_nan=False)+'\n')

    L = ['# W8 census tables (generated by scripts/w8_score.py)\n',
         'Offline reconstructions. R-rt = runtime global + full-precision B2 coefficients; R-hyb = STAR read-back global + full-precision B2 coefficients (hybrid, not a serialised field). A full refit STAR round trip is UNRUN. Native comparators: runtime field and serialised field from the H7a F `metrics.json`.\n',
         '## Predictions (R-rt vs native runtime)\n',
         f"- P1 dose1-family median RMS: {rt['P1_dose1_family_median_rms']:.4f} Å (prediction ≤ 0.15): {'HOLDS' if S['verdict']['P1'] else 'FAILS'}",
         f"- P2 in-model passes: {rt['P2_inmodel_passes']} of 80 (native {rt['native_inmodel_passes']}; prediction > 22): {'HOLDS' if S['verdict']['P2'] else 'FAILS'}",
         f"- median in-model relative RMS improvement: {rt['median_rel_improvement']:.3f} (refuted if < 0.20): {'REFUTED' if S['verdict']['refuted_improvement_lt_20pct'] else 'not refuted'}",
         f"- median in-model intercept r (frozen target): {S['median_r_inmodel']:.3f} (refuted if < 0.5): {'REFUTED' if S['verdict']['refuted_r_lt_0p5'] else 'not refuted'}; secondary r without 0.5 R(1): {S['median_r_without_half_R1_inmodel']:.3f}",
         f"- R-hyb (vs native serialised): P1 {S['R_hyb']['P1_dose1_family_median_rms']:.4f} Å, passes {S['R_hyb']['P2_inmodel_passes']} of 80 (native serialised {S['R_hyb']['native_inmodel_passes']}), median improvement {S['R_hyb']['median_rel_improvement']:.3f}\n",
         '## Per condition (median RMS / p95 / max Å; passes of 10)\n',
         '| condition | status | native rt | R-rt | native ser | R-hyb | passes native rt / R-rt / native ser / R-hyb | median r / r without 0.5R(1) |', '|---|---|---|---|---|---|---|---|']
    f3 = lambda ms, k: ' / '.join(f"{med([m[k][q] for m in ms]):.3f}" for q in LIM)
    for c in CONDS:
        ms = by[c]
        if not ms: continue
        st = ms[0]['status']
        if st == 'REFIT_B2':
            L.append(f"| {c} | {st} | {f3(ms, 'native_rt')} | {f3(ms, 'R_rt')} | {f3(ms, 'native_ser')} | {f3(ms, 'R_hyb')} | "
                     + ' / '.join(str(sum(not fails(m[k]) for m in ms)) for k in ('native_rt', 'R_rt', 'native_ser', 'R_hyb'))
                     + f" | {med([m['T4']['r'] for m in ms]):.3f} / {med([m['T4']['r_without_half_R1'] for m in ms]):.3f} |")
        else:
            L.append(f"| {c} | {st} (no refit) | {f3(ms, 'native_rt')} | n/a | {f3(ms, 'native_ser')} | n/a | {sum(not fails(m['native_rt']) for m in ms)} / n/a / {sum(not fails(m['native_ser']) for m in ms)} / n/a | n/a |")
    L.append('\n`dose1`, `pedestal0`, `contrast025` and `contrast4` share each seed\'s noise draws (not independent). `outmodel` is unrepresentable (RMS floor 0.885 Å) and is reported separately from the in-model predictions.\n')
    L.append('## Per movie (R-rt failing limits; native in brackets)\n')
    L.append('| movie | native rt RMS / p95 / max | R-rt RMS / p95 / max | R-rt fails | r |'); L.append('|---|---|---|---|---|')
    for m in res:
        if m['status'] != 'REFIT_B2':
            L.append(f"| {m['movie']} | " + ' / '.join(f"{m['native_rt'][q]:.3f}" for q in LIM) + f" | {m['status']} | {'+'.join(fails(m['native_rt'])) or 'pass'} (native) | n/a |")
            continue
        L.append(f"| {m['movie']} | " + ' / '.join(f"{m['native_rt'][q]:.3f}" for q in LIM) + ' | ' + ' / '.join(f"{m['R_rt'][q]:.3f}" for q in LIM)
                 + f" | {'+'.join(fails(m['R_rt'])) or 'pass'} [{'+'.join(fails(m['native_rt'])) or 'pass'}] | {m['T4']['r']:.3f} |")
    for arm in ('R_rt', 'R_hyb'):
        L.append(f"\n## Regressions, {arm} (RMS above native, or a native limit pass that fails): {len(S[arm]['regressions'])}\n")
        for g in S[arm]['regressions']:
            L.append(f"- {g['movie']}: native " + '/'.join(f"{g['native'][q]:.3f}" for q in LIM) + ' → refit ' + '/'.join(f"{g['refit'][q]:.3f}" for q in LIM)
                     + (f"; newly failing {g['newly_failing']}" if g['newly_failing'] else ''))
    MD.write_text('\n'.join(L)+'\n')
    print(json.dumps(S['verdict']), json.dumps({k: v for k, v in rt.items() if k != 'regressions'}))


if __name__ == '__main__':
    main()
