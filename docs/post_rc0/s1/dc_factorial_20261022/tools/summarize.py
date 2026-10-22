#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Summarize evaluated #262 records into results/*.json and tables.md.

usage: summarize.py EVAL_DIR OUT_DIR
EVAL_DIR is the remote ROOT/eval tree (A-*.json, B/*.json, C-rows.json, controls.json).
Statistics follow FREEZE.md: paired seed within condition, arm vs none on the
same backend, exact two-sided sign test, improves/harms at p < 0.05 (unadjusted).
"""
import json, math, statistics as st, sys
from pathlib import Path

ARMS = ['none', 'global', 'local', 'both']
ORDER = ['pedestal32', 'pedestal0', 'contrast025', 'contrast4', 'dose1', 'dose05', 'dose2', 'dose4', 'outmodel', 'nonsquare']


def sign_p(w, l):
    n = w + l
    if n == 0: return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def mcnemar_p(b, c): return sign_p(b, c)


def g(x, *ks):
    for k in ks:
        if x is None: return None
        x = x.get(k) if isinstance(x, dict) else None
    return x


def tier_a(ev):
    out, totals = [], {}
    for backend in ['cpu', 'cuda']:
        for arm in ARMS + ['plain']:
            p = ev / f'A-{backend}-{arm}.json'
            if not p.exists(): continue
            for r in json.loads(p.read_text()):
                row = dict(backend=backend, arm=arm, case=r['case'], native_exit=r['native_exit'],
                           checker_exit=r['checker_exit'], checker_status=r['checker_status'],
                           sampling=r.get('sampling_status'), field_gate=r['field_gate'],
                           rms_px=r['field_px']['rms'], p95_px=r['field_px']['p95'], max_px=r['field_px']['max'],
                           rms_A=r['field_angstrom']['rms'],
                           global_converged=g(r, 'convergence', 'global_converged'),
                           global_iterations=g(r, 'convergence', 'global_iterations'),
                           local_enabled=r.get('runtime_local_enabled'), image=r.get('image'), dc_witness=r.get('dc_witness'))
                out.append(row)
                t = totals.setdefault(f'{backend}-{arm}', {})
                t[row['checker_status']] = t.get(row['checker_status'], 0) + 1
    return out, totals


def failure(m):
    t = m.get('truth') or {}
    conv = t.get('convergence') or {}
    comp = dict(native_exit=m['exit'] != 0,
                global_nonconverged=conv.get('global_converged') is False,
                global_ambiguous=conv.get('global_converged') is None and m['exit'] == 0,
                local_disabled=t.get('local_enabled') is False,
                outside_roi=t.get('sampling_status') == 'OUTSIDE_FIXED_ROI',
                field_distance_fail=t.get('field_distance_status') == 'FAIL')
    comp['union'] = any(v for k, v in comp.items() if k != 'global_ambiguous')
    return comp


def band_transfer(img, which):
    """check_realistic_image interior metrics: in-band transfer, or the top (0.12-0.16) band."""
    it = img['interior']
    return it['bands'][-1]['transfer'] if which == 'top' else it['transfer_inband']


def tier_b(ev):
    recs = {}
    for p in sorted((ev / 'B').glob('*.json')):
        m = json.loads(p.read_text())
        recs[m['id']] = m
    rows, pairs, regress = [], [], []
    for c in ORDER:
        for backend in ['cpu', 'cuda']:
            per_arm = {}
            for arm in ARMS:
                seeds = []
                for s in range(10):
                    m = recs.get(f'B-{c}-s{s:02d}-{backend}-{arm}')
                    if m is None: seeds.append(None); continue
                    ok = m['status'] == 'EVALUATED'
                    f = failure(m)
                    seeds.append(dict(seed=s, status=m['status'], failure=f,
                                      rms=g(m, 'truth', 'field', 'px', 'rms') if ok else None,
                                      p95=g(m, 'truth', 'field', 'px', 'p95') if ok else None,
                                      max=g(m, 'truth', 'field', 'px', 'max') if ok else None,
                                      rms_A=g(m, 'truth', 'field', 'angstrom', 'rms') if ok else None,
                                      global_rms=g(m, 'truth', 'global_trajectory', 'px', 'rms') if ok else None,
                                      local_rms=g(m, 'truth', 'local_component', 'px', 'rms') if ok else None,
                                      transfer=band_transfer(m['image'], 'all') if ok else None,
                                      transfer_top=band_transfer(m['image'], 'top') if ok else None,
                                      wall=m.get('wall_s_unqualified')))
                per_arm[arm] = seeds
                done = [x for x in seeds if x and x['status'] == 'EVALUATED']
                med = lambda k: st.median([x[k] for x in done]) if done else None
                fails = {k: sum(1 for x in seeds if x and x['failure'][k]) for k in
                         ['native_exit', 'global_nonconverged', 'global_ambiguous', 'local_disabled', 'outside_roi', 'field_distance_fail', 'union']}
                rows.append(dict(condition=c, backend=backend, arm=arm, n=len(done), n_records=sum(1 for x in seeds if x),
                                 median_rms_px=med('rms'), median_p95_px=med('p95'), worst_max_px=max((x['max'] for x in done), default=None),
                                 median_rms_A=med('rms_A'), median_global_rms_px=med('global_rms'), median_local_rms_px=med('local_rms'),
                                 median_transfer=med('transfer'), median_transfer_top=med('transfer_top'), failures=fails))
            for arm in ARMS[1:]:
                for metric, better in [('rms', -1), ('max', -1), ('transfer', 1), ('transfer_top', 1)]:
                    w = l = t = 0; deltas = []
                    for a, b in zip(per_arm['none'], per_arm[arm]):
                        if not a or not b or a['status'] != 'EVALUATED' or b['status'] != 'EVALUATED': continue
                        d = b[metric] - a[metric]; deltas.append(d)
                        if d * better > 0: w += 1
                        elif d * better < 0:
                            l += 1
                            regress.append(dict(condition=c, backend=backend, arm=arm, seed=a['seed'], metric=metric,
                                                none=a[metric], arm_value=b[metric], delta=d))
                        else: t += 1
                    p = sign_p(w, l)
                    md = st.median(deltas) if deltas else None
                    cat = 'improves' if p < .05 and w > l else ('harms' if p < .05 and l > w else 'neutral/mixed')
                    fb = sum(1 for a, b in zip(per_arm['none'], per_arm[arm]) if a and b and a['failure']['union'] and not b['failure']['union'])
                    fc = sum(1 for a, b in zip(per_arm['none'], per_arm[arm]) if a and b and not a['failure']['union'] and b['failure']['union'])
                    pairs.append(dict(condition=c, backend=backend, arm=arm, metric=metric, pairs=len(deltas), wins=w, losses=l, ties=t,
                                      sign_p=p, median_delta=md, category=cat if deltas else 'UNRUN',
                                      failure_fixed=fb, failure_new=fc, failure_mcnemar_p=mcnemar_p(fb, fc)))
    return rows, pairs, regress


def tier_c(ev):
    p = ev / 'C-rows.json'
    if not p.exists(): return [], {}
    rows = json.loads(p.read_text())
    fam = lambda m: m.split('-')[0]
    summary = {}
    for f in sorted({fam(r['movie']) for r in rows}):
        sub = [r for r in rows if fam(r['movie']) == f]
        s = summary.setdefault(f, {})
        for arm in ARMS:
            b = [(r['movie'], r['arms'].get(f'backend-{arm}')) for r in sub]
            b = [(m, x) for m, x in b if x]
            pos = {m for m, x in b if x['relative_rmse'] >= .1}
            strict = [x['compare_exit'] for _, x in b]
            s[arm] = dict(configs=len(b), movies=len({m for m, _ in b}), screen_positive_configs=sum(x['relative_rmse'] >= .1 for _, x in b),
                          screen_positive_movies=len(pos), strict_gate_exit0=sum(e == 0 for e in strict),
                          median_relrmse=st.median([x['relative_rmse'] for _, x in b]) if b else None)
    return rows, summary


def main():
    ev, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    a_rows, a_tot = tier_a(ev)
    b_rows, b_pairs, b_reg = tier_b(ev)
    c_rows, c_sum = tier_c(ev)
    ctl = json.loads((ev / 'controls.json').read_text()) if (ev / 'controls.json').exists() else []
    json.dump(dict(tierA=a_rows, tierA_totals=a_tot), open(out / 'tierA.json', 'w'), indent=1)
    json.dump(dict(rows=b_rows, pairs=b_pairs, regressions=b_reg), open(out / 'tierB.json', 'w'), indent=1)
    json.dump(dict(summary=c_sum), open(out / 'tierC-summary.json', 'w'), indent=1)
    json.dump(ctl, open(out / 'controls.json', 'w'), indent=1)
    print(json.dumps(dict(tierA_totals=a_tot, tierB_rows=len(b_rows), tierB_regressions=len(b_reg), tierC=c_sum, controls=[c['status'] for c in ctl]), indent=1))


if __name__ == '__main__': main()
