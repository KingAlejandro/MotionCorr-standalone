#!/usr/bin/env python3 -I
"""Aggregate W-QM runs: per-case verdict, log-diff residual after a declared whitelist, stray-file check."""
import json, glob, os, re, sys, collections
R = '/mnt/clathrin/alex-motioncorr-rc0/W-QM/runs'
OUT = sys.argv[1] if len(sys.argv) > 1 else '/mnt/clathrin/alex-motioncorr-rc0/W-QM/final'
os.makedirs(OUT, exist_ok=True)
DROP = ('Full movie wall time', 'execution time:', 'transfer time:', 'Total GPU alignment time:', 'Kernel:', ' ms')
WL = [r'^Batched patch alignment', r'^Batched alignment', r'^Buffer VRAM', r'^cuFFT workspace VRAM', r'^Peak GPU memory',
      r'^Peak VRAM', r'^Buffer placement', r'^Movie FFT:', r'^nvCOMP ingestion', r'^Staging this movie', r'^Released native',
      r'^Materialized native', r'^Computing full-frame Fourier', r'^Reconstructing globally aligned',
      r'^Dose weighting and summing', r'^Summing frames before', r'^Dose-weighting scratch', r'^ERROR: Movie buffer allocation', r'^ERROR: Movie FFT scratch allocation',
      r'^WARNING: Failed to initialize CUDA movie session', r'^CUDA Error in ', r'^WARNING: CUDA ', r'^WARNING: resident ',
      r'^Device ingestion failed', r'^Written aligned', r'^Written ', r'^Fixed hot pixels', r'^Per-kernel timing', r'^\[CUDA ',
      r'^Resident ', r'^Staged ', r'^Mapped ', r'^Host ', r'device memory', r'^Using ', r'^Movie size']
WLRE = [re.compile(p) for p in WL]


def read_lines(p):
    if not os.path.exists(p):
        return None
    return [l.strip() for l in open(p, errors='replace') if l.strip() and not any(m in l for m in DROP)]


def norm(l):
    return re.sub(r'\d+(\.\d+)?', '#', l)


def residual(base_log, cand_log):
    a, b = read_lines(base_log), read_lines(cand_log)
    if a is None or b is None:
        return None
    sa, sb = set(a), set(b)
    res = [l for l in a if l not in sb] + [l for l in b if l not in sa]
    return [l for l in res if not any(r.search(l) for r in WLRE)]


rows = []
resid_all = {}
for p in sorted(glob.glob(R + '/*/result.json')):
    d = os.path.dirname(p)
    cid = os.path.basename(d)
    r = json.load(open(p))
    c = r.get('compare', {})
    stems = [os.path.basename(m).rsplit('.', 1)[0] for m in r['movies']]
    free = r['free_vram_after_balloon_mib']
    is_base = r['target_free_gib'] is None
    route = [w.split()[-1] for w in r['witness']]
    texts = ' '.join(l for ls in r['log_lines'].values() for l in ls)
    flags = []
    if 'falling back to streaming' in texts: flags.append('session-init-OOM->streaming')
    if 'Falling back to CPU preprocessing' in texts: flags.append('gain/sum-OOM->CPU-preprocess')
    if 'Device ingestion failed recoverably' in texts: flags.append('device-ingest-declined->host-reader')
    if 'resident patch preparation did not complete' in texts or 'CUDA patch preparation declined' in texts or 'resident retry preparation did not complete' in texts: flags.append('patch-prep-declined')
    # product identity
    if 'per_movie' in c:
        ident = {s: (e.get('products_rc'), e.get('strict_rc')) for s, e in c['per_movie'].items()}
        prod_ident = all(v[0] == 0 for v in ident.values() if v[0] is not None)
        n_present = sum(1 for e in c['per_movie'].values() if e['candidate_products_present'])
    else:
        ident = (c.get('products_rc'), c.get('strict_rc'))
        prod_ident = c.get('products_rc') == 0 if not is_base else None
        n_present = 1 if r['all_products'] else 0
    # strict residual after whitelist
    res_lines = None
    if not is_base and r['exit'] == 0:
        res_lines = []
        for s in stems:
            base = f"{R}/{r['family']}-{r['config']}-{r['ingest']}@none/out/Movies/{s}.log"
            x = residual(base, f'{d}/out/Movies/{s}.log')
            if x is None:
                x = ['<missing log>']
            res_lines += x
        resid_all[cid] = res_lines
    # failure cleanliness
    failure = None
    if r['exit'] != 0:
        stray = []
        for f in glob.glob(d + '/out/**', recursive=True):
            if os.path.isfile(f):
                rel = os.path.relpath(f, d + '/out')
                if not (rel.startswith('Movies/') and rel.endswith('.log')) and rel not in ('manifest.json',):
                    stray.append(rel)
        so = open(d + '/stdout.txt', errors='replace').read()
        named = 'Motion correction failed for' in so
        oom_line = next((l.strip() for l in so.splitlines() if 'out of memory in' in l or 'No space' in l), None)
        failure = {'exit': r['exit'], 'named_movie_failure_line': named, 'oom_line': oom_line,
                   'stray_files_besides_log': [s for s in stray if not s.endswith('.log')],
                   'gpu_used_after_mib': r['gpu_used_after_mib'], 'gpu_apps_after': r['gpu_apps_after'],
                   'signal_exit': r['exit'] > 128, 'timed_out': r['timed_out']}
    rows.append({'case': cid, 'spec': r['spec'], 'family': r['family'], 'config': r['config'], 'ingest': r['ingest'],
                 'free_mib': free, 'exit': r['exit'], 'timed_out': r['timed_out'], 'route': route, 'flags': flags,
                 'wall_s': r['wall_s'], 'peak_over_baseline_mib': r['sampled']['peak_motioncorr_above_baseline_mib'],
                 'peak_compute_app_mib': r['sampled']['peak_compute_app_mib'], 'max_rss_mib': r['max_rss_mib'],
                 'all_products': r['all_products'], 'movies_with_products': n_present, 'n_movies': len(stems),
                 'products_identical': prod_ident, 'identity_rc(products,strict)': ident,
                 'strict_log_residual_after_whitelist': (len(res_lines) if res_lines is not None else None),
                 'failure': failure, 'bench_lock_wait_s': r['bench_lock_wait_s'], 'balloon_gone': r['balloon_gone']})
json.dump(rows, open(OUT + '/cases.json', 'w'), indent=1)
json.dump({k: v[:10] for k, v in resid_all.items() if v}, open(OUT + '/log_residuals.json', 'w'), indent=1)
bad = {k: v for k, v in resid_all.items() if v}
print('cases:', len(rows), ' completed non-baseline cases with non-whitelisted log differences:', len(bad))
for k, v in list(bad.items())[:12]:
    print(' ', k, v[:3])
