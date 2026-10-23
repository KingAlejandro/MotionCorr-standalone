#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Evaluate #262 four-arm records with the unchanged checkers (FREEZE.md).

  evaluate.py A|B|C|controls|status ROOT

Checkers are imported from ROOT/src (the exact experiment source archive):
Tier A runs docs/post_rc0/s1/synth_combined/eval_v2.py; Tier B uses
tools/check_realistic_motion.py and tools/check_realistic_image.evaluate_sum with
#272's hash-verified truth caches; Tier C uses tools/compare_motioncorr.py
--gate backend for CPU-vs-CUDA and its relative-RMSE formula for arm-vs-none.
A record with a nonzero exit is reported as such and never evaluated as success.
"""
import hashlib, json, os, subprocess, sys
from pathlib import Path
import numpy as np

ROOT = Path(sys.argv[2]).resolve()
SRC = ROOT / 'src'
sys.path[:0] = [str(SRC / 'tools'), str(SRC / 'test-data')]
EVAL = ROOT / 'eval'
EVAL.mkdir(exist_ok=True)
PY = sys.executable
ARMS = ['none', 'global', 'local', 'both']
TRUTH = {(4096, 4096): ('/mnt/clathrin/alex-motioncorr-synth-combined/truth-4096x4096.npy',
                        '6b2733bd516d4c51333fa1981256137d084854cfaca4dd8af90a85be96f18c3b'),
         (5760, 4092): ('/mnt/clathrin/alex-motioncorr-synth-combined/truth-5760x4092.npy',
                        'ff084df764348da7b89626d37963546f0fc11e6ed3912347b0e5e6f532963145')}


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    return h.hexdigest()


def runs(prefix):
    out = {}
    for d in sorted((ROOT / 'runs').glob(prefix + '*')):
        rj = d / 'RUN.json'
        out[d.name] = json.loads(rj.read_text()) if rj.exists() else None
    return out


def read_mrc(path):
    raw = Path(path).read_bytes()
    nx, ny, nz, mode = np.frombuffer(raw[:16], '<i4')
    ext = int(np.frombuffer(raw[92:96], '<i4')[0])
    assert mode == 2
    return np.frombuffer(raw[1024 + ext:], '<f4', count=int(nx) * ny * nz).reshape(nz, ny, nx)


def relrmse(ref, test):
    """compare_motioncorr.py / mc-metrics formula: rms(test-ref) / population std(ref)."""
    a = ref.astype(np.float64); b = test.astype(np.float64)
    return float(np.sqrt(np.mean((b - a) ** 2)) / max(a.std(), 1e-12))


def log_convergence(log):
    import check_realistic_motion as crm
    try: return crm.convergence(log)
    except Exception as e: return dict(error=f'{type(e).__name__}: {e}')


def tier_a():
    rs = runs('A-')
    fixtures = ROOT / 'v2fixtures'
    rows = []
    for backend in ['cpu', 'cuda']:
        for arm in ARMS + ['plain']:
            rd = EVAL / 'A-rundirs' / f'{backend}-{arm}'
            rd.mkdir(parents=True, exist_ok=True)
            entries = []
            for case in ['zero', 'integer', 'fractional', 'affine', 'pedestal', 'noisy', 'flat', 'repeated']:
                rec = rs.get(f'A-{case}-{backend}-{arm}')
                if rec is None: entries = None; break
                link = rd / case
                if not link.exists(): link.symlink_to(ROOT / 'runs' / rec['id'] / case)
                entries.append(dict(case=case, exit=rec['exit'], dc=arm))
            if entries is None:
                rows.append(dict(backend=backend, arm=arm, status='UNRUN')); continue
            (rd / 'runs.json').write_text(json.dumps(entries, indent=1) + '\n')
            out = EVAL / f'A-{backend}-{arm}.json'
            p = subprocess.run([PY, str(SRC / 'docs/post_rc0/s1/synth_combined/eval_v2.py'), str(fixtures), str(rd), str(out)],
                               capture_output=True, text=True, env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'))
            res = json.loads(out.read_text()) if p.returncode == 0 else None
            if res:
                for r in res:
                    log = ROOT / 'runs' / f'A-{r["case"]}-{backend}-{arm}' / r['case'] / f'{r["case"]}.log'
                    r['convergence'] = log_convergence(log) if log.exists() else dict(error='no log')
                    rt = ROOT / 'runs' / f'A-{r["case"]}-{backend}-{arm}' / 'runtime.json'
                    r['runtime_local_enabled'] = json.loads(rt.read_text())['local_enabled'] if rt.exists() else None
                    r['dc_witness'] = rs[f'A-{r["case"]}-{backend}-{arm}']['dc_witness']
                out.write_text(json.dumps(res, indent=1) + '\n')
            rows.append(dict(backend=backend, arm=arm, eval_exit=p.returncode, stderr=p.stderr[-2000:], results=res))
    (EVAL / 'A-summary.json').write_text(json.dumps(rows, indent=1) + '\n')
    for r in rows:
        if r.get('results'):
            print(r['backend'], r['arm'], ' '.join(f"{x['case']}:{x['checker_status']}" for x in r['results']))
        else: print(r['backend'], r['arm'], r.get('status'), r.get('eval_exit'))


def tier_b():
    import check_realistic_motion as crm
    import check_realistic_image as img
    from motion_field import read_motion_star
    truth_cache = {}
    def truth(r):
        key = (r['nx'], r['ny'])
        if key not in truth_cache:
            path, expected = TRUTH[key]
            got = sha256(path)
            if got != expected: raise RuntimeError(f'truth cache hash {got} != {expected}')
            truth_cache[key] = np.load(path)
        return truth_cache[key]
    for name, rec in runs('B-').items():
        out = EVAL / 'B' / (name + '.json')
        if rec is None or out.exists(): continue
        out.parent.mkdir(exist_ok=True)
        run = ROOT / 'runs' / name
        receipt = Path(rec['cwd']) / 'RECEIPT.json'
        r = json.loads(receipt.read_text())['recipe']
        m = dict(id=name, exit=rec['exit'], arm=rec['arm'], backend=rec['backend'], group=rec['group'],
                 dc_witness=rec['dc_witness'], wall_s_unqualified=rec['wall_s_unqualified'])
        if rec['exit'] != 0:
            m['status'] = 'NATIVE_FAILURE'
        elif rec['arm'] == 'plain':
            m['status'] = 'CONTROL_ONLY'
        else:
            star = run / 'output/movie.star'
            crm.validate_star_rows(star, r)
            model = json.loads((run / 'runtime.json').read_text())
            m['truth'] = crm.evaluate(r, model, read_motion_star(star))
            m['truth']['convergence'] = crm.convergence(run / 'output/movie.log')
            summed = read_mrc(run / 'output/movie.mrc')[0]
            m['image'] = img.evaluate_sum(r, summed, truth(r))
            m['status'] = 'EVALUATED'
        out.write_text(json.dumps(m, indent=1, allow_nan=False) + '\n')
        print(name, m['status'], flush=True)


def find_product(run):
    mrcs = [p for p in run.rglob('*.mrc') if not p.name.endswith(('_PS.mrc', '_noDW.mrc'))]
    stars = [p for p in run.rglob('*.star') if p.name != 'corrected_micrographs.star']
    if len(mrcs) != 1 or len(stars) != 1: raise RuntimeError(f'{run}: products {mrcs} {stars}')
    return mrcs[0], stars[0]


def tier_c():
    rs = runs('C-')
    configs = sorted({n.rsplit('-', 2)[0] for n in rs})
    rows = []
    for cfg in configs:
        movie, grid = cfg[2:].rsplit('-', 1)
        row = dict(config=cfg, movie=movie, grid=grid, arms={})
        prod = {}
        for backend in ['cpu', 'cuda']:
            for arm in ARMS:
                rec = rs.get(f'{cfg}-{backend}-{arm}')
                if rec is None: continue
                d = dict(exit=rec['exit'], dc_witness=rec['dc_witness'], wall_s_unqualified=rec['wall_s_unqualified'],
                         route=None)
                run = ROOT / 'runs' / rec['id']
                if (run / 'witness.txt').exists(): d['route'] = (run / 'witness.txt').read_text().strip()[-400:]
                if rec['exit'] == 0:
                    mrc, star = find_product(run)
                    prod[(backend, arm)] = (mrc, star, run)
                    rt = json.loads((run / 'runtime.json').read_text())
                    d['local_enabled'] = rt['local_enabled']; d['global'] = rt['global']
                    logs = [p for p in run.rglob('*.log') if p.name not in ('stdout.log', 'stderr.log', 'time-v.log')]
                    d['convergence'] = log_convergence(logs[0]) if len(logs) == 1 else dict(error=f'logs {logs}')
                row['arms'][f'{backend}-{arm}'] = d
        for arm in ARMS:
            if ('cpu', arm) in prod and ('cuda', arm) in prod:
                (am, ast, _), (bm, bst, _) = prod[('cpu', arm)], prod[('cuda', arm)]
                p = subprocess.run([PY, str(SRC / 'tools/compare_motioncorr.py'), '--ref-mrc', str(am), '--ref-star', str(ast),
                                    '--test-mrc', str(bm), '--test-star', str(bst), '--gate', 'backend', '--json'],
                                   capture_output=True, text=True)
                try: cmp = json.loads(p.stdout)
                except ValueError: cmp = dict(parse_error=p.stdout[-500:] + p.stderr[-500:])
                row['arms'][f'backend-{arm}'] = dict(compare_exit=p.returncode,
                                                     relative_rmse=relrmse(read_mrc(am), read_mrc(bm)), compare=cmp)
        for backend in ['cpu', 'cuda']:
            if (backend, 'none') not in prod: continue
            base = read_mrc(prod[(backend, 'none')][0])
            g0 = np.array(row['arms'][f'{backend}-none']['global'])
            for arm in ARMS[1:]:
                if (backend, arm) not in prod: continue
                g = np.array(row['arms'][f'{backend}-{arm}']['global'])
                dg = np.hypot(*(g - g0).T)
                row['arms'][f'{backend}-{arm}']['vs_none'] = dict(relative_rmse=relrmse(base, read_mrc(prod[(backend, arm)][0])),
                                                               global_max_px=float(dg.max()), global_rms_px=float(np.sqrt(np.mean(dg ** 2))))
        rows.append(row)
        print(cfg, {k: round(v.get('relative_rmse', -1), 6) for k, v in row['arms'].items() if k.startswith('backend-')}, flush=True)
    (EVAL / 'C-rows.json').write_text(json.dumps(rows, indent=1) + '\n')


def controls():
    """Plain (option OFF) vs experiment none: MRC header 0:224, payload and STAR bytes."""
    rs = runs('')
    rows = []
    for name, rec in rs.items():
        if rec is None or rec['arm'] != 'plain': continue
        other = name[:-len('plain')] + 'none'
        o = rs.get(other)
        if o is None or rec['exit'] or o['exit']:
            rows.append(dict(control=name, status='UNRUN_OR_FAILED')); continue
        a, b = ROOT / 'runs' / name, ROOT / 'runs' / other
        mrcs = sorted(p.relative_to(a) for p in a.rglob('*.mrc'))
        stars = sorted(p.relative_to(a) for p in a.rglob('*.star'))
        diffs = []
        for rel in mrcs:
            x, y = (a / rel).read_bytes(), (b / rel).read_bytes()
            ext = int(np.frombuffer(x[92:96], '<i4')[0])
            if x[:224] != y[:224] or x[1024 + ext:] != y[1024 + ext:] or len(x) != len(y): diffs.append(str(rel))
        path_only = []
        for rel in stars:
            x, y = (a / rel).read_bytes(), (b / rel).read_bytes()
            if x == y: continue
            # The index STAR lists absolute product paths, which contain the run directory.
            if x.replace(str(a).encode(), b'RUN') == y.replace(str(b).encode(), b'RUN'): path_only.append(str(rel))
            else: diffs.append(str(rel))
        rows.append(dict(control=name, against=other, mrc=len(mrcs), star=len(stars), differing=diffs,
                         differing_only_by_run_directory_path=path_only,
                         status='IDENTICAL' if not diffs and mrcs and stars else 'DIFFERENT'))
    (EVAL / 'controls.json').write_text(json.dumps(rows, indent=1) + '\n')
    for r in rows: print(r['control'], r['status'], r.get('differing'), 'path-only:', r.get('differing_only_by_run_directory_path'))


def status():
    q = json.loads((ROOT / 'queue.json').read_text())
    rs = runs('')
    c = {}
    for j in q:
        rec = rs.get(j['id'], 'missing') if j['id'] in rs else 'missing'
        k = j['tier'] + '-' + j['backend']
        s = 'unrun' if rec == 'missing' else ('in-progress-or-orphan' if rec is None else ('exit0' if rec['exit'] == 0 else 'exit!=0'))
        c.setdefault(k, {}).setdefault(s, 0); c[k][s] += 1
    print(json.dumps(c, indent=1))


if __name__ == '__main__':
    dict(A=tier_a, B=tier_b, C=tier_c, controls=controls, status=status)[sys.argv[1]]()
