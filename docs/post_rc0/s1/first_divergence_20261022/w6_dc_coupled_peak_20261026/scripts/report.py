#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Saved-result processing of results/w6.json: frozen prediction verdicts, regressions, tables. No estimator runs."""
import hashlib
import json
from pathlib import Path

W6 = Path(__file__).resolve().parents[1]
raw = (W6/'results/w6.json').read_bytes()
d = json.loads(raw)
ARMS = ('S-P', 'S-D', 'H-P', 'H-D')
M = ('rms', 'p95', 'max')
SC = ('runtime', 'STAR')


def rows():
    """(group, case-or-control, domain, stop, variant/weight, arm, record)."""
    for case, rec in d['cases'].items():
        for key, r in rec['rows'].items():
            yield 'fixture', case, r['domain'], r['stop'], r['patch_variant'], r['arm'], r
    for key, r in d['probes'].items():
        yield 'probe', key.split('-'+r['weight'])[0], r['domain'], r['stop'], r['weight'], r['arm'], r


table = {}
for g, c, dom, stop, var, arm, r in rows():
    table[(g, c, dom, stop, var, arm)] = r


def get(g, c, dom, stop, var, arm):
    return table[(g, c, dom, stop, var, arm)]


def passes(r, s):
    return r[s]['verdict'] == 'PASS'


def traj(r):
    return r['global_trajectory']


def maxdiff(a, b):
    return max(abs(x-y) for ra, rb in zip(a, b) for x, y in zip(ra, rb))


# Regressions: every increase of any metric of any arm versus same-domain/stop/variant S-P.
regressions = []
for (g, c, dom, stop, var, arm), r in sorted(table.items()):
    if arm == 'S-P':
        continue
    b = get(g, c, dom, stop, var, 'S-P')
    for s in SC:
        up = {k: [b[s][k], r[s][k]] for k in M if r[s][k] > b[s][k]}
        if up:
            regressions.append(dict(group=g, case=c, domain=dom, stop=stop, variant=var, arm=arm, score=s,
                                    increased=up, baseline_verdict=b[s]['verdict'], arm_verdict=r[s]['verdict'],
                                    verdict_lost=b[s]['verdict'] == 'PASS' and r[s]['verdict'] == 'FAIL'))

P = {}
# P1
p1a = [(c, stop, s, get('fixture', c, 'map32', stop, 'framework', 'H-P')[s]['verdict'])
       for c in ('integer', 'fractional') for stop in ('5it', '50it') for s in SC]
p1b = [(c, stop, s, get('fixture', c, 'map32', stop, 'framework', 'H-D')[s]['verdict'])
       for c in ('integer', 'fractional') for stop in ('5it', '50it') for s in SC]
P['P1'] = dict(confirmed=all(v == 'FAIL' for *_, v in p1a) and all(v == 'PASS' for *_, v in p1b),
               map32_HP=p1a, map32_HD=p1b)
# P2
p2 = {}
for iv in (0, 1):
    j = d['jacobians'][f'vel{iv}-N5-prod-double-H-P']
    ev = sorted(e[0] for e in j['eigenvalues'])
    p2[f'vel{iv}'] = dict(eigen_min=ev[0], eigen_max=ev[-1], spectral_radius=j['spectral_radius'],
                          max_imag=max(abs(e[1]) for e in j['eigenvalues']))
P['P2'] = dict(confirmed=all(abs(v['eigen_min']+.249565) <= .01 and abs(v['eigen_max']+.228752) <= .01
                             and v['spectral_radius'] < 1 for v in p2.values()), values=p2)
# P3
lost = []
checked = 0
for (g, c, dom, stop, var, arm), r in table.items():
    if g != 'probe' or arm != 'H-D' or c.split('-')[1] not in ('N9', 'N13', 'N20'):
        continue
    b = get(g, c, dom, stop, var, 'S-P')
    for s in SC:
        if passes(b, s):
            checked += 1
            if not passes(r, s):
                lost.append(dict(control=f'{c}-{var}-{stop}', domain=dom, score=s, baseline=b[s], candidate=r[s]))
P['P3'] = dict(confirmed=not lost, baseline_pass_scores_checked=checked, pass_to_fail=lost)
# P4
p4 = {}
for dom in ('double', 'map32'):
    for stop in ('5it', '50it'):
        b = get('probe', 'vel1-N20', dom, stop, 'iso', 'S-P')
        r = get('probe', 'vel1-N20', dom, stop, 'iso', 'H-D')
        p4[f'{dom}-{stop}'] = dict(baseline_rms_px=b['trajectory_error_px']['rms'],
                                   candidate_rms_px=r['trajectory_error_px']['rms'],
                                   nonregression=r['trajectory_error_px']['rms'] <= b['trajectory_error_px']['rms']+1e-6,
                                   baseline_runtime=b['runtime'], baseline_STAR=b['STAR'],
                                   candidate_runtime=r['runtime'], candidate_STAR=r['STAR'],
                                   candidate_iterations=r['run']['iterations'], candidate_guard=r['guard'])
P['P4'] = dict(confirmed=p4['double-5it']['nonregression'] and p4['map32-5it']['nonregression'], values=p4)
# P5
p5 = []
for (g, c, dom, stop, var, arm), r in table.items():
    if dom != 'double' or arm not in ('S-D', 'H-D'):
        continue
    if g == 'fixture' and (c in ('flat', 'repeated') or var != 'framework'):
        continue
    ref = get(g, c, dom, stop, var, 'S-P' if arm == 'S-D' else 'H-P')
    p5.append((maxdiff(traj(r), traj(ref)), f'{g}:{c}-{var}-{stop}-{arm}'))
p5.sort(reverse=True)
P['P5'] = dict(confirmed=p5[0][0] <= 1e-6, compared=len(p5), largest=p5[:5])
# P6
j6 = {a: d['jacobians'][f'vel0-N5-prod-map32-{a}'] for a in ('S-P', 'H-P', 'H-D')}
jd = sorted(e[0] for e in d['jacobians']['vel0-N5-prod-double-H-P']['eigenvalues'])
jm = sorted(e[0] for e in j6['H-D']['eigenvalues'])
ident = {a: max(abs(e[0]-1)+abs(e[1]) for e in j6[a]['eigenvalues']) for a in ('S-P', 'H-P')}
P['P6'] = dict(confirmed=all(v <= 1e-6 for v in ident.values()) and max(abs(x-y) for x, y in zip(jd, jm)) <= .05,
               pedestal_identity_max_deviation=ident, map32_HD_eigen=[jm[0], jm[-1]], double_HP_eigen=[jd[0], jd[-1]],
               max_eigen_gap=max(abs(x-y) for x, y in zip(jd, jm)))
# P7
p7 = [(c, stop, s, get('fixture', c, 'double', stop, 'framework', 'H-P')[s]['verdict'])
      for c in ('integer', 'fractional') for stop in ('5it', '50it') for s in SC]
P['P7'] = dict(confirmed=all(v == 'PASS' for *_, v in p7), values=p7)
# P8
b = get('fixture', 'noisy', 'map32', '5it', 'framework', 'S-P')
r = get('fixture', 'noisy', 'map32', '5it', 'framework', 'H-D')
P['P8'] = dict(confirmed=all(r[s][k] > b[s][k] for s in SC for k in ('rms', 'max')),
               baseline={s: b[s] for s in SC}, candidate={s: r[s] for s in SC})

guard = {}
for (g, c, dom, stop, var, arm), r in table.items():
    if arm in ('H-P', 'H-D'):
        k = f'{g}-{dom}-{arm}'
        a = guard.setdefault(k, dict(peaks=0, not_negative_definite=0, offset_gt_1px=0))
        if var in ('framework', 'prod', 'iso'):
            for x in a:
                a[x] += r['guard'][x]
guard_rows = sorted({(f'{g}:{c}-{var}-{stop}', dom, arm): r['guard'] for (g, c, dom, stop, var, arm), r in table.items()
                     if arm in ('H-P', 'H-D') and r['guard']['not_negative_definite']+r['guard']['offset_gt_1px']}.items())

out = dict(source_sha256=hashlib.sha256(raw).hexdigest(), predictions=P, regressions=regressions,
           regression_counts={a: sum(1 for x in regressions if x['arm'] == a) for a in ARMS[1:]},
           verdict_losses=[x for x in regressions if x['verdict_lost']], guard_totals=guard,
           guard_fired_rows=[dict(row=k[0], domain=k[1], arm=k[2], **v) for k, v in guard_rows],
           script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
p = W6/'results/scorecard.json'
p.write_text(json.dumps(out, indent=1)+'\n')


# Markdown tables for the README.
def cell(r):
    return ' / '.join(f'{r[s]["rms"]:.6f} {r[s]["p95"]:.6f} {r[s]["max"]:.6f} {r[s]["verdict"][0]}' for s in SC)


md = ['## Fixtures (runtime / STAR: RMS p95 max Å, P/F)', '',
      '| Case | Domain | Stop | S-P | S-D | H-P | H-D |', '|---|---|---|---|---|---|---|']
for case in d['cases']:
    for dom in ('double', 'map32'):
        for stop in ('5it', '50it'):
            for var in ('framework', 'patch-native'):
                if (g := ('fixture', case, dom, stop, var, 'S-P')) not in table:
                    continue
                lbl = stop + ('' if var == 'framework' else ' patch-native')
                md.append(f'| {case} | {dom} | {lbl} | ' + ' | '.join(cell(get('fixture', case, dom, stop, var, a)) for a in ARMS) + ' |')
md += ['', '## Phase-ramp controls (runtime / STAR: RMS p95 max Å, P/F)', '',
       '| Control | Domain | S-P | S-D | H-P | H-D |', '|---|---|---|---|---|---|']
for iv in (0, 1):
    for N in (5, 9, 13, 20):
        for w in ('prod', 'iso'):
            for stop in ('5it', '50it'):
                for dom in ('double', 'map32'):
                    c = f'vel{iv}-N{N}'
                    md.append(f'| {c}-{w}-{stop} | {dom} | ' + ' | '.join(cell(get('probe', c, dom, stop, w, a)) for a in ARMS) + ' |')
md += ['', '## H-D regressions versus same-domain S-P (every increase, no threshold)', '',
       '| Row | Domain | Score | Increased metrics (S-P -> H-D, Å) | Verdict S-P -> H-D |', '|---|---|---|---|---|']
for x in regressions:
    if x['arm'] != 'H-D':
        continue
    inc = ', '.join(f'{k} {a:.6f} -> {b:.6f}' for k, (a, b) in x['increased'].items())
    md.append(f'| {x["group"]}:{x["case"]}-{x["variant"]}-{x["stop"]} | {x["domain"]} | {x["score"]} | {inc} | '
              f'{x["baseline_verdict"]} -> {x["arm_verdict"]} |')
(W6/'results/tables.md').write_text('\n'.join(md)+'\n')
print(json.dumps({k: v['confirmed'] for k, v in P.items()}), out['regression_counts'], len(out['verdict_losses']))
