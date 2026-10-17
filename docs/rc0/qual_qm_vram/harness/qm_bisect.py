#!/usr/bin/env python3
"""Bisect the minimum free VRAM (GiB, on GPU1 under the balloon) for a case.

usage: qm_bisect.py <fam> <cfg> <ingest> <resident|completes> <lo_fail_gib> <hi_pass_gib> [tol_gib=1.0]

Predicate resident : exit 0, products complete, witness != float, no 'falling back to streaming' warning.
Predicate completes: exit 0, all products present.
lo is assumed failing and hi passing (both are re-verified if not already measured in this call).
All probes are real runs written under runs/bisect-<fam>-<cfg>-<ing>-<pred>@<free>.
"""
import json, re, sys
sys.path.insert(0, '/mnt/clathrin/alex-motioncorr-rc0/W-QM')
import qm_batch as q

fam, cfg, ing, pred, lo, hi = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5]), float(sys.argv[6])
tol = float(sys.argv[7]) if len(sys.argv) > 7 else 1.0
fams = q.families()


def ensure_baseline():
    if not (q.baseline_dir(fam, cfg, ing) / 'result.json').exists():
        print('  baseline', flush=True)
        q.run_case(f'{fam}-{cfg}-{ing}@none', fams)


def probe(g):
    ensure_baseline()
    spec = f'{fam}-{cfg}-{ing}@{g:g}:bis{pred[:3]}'
    r = q.run_case(spec, fams)
    warn = any('falling back to streaming' in l for ls in r['log_lines'].values() for l in ls)
    route = (r['witness'][-1].split()[-1] if r['witness'] else None)
    ok = r['exit'] == 0 and r['all_products'] and (pred == 'completes' or (route != 'float' and not warn))
    c = r.get('compare', {})
    print(f"  probe {g:g} GiB -> {'PASS' if ok else 'FAIL'} exit={r['exit']} route={route} fallback_warn={warn} wall={r['wall_s']}s "
          f"free_meas={r['free_vram_after_balloon_mib']}MiB products_rc={c.get('products_rc')} strict_rc={c.get('strict_rc')}", flush=True)
    return ok, r


results = {}
for g in (hi, lo):
    ok, r = probe(g)
    results[g] = ok
if not results[hi]:
    print('hi is not passing; abort', flush=True)
    sys.exit(3)
if results[lo]:
    print('lo already passes; floor <= lo', flush=True)
    sys.exit(0)
while hi - lo > tol + 1e-9:
    mid = round((lo + hi) / 2 * 2) / 2  # 0.5 GiB grid
    if mid <= lo or mid >= hi:
        break
    ok, r = probe(mid)
    if ok:
        hi = mid
    else:
        lo = mid
print(f'FLOOR {fam}-{cfg}-{ing} {pred}: fails at {lo:g} GiB free, passes at {hi:g} GiB free (tol {tol:g})', flush=True)
