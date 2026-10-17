#!/usr/bin/env python3
"""Generate raw/tables.md (markdown tables for the README) from raw/summaries/*.json."""
import glob
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1] / 'raw'
S = R / 'summaries'
ALLOW = ['nvCOMP ingestion', 'Staging this movie as native', 'Released native uint', 'Released native int', 'Materialized native']
out = []

out.append('### Route-invariance (item 3): nvcomp build, `--ingest auto` vs `--ingest float`\n')
out.append('| family | cfg | auto route | float route | CPU build route | products-only identity (MRC hdr+payload, STAR) | strict all-files | route-log allowance (declared prefixes) | other log diffs | peak RSS auto / float / CPU (GiB) |')
out.append('|---|---|---|---|---|---|---|---|---:|---|')
diag = []
for f in sorted(S.glob('campaign/*-[GL].json'), key=lambda p: (['tutorial', 'e10361', 'e10474f3', 'e12963', 'e10216', 'e10028', 'e10164'].index(json.load(open(p))['family']), p.name)):
    d = json.load(open(f))
    a = d['checks']['auto_vs_float']
    ld = a['log_line_diff']
    other = [l for side in ld.values() for l in side
             if not (l.startswith('Written aligned and dose-weighted sum to ') or any(l.startswith(p) for p in ALLOW))]
    wit = {k: r['ingest_witness'][0].split()[-1] for k, r in d['runs'].items()}
    rss = ' / '.join('%.2f' % (d['runs'][k]['max_rss_kib'] / 1048576) for k in ('auto', 'float', 'cpu'))
    pr = 'PASS' if a['products_only_rc'] == 0 else 'FAIL'
    st = 'PASS' if a['strict_all_files_rc'] == 0 else 'differs (route log lines)'
    dc = 'PASS' if a['declared_route_log_allowance_rc'] == 0 else ('PASS*' if not other else 'FAIL')
    out.append(f"| {d['family']} | {d['config']} | {wit['auto']} | {wit['float']} | {wit['cpu']} | {pr} | {st} | {dc} | {len(other)} | {rss} |")
    g = d['checks'].get('cpu_vs_cuda_auto_backend_gate_DIAGNOSTIC_ONLY', {})
    jc = g.get('json_checks', {})
    ci, tr = jc.get('corrected_image', {}), jc.get('motion_trajectory', {})
    diag.append((d['family'], d['config'], g.get('rc'), tr.get('coord_rms_error'), tr.get('max_shift_error'),
                 ci.get('rmse'), ci.get('max_abs_pixel_error'), ci.get('relative_rmse')))
out.append('\n`PASS*` = the comparator, run with the four prefixes declared in advance, still reports a log difference, but the retained '
           'logs show the only extra lines are the signed/int route record `Released native int16/int8 host staging after device forward FFT.` '
           '(added by #195; prefix `Released native int`); there are no other log differences (column "other log diffs" counts lines outside the extended prefix list).\n')

out.append('### CPU-only build vs CUDA `auto` (item 3, `compare_motioncorr.py --gate backend`, DIAGNOSTIC ONLY)\n')
out.append('Backend thresholds: shift RMS 0.02 px, max shift 0.05 px, image RMSE 0.020, max pixel error 5, relative RMSE 0.001 (nonblocking diagnostic).\n')
out.append('| family | cfg | gate exit | shift RMS px | max shift px | image RMSE | max pixel err | relative RMSE |')
out.append('|---|---|---:|---:|---:|---:|---:|---:|')
for d in diag:
    out.append('| %s | %s | %s | %.4f | %.4f | %.4g | %.4g | %.4g |' % d)

out.append('\n### #178 fallback (item 4): 1db86902 CUDA+nvCOMP build vs pre-#178 d7171b81 CUDA+nvCOMP build, both WITHOUT `--gpu`\n')
out.append('| case | options beyond family G/L | CPU witness (cur / pre) | MRC compared | strict tree identity |')
out.append('|---|---|---|---:|---|')
for n in ['noDW-G', 'noDW-L', 'evenodd-G', 'evenodd-L', 'evenodd-23fr-L', 'nodose-G']:
    d = json.load(open(S / f'fallback178/{n}.json'))
    i = d['identity_cur_vs_pre178']['detail']
    w = {k: d['runs'][k]['witness'] for k in ('cur', 'pre178')}
    out.append(f"| {n} | `{' '.join(d['extra_options']) or '(no --dose_weighting)'}` | {w['cur']['cpu_line_count']} / {w['pre178']['cpu_line_count']} CPU lines, {w['cur']['cuda_line_count']} / {w['pre178']['cuda_line_count']} CUDA | {i['mrc_compared']} | {'PASS' if i['identical'] else 'FAIL'} |")
out.append('')
open(R / 'tables.md', 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
