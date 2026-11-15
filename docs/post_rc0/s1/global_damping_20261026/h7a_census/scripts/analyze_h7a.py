#!/usr/bin/env python3
"""Score H7a against the frozen predictions. usage: analyze_h7a.py RESULTS_DIR OUT_PREFIX
RESULTS_DIR holds census.json (rows from h7a_census.py) and runs/<movie>/{F,C}/ (STAR, log, metrics.json, stdout.log, RUN.json).
Truth scoring is tools/check_realistic_motion.py (unchanged): runtime field = full-precision capture, STAR = serialized; limits 0.20 / 0.40 / 0.80 A.
"""
import json, math, pathlib, re, sys
R = pathlib.Path(sys.argv[1]); out = sys.argv[2]
d = json.loads((R/'census.json').read_text()); rows = d['rows']
GOOD = [192, 216, 256, 288, 324, 384, 432, 486, 512, 576, 648, 768, 800, 864, 972, 1024, 1296, 1536, 1728, 1944, 2048, 2304, 2592, 3072, 3200, 3456, 3888, 4096, 4608, 5000, 5184, 6144, 6250, 6400, 6912, 7776, 8192, 9216, 10240, 12288, 12500]
def good(n):
    for g in GOOD:
        if g >= n: return g
    return n
def ccf(n, B=150.0):
    s = math.sqrt(-math.log(1e-8)/(2*B)); c = min(good(int(n*s)), n); return c + c % 2
def patch_crops(movie):
    t = (R/'runs'/movie/'F'/'output/movie.log').read_text(); res = []
    for m in re.finditer(r'X range = \[(\d+), (\d+)\), Y range = \[(\d+), (\d+)\)', t):
        w, h = int(m.group(2))-int(m.group(1)), int(m.group(4))-int(m.group(3)); res.append((w, h, ccf(w), ccf(h)))
    return res
def sign_test(k, n):
    if n == 0: return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(k, n-k)+1)); return min(1.0, 2*tail/2**n)
ok = [r for r in rows if 'F' in r and 'C' in r and r['F'].get('exit') == 0 and r['C'].get('exit') == 0 and 'field_runtime' in r['F'] and 'field_runtime' in r['C']]
res = dict(n_rows=len(rows), n_scored_pairs=len(ok), binary_sha256=d['binary_sha256'])
res['skipped_or_errors'] = [dict(movie=r['movie'], note=r.get('error') or r.get('skipped') or r.get('stop')) for r in rows if r not in ok]
# identity of F with the C1 K269 CPU census
res['identity'] = dict(F_star_equals_c1=sum(r['F'].get('star_equals_c1_census') is True for r in rows if 'F' in r), F_payload_equals_c1=sum(r['F'].get('payload_equals_c1_census') is True for r in rows if 'F' in r),
                       of=sum('F' in r for r in rows), mismatches=[r['movie'] for r in rows if 'F' in r and r['F'].get('star_equals_c1_census') is not True])
res['movie_hash_equals_receipt'] = sum(r.get('movie_sha256_equals_receipt') is True for r in rows)
res['sources'] = {k: sum(r.get('source', '').startswith(k) for r in rows) for k in ('retained', 'regenerated')}
# prediction 1: paired sign test on runtime field RMS (and STAR as a check)
def paired(key):
    lower = sum(1 for r in ok if r['C'][key]['rms'] < r['F'][key]['rms']); higher = sum(1 for r in ok if r['C'][key]['rms'] > r['F'][key]['rms'])
    ties = len(ok)-lower-higher; return dict(C_lower=lower, C_higher=higher, ties=ties, p_two_sided_exact=sign_test(lower, lower+higher))
res['p1_runtime'] = paired('field_runtime'); res['p1_star'] = paired('field_star')
# prediction 2: movies meeting all three limits
def passes(r, arm, key):
    m = r[arm][key]; return m['rms'] <= .20 and m['p95'] <= .40 and m['max'] <= .80
res['p2'] = {rep: dict(F=sum(passes(r, 'F', key) for r in ok), C=sum(passes(r, 'C', key) for r in ok)) for rep, key in (('runtime', 'field_runtime'), ('STAR', 'field_star'))}
# prediction 3: F pass and C fail, listed individually
harm = []; gain = []
for r in ok:
    for rep, key in (('runtime', 'field_runtime'), ('STAR', 'field_star')):
        if passes(r, 'F', key) and not passes(r, 'C', key):
            harm.append(dict(movie=r['movie'], rep=rep, F=[r['F'][key][k] for k in ('rms', 'p95', 'max')], C=[r['C'][key][k] for k in ('rms', 'p95', 'max')]))
        if not passes(r, 'F', key) and passes(r, 'C', key): gain.append(dict(movie=r['movie'], rep=rep))
res['p3_harm_F_pass_C_fail'] = harm; res['p3_harm_movies_runtime'] = sorted({h['movie'] for h in harm if h['rep'] == 'runtime'}); res['gain_F_fail_C_pass'] = gain
# prediction 4: guard fire rates (C arm; F has no H2)
gg = [0, 0]; gp = [0, 0]; per_movie = []
for r in ok:
    g = r['C']['guard_fired_over_peaks']; gg[0] += g['global'][0]; gg[1] += g['global'][1]; gp[0] += g['patch'][0]; gp[1] += g['patch'][1]
    per_movie.append(dict(movie=r['movie'], global_rate=g['global'][0]/g['global'][1] if g['global'][1] else None, patch_rate=g['patch'][0]/g['patch'][1] if g['patch'][1] else None))
res['p4'] = dict(global_fired=gg[0], global_peaks=gg[1], global_rate=gg[0]/gg[1] if gg[1] else None, patch_fired=gp[0], patch_peaks=gp[1], patch_rate=gp[0]/gp[1] if gp[1] else None,
                 max_movie_global_rate=max((p['global_rate'] or 0) for p in per_movie), max_movie_patch_rate=max((p['patch_rate'] or 0) for p in per_movie),
                 movies_over_5pct=[p['movie'] for p in per_movie if (p['global_rate'] or 0) > .05 or (p['patch_rate'] or 0) > .05])
# prediction 5: exits, dropped patches, convergence changes per movie
ch = []
for r in rows:
    if 'F' not in r or 'C' not in r: continue
    f, c = r['F'], r['C']
    fd = sum(p['converged'] is not True for p in f.get('patches', [])); cd = sum(p['converged'] is not True for p in c.get('patches', []))
    if f.get('exit') != c.get('exit') or fd != cd or f.get('global_converged') != c.get('global_converged') or f.get('global_iterations') != c.get('global_iterations') or f.get('sampling') != c.get('sampling'):
        ch.append(dict(movie=r['movie'], exit=[f.get('exit'), c.get('exit')], dropped_patches=[fd, cd], global_converged=[f.get('global_converged'), c.get('global_converged')],
                       global_iterations=[f.get('global_iterations'), c.get('global_iterations')], sampling=[f.get('sampling'), c.get('sampling')]))
res['p5'] = dict(nonzero_exit=[r['movie'] for r in rows if 'F' in r and (r['F'].get('exit') != 0 or r.get('C', {}).get('exit') != 0)], changes=ch,
                 dropped_patches_F=sum(sum(p['converged'] is not True for p in r['F'].get('patches', [])) for r in ok), dropped_patches_C=sum(sum(p['converged'] is not True for p in r['C'].get('patches', [])) for r in ok),
                 patches_total=sum(r['F']['n_patches'] for r in ok))
# scale report (size, crop, binning)
scale = {}
for r in rows:
    if 'F' not in r: continue
    pc = patch_crops(r['movie']); key = f"{r['nx']}x{r['ny']}x{r['frames']}"
    ent = scale.setdefault(key, dict(movies=0, global_ccf=(r['ccf_global']['ccf_nx'], r['ccf_global']['ccf_ny']), crop=(round(r['ccf_global']['crop_x'], 4), round(r['ccf_global']['crop_y'], 4)),
                                      ccf_px_in_movie_px=[round(v, 3) for v in r['ccf_global']['ccf_pixel_in_movie_px']], patch_dims=sorted({(a, b, c, e) for a, b, c, e in pc}), bin_factor=1, bytes=r['movie_bytes']))
    ent['movies'] += 1
res['scale'] = {k: dict(v, global_ccf=list(v['global_ccf']), crop=list(v['crop']), patch_dims=[list(x) for x in v['patch_dims']]) for k, v in scale.items()}
# per condition summary
cond = {}
for r in ok:
    c = cond.setdefault(r['condition'], dict(n=0, F_rms=[], C_rms=[], F_pass=0, C_pass=0))
    c['n'] += 1; c['F_rms'].append(r['F']['field_runtime']['rms']); c['C_rms'].append(r['C']['field_runtime']['rms']); c['F_pass'] += passes(r, 'F', 'field_runtime'); c['C_pass'] += passes(r, 'C', 'field_runtime')
res['per_condition'] = {k: dict(n=v['n'], F_median_rms=sorted(v['F_rms'])[len(v['F_rms'])//2], C_median_rms=sorted(v['C_rms'])[len(v['C_rms'])//2], F_pass=v['F_pass'], C_pass=v['C_pass']) for k, v in cond.items()}
res['per_movie'] = [dict(movie=r['movie'], condition=r['condition'], size=f"{r['nx']}x{r['ny']}x{r['frames']}", F_runtime=[r['F']['field_runtime'][k] for k in ('rms', 'p95', 'max')], C_runtime=[r['C']['field_runtime'][k] for k in ('rms', 'p95', 'max')],
                    F_gate=r['F']['gate_runtime'], C_gate=r['C']['gate_runtime'], F_star_rms=r['F']['field_star']['rms'], C_star_rms=r['C']['field_star']['rms'],
                    F_patches_ok=sum(p['converged'] is True for p in r['F']['patches']), C_patches_ok=sum(p['converged'] is True for p in r['C']['patches']), n_patches=r['F']['n_patches'],
                    source=r['source']) for r in ok]
pathlib.Path(out+'.json').write_text(json.dumps(res, indent=1, allow_nan=False)+'\n')
L = ['| Movie | Size | F runtime rms / p95 / max | F | C runtime rms / p95 / max | C | patches kept F / C |', '|---|---|---|---|---|---|---|']
for p in res['per_movie']:
    L.append(f"| {p['movie']} | {p['size']} | {p['F_runtime'][0]:.4f} / {p['F_runtime'][1]:.4f} / {p['F_runtime'][2]:.4f} | {p['F_gate']} | {p['C_runtime'][0]:.4f} / {p['C_runtime'][1]:.4f} / {p['C_runtime'][2]:.4f} | {p['C_gate']} | {p['F_patches_ok']} / {p['C_patches_ok']} of {p['n_patches']} |")
pathlib.Path(out+'_per_movie.md').write_text('\n'.join(L)+'\n')
print(json.dumps({k: res[k] for k in ('n_rows', 'n_scored_pairs', 'identity', 'movie_hash_equals_receipt', 'sources', 'p1_runtime', 'p1_star', 'p2', 'p3_harm_movies_runtime', 'p4', 'scale')}, indent=1))
print('P5 changes:', len(ch), '| nonzero exits:', res['p5']['nonzero_exit'], '| dropped patches F/C:', res['p5']['dropped_patches_F'], res['p5']['dropped_patches_C'], 'of', res['p5']['patches_total'])
print('gain F-fail/C-pass (runtime):', sum(1 for g in gain if g['rep'] == 'runtime'))
