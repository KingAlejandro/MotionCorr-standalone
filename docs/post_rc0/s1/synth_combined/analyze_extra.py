#!/usr/bin/env python3
"""Controls, #270 image effect and #267 tables. usage: analyze_extra.py DATA OUTDIR"""
import json, pathlib, sys
import numpy as np
REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path[:0] = [str(REPO/'tools')]
from summarize_realistic_motion import paired
data, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]); out.mkdir(exist_ok=True, parents=True)
J = lambda p: json.loads(p.read_text()); md = []
f3 = lambda x: f'{x:.3f}'
# controls
md.append('### Image-check controls (seed 0 of every condition; 1536x1536 interior crop; transfer per band .01-.04/.04-.08/.08-.12/.12-.16)\n\n|Condition|Control|Transfer by band|FRC by band|in-band relRMSE|pixel relRMSE|\n|---|---|---|---|---:|---:|')
for p in sorted((data/'controls').glob('*.json')):
    d = J(p)
    for k in ('truth_vs_truth', 'oracle', 'zero', 'wrong_sign'):
        m = d[k]; md.append(f"|{d['fixture'].rsplit('-s',1)[0]}|{k}|{' / '.join(f3(b['transfer']) for b in m['bands'])}|{' / '.join(f3(b['frc']) for b in m['bands'])}|{f3(m['relrmse_inband'])}|{f3(m['pixel_relrmse']) if 'pixel_relrmse' in m else '—'}|")
# #270 effect
eff = J(data/'effect270.json') if (data/'effect270.json').exists() else []
if eff:
    ident = sum(r['bytes_identical'] for r in eff)
    md.append(f'\n### #270 image effect (CUDA DC none; with #270 minus without), {len(eff)} movies, {ident} with byte-identical sums\n')
    md.append('|Distance to edge px|median RMS change (/scene std)|max |change| over movies|median d(sq.err) per movie (/scene var; <0 better)|movies better/worse/tie|sign p|\n|---|---:|---:|---:|---|---:|')
    keys = [tuple(b['distance_px']) for b in eff[0]['bins']]
    for k in keys:
        rows = [b for r in eff for b in r['bins'] if tuple(b['distance_px']) == k]
        d = np.array([b['d_sq_error'] for b in rows]); w = int((d < -1e-9).sum()); l = int((d > 1e-9).sum()); ties = len(d)-w-l
        pv = paired(np.zeros(len(d)), d)['sign_test_two_sided_p']
        md.append(f"|{k[0]}-{k[1] if k[1] < 10**6 else 'end'}|{np.median([b['rms_change'] for b in rows]):.3g}|{max(b['max_abs_change'] for b in rows):.3g}|{np.median(d):.3g}|{w}/{l}/{ties}|{pv:.3g}|")
# #267
md.append('\n### #267 eight cases: main (36913740, #269 published) vs combined build; field RMS px (checker status)\n\n|Backend|Case|main|combined DC none|combined DC both|\n|---|---|---|---|---|')
main = {(r['backend'], r['case']): r for r in J(REPO/'docs/post_rc0/s1/km_truth/native_v2_metrics.json')}
tags = {t: J(data/'v2'/f'v2-comb-{t}.eval.json') for t in ('cpu-none', 'cpu-both', 'cuda-none', 'cuda-both') if (data/'v2'/f'v2-comb-{t}.eval.json').exists()}
for be in ('cpu', 'cuda'):
    for case in ['zero', 'integer', 'fractional', 'affine', 'pedestal', 'noisy', 'flat', 'repeated']:
        m = main[(be, case)]; cells = [f"{m['field_px']['rms']:.4f} ({m['original_checker_status']})"]
        for dc in ('none', 'both'):
            r = next((x for x in tags.get(f'{be}-{dc}', []) if x['case'] == case), None)
            cells.append('—' if r is None else f"{r['field_px']['rms']:.4f} ({r['checker_status']})")
        md.append(f'|{be}|{case}|' + '|'.join(cells) + '|')
(out/'extra_tables.md').write_text('\n'.join(md)+'\n'); print('\n'.join(md))
