"""Two-case read-only scoring audit. No fitter, native job, image read, or tuning."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode = True
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-f9ee0a2b')
BASE = Path('/tmp/motioncorr-b2-retained-challenge-20261026')
HEAD = 'e28ffb10c9189a5a5054bf7e6e51027f560766a6'
REMOTE = '/tmp/motioncorr-b2-factorial-20261026/evidence/runs'
EPS = 1e-12  # numerical audit threshold; no scientific gate change
sha = lambda b: hashlib.sha256(b).hexdigest()
paths = [f'{case}/{arm}/{name}' for case in ['noisy', 'affine']
         for arm in ['UP_only', 'UP_B2']
         for name in ['runtime.json', 'metrics.json', 'RUN.json', f'output/{case}.star']]
start = time.time()

# Version 2 consumes the exact existing read-only fetch; no SSH or producer rerun.
index = json.loads((HERE / 'raw/FETCH_INDEX.json').read_text())
for name in paths:
    data = (HERE / 'raw' / name).read_bytes()
    assert sha(data) == index['files'][name]['sha256']
    assert len(data) == index['files'][name]['bytes']

source = subprocess.check_output(['git', 'show', HEAD + ':tools/motion_field.py'], cwd=REPO)
assert sha(source) == 'd72cfad7175368fa6d0727c2727c49780328951c6f4d3ecc20e9ac662ac2e810'
module_path = HERE / 'motion_field.py'
module_path.write_bytes(source)
spec = importlib.util.spec_from_file_location('audit_motion_field', module_path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

manifest_path = BASE / 'v2fixtures/MANIFEST.json'
manifest = json.loads(manifest_path.read_text())
pins_path = REPO / 'docs/post_rc0/s1/native_b2_upstream_factorial_20261026/PINS.json'
pins = json.loads(pins_path.read_text())
for case in ['noisy', 'affine']:
    expected = pins['fixture_files'][pins['fixtures_root'] + '/' + case + '_field.npy']
    data = (BASE / 'v2fixtures' / (case + '_field.npy')).read_bytes()
    assert sha(data) == expected['sha256'] and len(data) == expected['bytes']

inputs = {'fixture_manifest': {'path': str(manifest_path), 'sha256': sha(manifest_path.read_bytes())},
          'source': {'revision': HEAD, 'motion_field.py': sha(source)}, 'truth': {}}
rows = []
for case in ['noisy', 'affine']:
    c = manifest['cases'][case]
    r = c['recipe']
    y0, y1, x0, x1 = c['roi']
    truth_path = BASE / f'v2fixtures/{case}_field.npy'
    truth_bytes = truth_path.read_bytes()
    inputs['truth'][case] = {'path': str(truth_path), 'sha256': sha(truth_bytes), 'roi': c['roi']}
    truth = np.load(io.BytesIO(truth_bytes), allow_pickle=False)
    assert truth.shape == (r['frames'], r['ny'], r['nx'], 2)
    yy, xx = np.mgrid[:r['ny'], :r['nx']]
    u, v = xx.ravel() / r['nx'] - .5, yy.ravel() / r['ny'] - .5
    spatial = np.stack([np.ones_like(u), u, u*u, v, v*v, u*v])
    f = np.arange(r['frames'], dtype=float)
    temporal = np.stack([f, f*f, f*f*f])
    for arm in ['OFF', 'B2', 'UP_only', 'UP_B2']:
        if arm in ['OFF', 'B2']:
            d = BASE / 'evidence/K267' / case / ('OFF' if arm == 'OFF' else 'ON-v3')
        else:
            d = HERE / 'raw' / case / arm
        rt = json.loads((d / 'runtime.json').read_text())
        st = mod.read_motion_star(d / f'output/{case}.star')
        assert (st.nx, st.ny, st.n_frames, st.first_frame) == (r['nx'], r['ny'], r['frames'], 1)
        assert st.pixel_size == r['pixel_size']
        g = np.asarray(rt['global'], dtype=float)
        field = np.broadcast_to(g[:, None, :], (r['frames'], u.size, 2)).copy()
        if rt['local_enabled']:
            coeff = np.array([rt['coeff_x'], rt['coeff_y']]).reshape(2, 6, 3)
            field += np.einsum('agt,tf,gp->fpa', coeff, temporal, spatial)
        star_field = st.field(st.frames, xx.ravel(), yy.ravel())
        row = {'case': case, 'arm': arm, 'local_enabled': rt['local_enabled'], 'runtime': {}, 'STAR': {}}
        for name, value in [('runtime', field), ('STAR', star_field)]:
            value = value.reshape(truth.shape)
            assert np.isfinite(value).all()
            err = ((value - truth) * r['pixel_size'])[:, y0:y1, x0:x1]
            norms = np.linalg.norm(err, axis=-1)
            m = {'rms': float(np.sqrt(np.mean(norms*norms))),
                 'p95': float(np.percentile(norms, 95)), 'max': float(norms.max())}
            m['verdict'] = 'PASS' if all(m[k] <= z for k, z in [('rms', .2), ('p95', .4), ('max', .8)]) else 'FAIL'
            row[name] = m
        if arm in ['UP_only', 'UP_B2']:
            saved = json.loads((d / 'metrics.json').read_text())
            diffs = {f'{kind}.{k}': abs(row[kind][k] - saved[kind]['angstrom'][k])
                     for kind in ['runtime', 'STAR'] for k in ['rms', 'p95', 'max']}
            assert max(diffs.values()) <= EPS, diffs
            row['saved_metric_max_abs_diff_A'] = max(diffs.values())
        row['model_sha256'] = sha((d / 'runtime.json').read_bytes())
        row['STAR_sha256'] = sha((d / f'output/{case}.star').read_bytes())
        rows.append(row)

noisy = {x['arm']: x for x in rows if x['case'] == 'noisy'}
comparisons = {}
for kind in ['runtime', 'STAR']:
    comparisons[kind] = {k: noisy['UP_B2'][kind][k] - noisy['UP_only'][kind][k] for k in ['rms', 'p95', 'max']}
    assert all(x > 0 for x in comparisons[kind].values())
result = {'status': 'AUDIT_PASS', 'scientific_promotion': 'BLOCKED',
          'scope': 'noisy and affine only; saved fields and STAR; no fit/native/image analysis',
          'numerical_audit_tolerance_A': EPS, 'scientific_limits_A': [.2, .4, .8],
          'inputs': inputs, 'rows': rows, 'noisy_UP_B2_minus_UP_only_A': comparisons,
          'P2_no_worsening': 'FALSIFIED', 'seconds': time.time() - start,
          'numpy': np.__version__}
(HERE / 'RESULT-v2.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
files = [p for p in HERE.rglob('*') if p.is_file() and p.name != 'SHA256SUMS']
(HERE / 'SHA256SUMS').write_text('\n'.join(f'{sha(p.read_bytes())}  {p.relative_to(HERE)}' for p in sorted(files)) + '\n')
print(json.dumps({'status': result['status'], 'P2_no_worsening': result['P2_no_worsening'],
                  'noisy_increases': comparisons, 'rows': len(rows), 'seconds': result['seconds']}))
