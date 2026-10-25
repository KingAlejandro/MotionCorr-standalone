#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Four-arm DC comparison over Tier B (804 records) and Tier C (C-rows), as declared in COMPARISON-PROTOCOL.md.

usage: analyze_dc_fourarm.py --tierb-dir DIR_WITH_B_JSON... --tierc-rows C-rows.json... --inventory INVENTORY.json
                              --summary804 tierB-v2.json --out OUT_DIR

Tier B definitions (failure(), band_transfer(), the regression rule, sign test) are imported from the unchanged
tools/summarize.py. The script refuses to continue unless the imported rule reproduces the reviewed v2.2 summary's
80 rows / 240 pairs / 965 regression entries exactly.
"""
import argparse, csv, importlib.util, json, math, shutil, statistics as st, sys, tempfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SUMMARIZE = HERE.parent / 'dc_factorial_20261022' / 'tools' / 'summarize.py'
ARMS = ['none', 'global', 'local', 'both']
VARIANTS = ARMS[1:]
LIMITS = dict(rms=0.20, p95=0.40, max=0.80)  # Angstrom; unchanged field_distance_status rule
SEED = 20261025
BOOT = 10000
SCREEN = 0.1  # existing Tier C screen threshold in summarize.tier_c


def load_summarize():
    spec = importlib.util.spec_from_file_location('dc_summarize', SUMMARIZE)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); adj = [None] * len(ps); run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i])); adj[i] = run
    return adj


def boot_ci(values, rng):
    v = np.asarray(values, float)
    if len(v) == 0: return [None, None]
    meds = np.median(v[rng.integers(0, len(v), (BOOT, len(v)))], axis=1)
    return [float(x) for x in np.percentile(meds, [2.5, 97.5])]


def sign_counts(deltas, better=-1):
    w = sum(1 for d in deltas if d * better > 0); l = sum(1 for d in deltas if d * better < 0)
    return w, l, len(deltas) - w - l


# ---------------------------------------------------------------- Tier B
def seed_table(S, recs):
    rows = {}
    for rid, m in recs.items():
        if m['arm'] not in ARMS: continue
        cond, seed = rid.split('-')[1], int(rid.split('-')[2][1:])
        row = dict(id=rid, cond=cond, seed=seed, backend=m['backend'], arm=m['arm'], status=m['status'], fail=S.failure(m))
        if m['status'] == 'EVALUATED':
            a = m['truth']['field']['angstrom']
            row.update(rms=a['rms'], p95=a['p95'], max=a['max'], transfer=S.band_transfer(m['image'], 'all'),
                       transfer_top=S.band_transfer(m['image'], 'top'), gate=m['truth']['field_distance_status'])
        rows[(cond, m['backend'], m['arm'], seed)] = row
    return rows


def tier_b_analysis(S, recs, rng):
    T = seed_table(S, recs)
    conds = sorted({k[0] for k in T}, key=lambda c: S.ORDER.index(c))
    out = dict(cells=[], limits=[], material=[], incomplete=[], backend_gap=[])
    for backend in ['cpu', 'cuda']:
        for c in conds:
            for arm in ARMS:
                got = [T.get((c, backend, arm, s)) for s in range(10)]
                ev = [r for r in got if r and r['status'] == 'EVALUATED']
                out['limits'].append(dict(cond=c, backend=backend, arm=arm, evaluated=len(ev),
                    pass_rms=sum(r['rms'] <= LIMITS['rms'] for r in ev), pass_p95=sum(r['p95'] <= LIMITS['p95'] for r in ev),
                    pass_max=sum(r['max'] <= LIMITS['max'] for r in ev), pass_all=sum(r['gate'] == 'PASS' for r in ev),
                    median_rms=st.median([r['rms'] for r in ev]) if ev else None, median_p95=st.median([r['p95'] for r in ev]) if ev else None,
                    median_max=st.median([r['max'] for r in ev]) if ev else None,
                    median_transfer=st.median([r['transfer'] for r in ev]) if ev else None,
                    median_transfer_top=st.median([r['transfer_top'] for r in ev]) if ev else None,
                    nonconverged=sum(1 for r in got if r and r['fail']['global_nonconverged'])))
                out['incomplete'].append(dict(tier='B', cond=c, backend=backend, arm=arm, expected=10, present=sum(1 for r in got if r),
                                              evaluated=len(ev), missing=10 - sum(1 for r in got if r)))
            for arm in VARIANTS:
                pairs = [(T.get((c, backend, 'none', s)), T.get((c, backend, arm, s))) for s in range(10)]
                ok = [(a, b) for a, b in pairs if a and b and a['status'] == 'EVALUATED' and b['status'] == 'EVALUATED']
                d = [b['rms'] - a['rms'] for a, b in ok]
                w, l, t = sign_counts(d)
                cell = dict(cond=c, backend=backend, arm=arm, matched=len(ok), wins=w, losses=l, ties=t, sign_p=S.sign_p(w, l),
                            median_delta_rms_A=st.median(d) if d else None, boot95_median_delta=boot_ci(d, rng))
                for met in ['p95', 'max']:
                    dm = [b[met] - a[met] for a, b in ok]
                    cell[f'median_delta_{met}_A'] = st.median(dm) if dm else None
                    cell[f'{met}_wins_losses'] = sign_counts(dm)[:2]
                for met in ['transfer', 'transfer_top']:
                    dm = [b[met] - a[met] for a, b in ok]
                    cell[f'median_delta_{met}'] = st.median(dm) if dm else None
                    cell[f'{met}_gain_loss'] = sign_counts(dm, better=1)[:2]
                gate_b = sum(1 for a, b in ok if a['gate'] != 'PASS' and b['gate'] == 'PASS')
                gate_c = sum(1 for a, b in ok if a['gate'] == 'PASS' and b['gate'] != 'PASS')
                cell.update(gate_fixed=gate_b, gate_new=gate_c, gate_mcnemar_p=S.sign_p(gate_b, gate_c),
                            fail_fixed=sum(1 for a, b in pairs if a and b and a['fail']['union'] and not b['fail']['union']),
                            fail_new=sum(1 for a, b in pairs if a and b and not a['fail']['union'] and b['fail']['union']))
                out['cells'].append(cell)
                for a, b in ok:  # material harm: limit crossing and new failure components
                    reasons = [f'limit_cross:{met}' for met in LIMITS if a[met] <= LIMITS[met] < b[met]]
                    reasons += [f'new_failure:{k}' for k in ('native_exit', 'global_nonconverged', 'local_disabled', 'outside_roi')
                                if b['fail'][k] and not a['fail'][k]]
                    if reasons:
                        out['material'].append(dict(tier='B', id=b['id'], cond=c, backend=backend, arm=arm, seed=a['seed'], reasons=reasons,
                                                    none=dict(rms=a['rms'], p95=a['p95'], max=a['max']), arm_value=dict(rms=b['rms'], p95=b['p95'], max=b['max'])))
    adj = holm([c['sign_p'] for c in out['cells']])
    for c, a in zip(out['cells'], adj): c['holm_p'] = a
    for c in out['cells']:
        c['label_raw'] = 'improves' if c['sign_p'] < .05 and c['wins'] > c['losses'] else ('harms' if c['sign_p'] < .05 and c['losses'] > c['wins'] else 'neutral/mixed')
        c['label_holm'] = 'improves' if c['holm_p'] < .05 and c['wins'] > c['losses'] else ('harms' if c['holm_p'] < .05 and c['losses'] > c['wins'] else 'neutral/mixed')
    for c in conds:  # descriptive backend gap in truth error (not output agreement)
        for arm in ARMS:
            gaps = [abs(T[(c, 'cuda', arm, s)]['rms'] - T[(c, 'cpu', arm, s)]['rms']) for s in range(10)
                    if (c, 'cuda', arm, s) in T and (c, 'cpu', arm, s) in T and 'rms' in T[(c, 'cuda', arm, s)] and 'rms' in T[(c, 'cpu', arm, s)]]
            out['backend_gap'].append(dict(cond=c, arm=arm, n=len(gaps), median_abs_gap_rms_A=st.median(gaps) if gaps else None))
    return out


# ---------------------------------------------------------------- Tier C
def tier_c_analysis(rows, inv, rng):
    rows = sorted(rows, key=lambda r: r['config'])
    cfgs = {r['config']: r for r in rows}
    out = dict(graded=dict(cpu=0, cuda=0), vs_none=[], agreement=[], agreement_tests=[], convergence=[], incomplete=[], harm=[], units=[])
    movies = sorted({r['movie'] for r in rows}); fam = lambda m: m.split('-')[0]
    out['movies'] = len(movies); out['configs'] = len(rows); out['families'] = len({fam(m) for m in movies})
    for r in rows:
        for k in r['arms']:
            if k.split('-')[0] in ('cpu', 'cuda') and r['arms'][k].get('exit') == 0: out['graded'][k.split('-')[0]] += 1

    def nonconv(r, backend, arm):
        d = r['arms'].get(f'{backend}-{arm}')
        if d is None: return None
        g = (d.get('convergence') or {})
        if 'error' in g: return 'error'
        return {True: False, False: True, None: 'ambiguous'}[g.get('global_converged')]

    def movie_values(fn, arms_needed):
        """Movie-level mean of fn(row) over the grids where fn is defined for every needed arm."""
        per = {}
        for r in rows:
            vals = [fn(r, a) for a in arms_needed]
            if all(v is not None for v in vals): per.setdefault(r['movie'], []).append(vals)
        return {m: [float(np.mean([v[i] for v in vs])) for i in range(len(arms_needed))] for m, vs in per.items()}, per

    # change vs none (descriptive)
    for backend in ['cpu', 'cuda']:
        for arm in VARIANTS:
            for key in ('relative_rmse', 'global_rms_px'):
                fn = lambda r, a, backend=backend, key=key: ((r['arms'].get(f'{backend}-{a}') or {}).get('vs_none') or {}).get(key)
                mv, per = movie_values(fn, [arm])
                v = [x[0] for x in mv.values()]
                entry = dict(backend=backend, arm=arm, metric=key, movies=len(v), configs=sum(len(x) for x in per.values()),
                             median=st.median(v) if v else None, boot95=boot_ci(v, rng), max=max(v) if v else None)
                if key == 'relative_rmse':
                    allc = [x[0] for xs in per.values() for x in xs]
                    entry.update(configs_ge_screen=sum(x >= SCREEN for x in allc), movies_ge_screen=sum(any(x[0] >= SCREEN for x in xs) for xs in per.values()))
                out['vs_none'].append(entry)
    # CPU/CUDA agreement per arm and paired difference vs none
    for arm in ARMS:
        fn = lambda r, a, arm=arm: ((r['arms'].get(f'backend-{arm}') or {}).get('relative_rmse'))
        mv, per = movie_values(fn, [arm])
        v = [x[0] for x in mv.values()]
        out['agreement'].append(dict(arm=arm, movies=len(v), configs=sum(len(x) for x in per.values()), median_relrmse=st.median(v) if v else None,
                                     boot95=boot_ci(v, rng), max=max(v) if v else None,
                                     configs_ge_screen=sum(x[0] >= SCREEN for xs in per.values() for x in xs),
                                     compare_exit0=sum(1 for r in rows if (r['arms'].get(f'backend-{arm}') or {}).get('compare_exit') == 0),
                                     compare_present=sum(1 for r in rows if f'backend-{arm}' in r['arms'])))
    for arm in VARIANTS:
        fn = lambda r, a: ((r['arms'].get(f'backend-{a}') or {}).get('relative_rmse'))
        mv, per = movie_values(fn, ['none', arm])
        d = [x[1] - x[0] for x in mv.values()]
        w, l, t = sign_counts(d)
        byfam = {}
        for m, x in mv.items():
            e = byfam.setdefault(fam(m), [0, 0, 0]); dd = x[1] - x[0]
            e[0 if dd < 0 else (1 if dd > 0 else 2)] += 1
        out['agreement_tests'].append(dict(arm=arm, by_family_closer_further_tie=byfam, movies=len(d), configs=sum(len(x) for x in per.values()), closer=w, further=l, ties=t,
                                           sign_p=sign_p_exact(w, l), median_delta=st.median(d) if d else None, boot95=boot_ci(d, rng)))
    adj = holm([t['sign_p'] for t in out['agreement_tests']])
    for t, a in zip(out['agreement_tests'], adj): t['holm_p'] = a
    # convergence change vs none (paired within config; movie-level counted separately)
    for backend in ['cpu', 'cuda']:
        for arm in VARIANTS:
            fixed = new = both = neither = unmatched = 0; amb = 0
            for r in rows:
                a, b = nonconv(r, backend, 'none'), nonconv(r, backend, arm)
                if a is None or b is None: unmatched += 1; continue
                if 'error' in (a, b) or 'ambiguous' in (a, b): amb += 1; continue
                if a and not b: fixed += 1
                elif b and not a:
                    new += 1
                    out['harm'].append(dict(tier='C', config=r['config'], backend=backend, arm=arm, reason='new_global_nonconvergence_vs_none'))
                elif a and b: both += 1
                else: neither += 1
            out['convergence'].append(dict(backend=backend, arm=arm, configs_matched=fixed + new + both + neither, fixed=fixed, new=new,
                                           both_nonconverged=both, neither=neither, ambiguous_or_error=amb, unmatched_with_none=unmatched,
                                           mcnemar_p=sign_p_exact(fixed, new)))
    # incomplete / unmatched table from the frozen queue inventory
    exp = {}
    for rec in inv['records'] + inv['other']:
        k = (rec['backend'], rec['arm']); e = exp.setdefault(k, dict(expected=0, graded=0, never_run=0, orphan=0, other=0))
        e['expected'] += 1
        e['graded'] += rec['state'] == 'EXIT0'; e['never_run'] += rec['state'] == 'NEVER_RUN'
        e['orphan'] += rec['state'].startswith('INTERRUPTED'); e['other'] += rec['state'] not in ('EXIT0', 'NEVER_RUN') and not rec['state'].startswith('INTERRUPTED')
    out['incomplete'] = [dict(tier='C', backend=k[0], arm=k[1], **v) for k, v in sorted(exp.items())]
    out['unmatched_agreement_configs'] = {arm: sorted(r['config'] for r in rows if f'backend-{arm}' not in r['arms']) for arm in ARMS}
    out['unmatched_agreement_counts'] = {arm: len(v) for arm, v in out['unmatched_agreement_configs'].items()}
    out['configs_with_any_cuda'] = sum(1 for r in rows if any(k.startswith('cuda-') for k in r['arms']))
    out['configs_with_full_cuda_arms'] = sum(1 for r in rows if all(f'cuda-{a}' in r['arms'] for a in ARMS))
    return out


def sign_p_exact(w, l):
    n = w + l
    if n == 0: return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n)


# ---------------------------------------------------------------- driver
def read_recs(dirs):
    recs = {}
    for d in dirs:
        for p in sorted(Path(d).glob('*.json')):
            m = json.loads(p.read_text())
            if m['id'] in recs: raise SystemExit(f'duplicate Tier B record {m["id"]}')
            recs[m['id']] = m
    return recs


def fmt(v, d=4):
    if v is None: return ''
    return f'{v:.{d}g}' if isinstance(v, float) else str(v)


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or (list(rows[0].keys()) if rows else [])
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader()
        for r in rows: w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tierb-dir', action='append', required=True); ap.add_argument('--tierc-rows', action='append', required=True)
    ap.add_argument('--inventory', required=True); ap.add_argument('--summary804', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    S = load_summarize(); rng = np.random.default_rng(SEED)
    recs = read_recs(a.tierb_dir)
    # control: the imported unchanged rule must reproduce the reviewed v2.2 summary exactly
    with tempfile.TemporaryDirectory() as t:
        (Path(t) / 'B').mkdir()
        for rid, m in recs.items(): (Path(t) / 'B' / f'{rid}.json').write_text(json.dumps(m))
        rows, pairs, regress = S.tier_b(Path(t))
    ref = json.loads(Path(a.summary804).read_text())
    key = lambda r: json.dumps(r, sort_keys=True)
    if sorted(map(key, regress)) != sorted(map(key, ref['regressions'])) or len(rows) != len(ref['rows']) or len(pairs) != len(ref['pairs']):
        raise SystemExit('FAIL: reimplementation does not reproduce the reviewed 80/240/965 summary')
    control = dict(rows=len(rows), pairs=len(pairs), regressions=len(regress), regressions_identical_to_v2_2_summary=True, records=len(recs))
    B = tier_b_analysis(S, recs, rng)
    inv = json.loads(Path(a.inventory).read_text())
    crow = [r for p in a.tierc_rows for r in json.loads(Path(p).read_text())]
    if len({r['config'] for r in crow}) != len(crow): raise SystemExit('duplicate Tier C config across batches')
    C = tier_c_analysis(crow, inv, rng)
    res = dict(protocol='COMPARISON-PROTOCOL.md', seed=SEED, bootstrap=BOOT, control=control, tierB=B, tierC=C)
    (out / 'RESULTS.json').write_text(json.dumps(res, indent=1, allow_nan=False) + '\n')
    write_csv(out / 'tierB_cells.csv', B['cells']); write_csv(out / 'tierB_limits.csv', B['limits'])
    write_csv(out / 'tierB_material_harms.csv', B['material']); write_csv(out / 'tierB_regressions_all.csv', regress)
    write_csv(out / 'tierC_vs_none.csv', C['vs_none']); write_csv(out / 'tierC_agreement.csv', C['agreement'])
    write_csv(out / 'tierC_convergence.csv', C['convergence']); write_csv(out / 'incomplete.csv', B['incomplete'] + C['incomplete'])
    write_csv(out / 'tierC_harm.csv', C['harm'], ['tier', 'config', 'backend', 'arm', 'reason'])
    (out / 'REPORT.md').write_text(report(res, regress))
    print(json.dumps(dict(control=control, tierC_graded=C['graded'], material_B=len(B['material']), harm_C=len(C['harm']))))


def report(res, regress):
    B, C = res['tierB'], res['tierC']; L = ['# Four-arm DC comparison (generated)', '', f"Control: imported unchanged rule reproduces v2.2 summary exactly ({res['control']['rows']} rows / {res['control']['pairs']} pairs / {res['control']['regressions']} regression entries; {res['control']['records']} Tier B records).", '']
    L += ['## Tier B: field RMS vs none, per backend (cells = 10 conditions; paired seeds)', '',
          '| backend | arm | cells improves (raw p<.05) | cells harms (raw) | improves after Holm(60) | harms after Holm(60) | seeds meeting all 3 limits /100 | seeds meeting RMS / p95 / max limit |', '|---|---|---:|---:|---:|---:|---:|---|']
    for backend in ['cpu', 'cuda']:
        for arm in ARMS:
            lim = [x for x in B['limits'] if x['backend'] == backend and x['arm'] == arm]
            tail = f"{sum(x['pass_all'] for x in lim)}/{sum(x['evaluated'] for x in lim)} | {sum(x['pass_rms'] for x in lim)} / {sum(x['pass_p95'] for x in lim)} / {sum(x['pass_max'] for x in lim)}"
            if arm == 'none': L.append(f'| {backend} | none | - | - | - | - | {tail} |'); continue
            cs = [c for c in B['cells'] if c['backend'] == backend and c['arm'] == arm]
            L.append(f"| {backend} | {arm} | {sum(c['label_raw']=='improves' for c in cs)} | {sum(c['label_raw']=='harms' for c in cs)} | {sum(c['label_holm']=='improves' for c in cs)} | {sum(c['label_holm']=='harms' for c in cs)} | {tail} |")
    L += ['', '### Every primary cell (arm - none, field RMS Angstrom; W/L = seeds improved/worsened)', '',
          '| cond | backend | arm | n | W/L/T | raw p | Holm p | median delta | boot95 median delta | median delta p95 / max | transfer gain/loss | limit pass fixed/new |', '|---|---|---|---:|---|---:|---:|---:|---|---|---|---|']
    for c in B['cells']:
        L.append(f"| {c['cond']} | {c['backend']} | {c['arm']} | {c['matched']} | {c['wins']}/{c['losses']}/{c['ties']} | {fmt(c['sign_p'])} | {fmt(c['holm_p'])} | {fmt(c['median_delta_rms_A'])} | "
                 f"[{fmt(c['boot95_median_delta'][0])}, {fmt(c['boot95_median_delta'][1])}] | {fmt(c['median_delta_p95_A'])} / {fmt(c['median_delta_max_A'])} | {c['transfer_gain_loss'][0]}/{c['transfer_gain_loss'][1]} | {c['gate_fixed']}/{c['gate_new']} |")
    L += ['', f"### Material harms in Tier B ({len(B['material'])} seed entries; also in tierB_material_harms.csv)", '',
          '| id | arm | reasons | rms none -> arm | p95 none -> arm | max none -> arm |', '|---|---|---|---|---|---|']
    for h in B['material']:
        L.append(f"| {h['id']} | {h['arm']} | {', '.join(h['reasons'])} | {fmt(h['none']['rms'])} -> {fmt(h['arm_value']['rms'])} | {fmt(h['none']['p95'])} -> {fmt(h['arm_value']['p95'])} | {fmt(h['none']['max'])} -> {fmt(h['arm_value']['max'])} |")
    L += ['', f"Existing regression rule: {len(regress)} entries (all in tierB_regressions_all.csv). Material harm is a subset by construction only for limit crossings; see protocol.", '']
    L += ['## Tier C (no truth): change vs none, convergence, CPU/CUDA agreement', '',
          f"Graded: CPU {C['graded']['cpu']}, CUDA {C['graded']['cuda']} records; {C['configs']} configs from {C['movies']} movies / {C['families']} families; CUDA present for {C['configs_with_any_cuda']} configs ({C['configs_with_full_cuda_arms']} with all four arms).", '',
          '| backend | arm | metric | movies | configs | median | boot95 | max | configs / movies >= 0.1 |', '|---|---|---|---:|---:|---:|---|---:|---|']
    for v in C['vs_none']:
        scr = f"{v.get('configs_ge_screen','')} / {v.get('movies_ge_screen','')}" if v['metric'] == 'relative_rmse' else ''
        L.append(f"| {v['backend']} | {v['arm']} | {v['metric']} | {v['movies']} | {v['configs']} | {fmt(v['median'])} | [{fmt(v['boot95'][0])}, {fmt(v['boot95'][1])}] | {fmt(v['max'])} | {scr} |")
    L += ['', '### Convergence change vs none (config-paired; sign test shown, not in any family)', '', '| backend | arm | matched | fixed | new | both nonconv | ambiguous/error | unmatched | p |', '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for v in C['convergence']:
        L.append(f"| {v['backend']} | {v['arm']} | {v['configs_matched']} | {v['fixed']} | {v['new']} | {v['both_nonconverged']} | {v['ambiguous_or_error']} | {v['unmatched_with_none']} | {fmt(v['mcnemar_p'])} |")
    L += ['', '### CPU/CUDA agreement (relative image RMSE, separate axis)', '', '| arm | movies | configs | median | boot95 | max | configs >= 0.1 | strict backend gate exit 0 (of present) |', '|---|---:|---:|---:|---|---:|---:|---|']
    for v in C['agreement']:
        L.append(f"| {v['arm']} | {v['movies']} | {v['configs']} | {fmt(v['median_relrmse'])} | [{fmt(v['boot95'][0])}, {fmt(v['boot95'][1])}] | {fmt(v['max'])} | {v['configs_ge_screen']} | {v['compare_exit0']} / {v['compare_present']} |")
    L += ['', '#### Primary Tier C family: agreement of arm minus none (per movie; negative = closer CPU/CUDA agreement)', '', '| arm | movies | closer/further/tie | raw p | Holm p (3) | median delta | boot95 |', '|---|---:|---|---:|---:|---:|---|']
    for t in C['agreement_tests']:
        L.append(f"| {t['arm']} | {t['movies']} | {t['closer']}/{t['further']}/{t['ties']} | {fmt(t['sign_p'])} | {fmt(t['holm_p'])} | {fmt(t['median_delta'])} | [{fmt(t['boot95'][0])}, {fmt(t['boot95'][1])}] |")
    L += ['', 'Post-hoc caveat (not in the declared family): matched movies come from few datasets, and movies of one dataset are not independent. Per-family closer/further/tie: ' + '; '.join(f"{t['arm']} {t['by_family_closer_further_tie']}" for t in C['agreement_tests']) + '.']
    L += ['', '## Incomplete or unmatched', '', '| tier | backend | arm | expected | present/graded | never run | orphan | other |', '|---|---|---|---:|---:|---:|---:|---:|']
    for r in C['incomplete']:
        L.append(f"| C | {r['backend']} | {r['arm']} | {r['expected']} | {r['graded']} | {r['never_run']} | {r['orphan']} | {r['other']} |")
    bi = {}
    for r in B['incomplete']:
        k = (r['backend'], r['arm']); e = bi.setdefault(k, [0, 0, 0]); e[0] += r['expected']; e[1] += r['present']; e[2] += r['evaluated']
    for (b, arm), e in sorted(bi.items()): L.append(f"| B | {b} | {arm} | {e[0]} | {e[1]} present / {e[2]} evaluated | 0 | 0 | 0 |")
    L += ['', f"Tier C configs without a CPU/CUDA comparison per arm: {C['unmatched_agreement_counts']} of {C['configs']} (names in RESULTS.json)."]
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    main()
