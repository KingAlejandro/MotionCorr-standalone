"""Formats observation_residual.json into Markdown tables. Rendering only: no new numerical quantity is computed here."""
import json, sys
from pathlib import Path
sys.dont_write_bytecode = True
OUT = Path(sys.argv[1]).resolve()
D = json.loads((OUT / 'observation_residual.json').read_text())
f = lambda v: '%.6f' % v
e3 = lambda v: '%.3e' % v
CASES, ARMS = ('noisy', 'affine', 'pedestal'), ('OFF', 'ON')
FS = ('native_runtime_coeff', 'legacy_coeff', 'B2_coeff')
FSN = {'native_runtime_coeff': 'native runtime coeff', 'legacy_coeff': 'legacy refit coeff', 'B2_coeff': 'B2 refit coeff'}
pt = lambda p: '(%d,%d)' % tuple(p)
L = []
w = L.append
w('# Observation-residual diagnostic: tables (descriptive; no thresholds, no gate, no acceptance)\n')
w('Units: px unless stated. Patch = centre (x,y). g = 0..4 is stored STAR frame g+1. Definitions are frozen in `PLAN.md`: y stored observation; H = unchanged truth(centre,g) - runtime G[g]; TrH = H + 0.5*H[:,1]; e_Tr = y - TrH; s = y - y[:,0]; eta = s - H. '
  'RMS is the root mean square of the vector norm; signed means are per component. `eta` at g=0 is identically 0 by construction; `e_Tr` at g=0 is the observed reference offset/nuisance, not evidence about frame-0 noise. STAR observations carry 5-decimal rounding (5e-6 px/axis half-unit).\n')

w('## T0 Structure, closure and linked sealed metrics\n')
w('| case/arm | patches | excluded (no obs) | G3 max |y1-3 y0| | closure max abs (eta-(e_Tr-e_Tr0)) | sealed ROI Å native runtime rms/p95/max | sealed legacy refit R_rt | sealed B2 refit R_rt |')
w('|---|---|---|---|---|---|---|---|')
for c in CASES:
    for a in ARMS:
        e = D['cases'][f'{c}/{a}']; m = e['sealed_roi_metrics_A_linked_not_rescored']
        t = lambda d: '%.4f / %.4f / %.4f' % (d['rms'], d['p95'], d['max'])
        w(f"| {c}/{a} | {e['n_patches']} | {', '.join(pt(p) for p in e['excluded_no_observation']) or 'none'} | {e3(e['G3_max_px'])} | {e3(e['closure_max_abs_px'])} | {t(m['native_runtime'])} | {t(m['offline_legacy_R_rt'])} | {t(m['offline_B2_R_rt'])} |")
w('\nSealed ROI metrics are copied from the sealed `stage2_result.json` (not rescored, not replaced). They are dense fixed-ROI field accuracy; the point-centre quantities below are a different estimand.\n')

w('## T1 Excluded patch and iteration criterion (separate from truth)\n')
w('| case | patch | arm | in STAR | iterations | final RMSD px | sequence |')
w('|---|---|---|---|---|---|---|')
for c in CASES:
    for a in ARMS:
        for lp in D['cases'][f'{c}/{a}']['log_patches']:
            w(f"| {c} | {pt(lp['centre'])} | {a} | {'yes' if lp['accepted_in_star'] else '**no (excluded, no observation, not imputed)**'} | {lp['n_iterations']} | {f(lp['final_rmsd_px'])} | {' > '.join('%g' % v for v in lp['iterations'])} |")
w('\nThese are the log RMSD iteration values only. No point-truth claim is attached to them.\n')

w('## T2 Per-patch, per-frame values (all accepted patches, all frames)\n')
for c in CASES:
    for a in ARMS:
        e = D['cases'][f'{c}/{a}']
        w(f'### {c}/{a}  (G runtime: ' + '; '.join('(%s, %s)' % (f(v[0]), f(v[1])) for v in e['G']) + ')\n')
        w('| patch | g | y x | y y | \\|y\\| | H x | H y | \\|H\\| | TrH x | TrH y | \\|TrH\\| | e_Tr x | e_Tr y | \\|e_Tr\\| | s x | s y | \\|s\\| | eta x | eta y | \\|eta\\| |')
        w('|' + '---|' * 20)
        for p, pa in enumerate(e['patches']):
            for g in range(5):
                row = [pt(pa), str(g)]
                for q in ('y', 'H', 'TrH', 'e_tr', 's', 'eta'):
                    v = e[q][p][g]; row += [f(v[0]), f(v[1]), f(e[q + '_norm'][p][g])]
                w('| ' + ' | '.join(row) + ' |')
        w('')

def per_frame_table(title, getter, case_arm_list=None):
    w(f'## {title}\n')
    w('| case/arm | g | n | RMS | max | mean x | mean y | RMS x | RMS y |')
    w('|---|---|---|---|---|---|---|---|---|')
    for c in CASES:
        for a in ARMS:
            blk = getter(D['cases'][f'{c}/{a}'])['per_frame']
            for g in range(5):
                s = blk[str(g)]
                w(f"| {c}/{a} | {g}{' (endpoint)' if g == 4 else ''} | {s['n']} | {f(s['rms'])} | {f(s['max'])} | {f(s['mean_x'])} | {f(s['mean_y'])} | {f(s['rms_x'])} | {f(s['rms_y'])} |")
    w('')
per_frame_table('T3a Per-frame summary across patches: H (truth - G at centres)', lambda e: e['H_block'])
per_frame_table('T3b Per-frame summary: e_Tr (operator Tr gauge)', lambda e: e['e_tr_block'])
per_frame_table('T3c Per-frame summary: eta (physical recentered gauge)', lambda e: e['eta_block'])
for fs in FS:
    per_frame_table(f'T3d Per-frame summary: fitted published field minus H at centres, {FSN[fs]} (estimand differs from dense ROI accuracy)', lambda e, fs=fs: e['fitted'][fs]['block'])

w('## T4 Overall summaries and the g=4 endpoint (g1-3 versus g4 kept separate)\n')
w('| quantity | case/arm | set | n | RMS | max | mean x | mean y |')
w('|---|---|---|---|---|---|---|---|')
quant = [('e_Tr', lambda e: e['e_tr_block'], ('g0_4', 'g1_4', 'g1_3', 'g4')), ('eta', lambda e: e['eta_block'], ('g1_4', 'g1_3', 'g4'))] + \
        [(f'fit-H {FSN[fs]}', (lambda e, fs=fs: e['fitted'][fs]['block']), ('g1_4', 'g1_3', 'g4')) for fs in FS]
for name, getter, sets in quant:
    for c in CASES:
        for a in ARMS:
            for st in sets:
                s = getter(D['cases'][f'{c}/{a}'])['overall'][st]
                w(f"| {name} | {c}/{a} | {st} | {s['n']} | {f(s['rms'])} | {f(s['max'])} | {f(s['mean_x'])} | {f(s['mean_y'])} |")
w('')

w('## T5 Per-patch summaries (frames g=1..4; g4 alone in the last column)\n')
w('| quantity | case/arm | patch | RMS g1-4 | max g1-4 | mean x | mean y | RMS g1-3 | RMS g4 |')
w('|---|---|---|---|---|---|---|---|---|')
pq = [('e_Tr', lambda e: e['e_tr_block']), ('eta', lambda e: e['eta_block'])] + [(f'fit-H {FSN[fs]}', (lambda e, fs=fs: e['fitted'][fs]['block'])) for fs in FS]
for name, getter in pq:
    for c in CASES:
        for a in ARMS:
            e = D['cases'][f'{c}/{a}']
            for p, pa in enumerate(e['patches']):
                s = getter(e)['per_patch'][p]
                w(f"| {name} | {c}/{a} | {pt(pa)} | {f(s['g1_4']['rms'])} | {f(s['g1_4']['max'])} | {f(s['g1_4']['mean_x'])} | {f(s['g1_4']['mean_y'])} | {f(s['g1_3']['rms'])} | {f(s['g4']['rms'])} |")
w('')

w('## T6 Arm changes, full-width ON minus old-weight OFF (same patches; no causal share is attributed)\n')
for c in CASES:
    ch = D['arm_changes'][c]
    w(f"### {c}: common patches {len(ch['common_patches'])}; only OFF {ch['only_OFF']}; only ON {ch['only_ON']}; runtime G equal: {ch['G_equal']}\n")
    w('| quantity | set | RMS OFF | RMS ON | RMS of (ON-OFF) vector | max of (ON-OFF) | mean x of (ON-OFF) | mean y of (ON-OFF) |')
    w('|---|---|---|---|---|---|---|---|')
    for q in ('e_tr', 'eta') + tuple('fit:' + s for s in FS):
        for st in ('g1_4', 'g1_3', 'g4'):
            o = ch[q]['overall'][st]
            w(f"| {q} | {st} | {f(o['rms_OFF'])} | {f(o['rms_ON'])} | {f(o['delta']['rms'])} | {f(o['delta']['max'])} | {f(o['delta']['mean_x'])} | {f(o['delta']['mean_y'])} |")
    w('\nPer frame (RMS across common patches):\n')
    w('| quantity | g | RMS OFF | RMS ON | RMS of (ON-OFF) |')
    w('|---|---|---|---|---|')
    for q in ('e_tr', 'eta') + tuple('fit:' + s for s in FS):
        for g in range(5):
            o = ch[q]['per_frame'][str(g)]
            w(f"| {q} | {g} | {f(o['rms_OFF'])} | {f(o['rms_ON'])} | {f(o['delta']['rms'])} |")
    w('\nPer patch (g=1..4):\n')
    w('| quantity | patch | RMS OFF | RMS ON | RMS of (ON-OFF) |')
    w('|---|---|---|---|---|')
    for q in ('e_tr', 'eta') + tuple('fit:' + s for s in FS):
        for o in ch[q]['per_patch']:
            w(f"| {q} | {pt(o['patch'])} | {f(o['rms_OFF_g1_4'])} | {f(o['rms_ON_g1_4'])} | {f(o['delta_g1_4']['rms'])} |")
    w('')

R_ = []
r = R_.append
r('# Full ranked lists (not threshold-filtered)\n')
r('Each list is every patch/frame row, sorted by descending vector norm (px). eta lists start at g=1 because eta at g=0 is identically zero; e_Tr lists include g=0.\n')
for c in CASES:
    for a in ARMS:
        e = D['cases'][f'{c}/{a}']
        r(f'## {c}/{a}\n')
        lists = [('eta (g1-4)', e['rank_eta_g1_4']), ('e_Tr (g0-4)', e['rank_e_tr_g0_4'])] + [(f'fit-H {FSN[fs]} (g1-4)', e['fitted'][fs]['rank_g1_4']) for fs in FS]
        for name, rows in lists:
            r(f'**{name}**: ' + '; '.join('%s g%d %s' % (pt(x['patch']), x['g'], f(x['norm'])) for x in rows) + '\n')
        for name, rows in [('patch RMS eta (g1-4)', e['rank_patch_eta_rms']), ('patch RMS e_Tr (g1-4)', e['rank_patch_e_tr_rms'])] + [(f'patch RMS fit-H {FSN[fs]} (g1-4)', e['fitted'][fs]['rank_patch_rms']) for fs in FS]:
            r(f'**{name}**: ' + '; '.join('%s %s' % (pt(x['patch']), f(x['norm'])) for x in rows) + '\n')
    r('')
for c in CASES:
    ch = D['arm_changes'][c]
    r(f'## {c}: ON minus OFF change of vector norm, ranked by absolute change\n')
    for q in ('e_tr', 'eta') + tuple('fit:' + s for s in FS):
        r(f'**{q}**: ' + '; '.join('%s g%d %s (OFF %s, ON %s)' % (pt(x['patch']), x['g'], '%+.6f' % x['change'], f(x['norm_OFF']), f(x['norm_ON'])) for x in ch[q]['rank_change_of_norm']) + '\n')

env = D['environment']
w('## Run environment\n')
w(f"Python {env['python']}, NumPy {env['numpy']}, threads {env['threads']}, wall {env['wall_s']:.2f} s, peak RSS {env['peak_rss_bytes']/1e6:.1f} MB (ru_maxrss bytes on macOS), platform {env['platform']}. Sealed status unchanged: {D['sealed_status_unchanged']}.\n")
(OUT / 'RESULT_TABLES.md').write_text('\n'.join(L) + '\n')
(OUT / 'RANKED_LISTS.md').write_text('\n'.join(R_) + '\n')
print('tables written', len(L), len(R_))
