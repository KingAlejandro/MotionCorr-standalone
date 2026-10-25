# SPDX-License-Identifier: GPL-2.0-or-later
"""Frozen-input helpers; no native execution or fixture regeneration."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / 'input-cache'
PIN = '757558777b1e89611fa10f0a61dbcd941920207440c419fd1826ece86d07adb5'
sha = lambda b: hashlib.sha256(b).hexdigest()

def verify():
    raw = (ROOT / 'INPUTS.json').read_bytes()
    assert sha(raw) == PIN
    man = json.loads(raw)
    for rel, p in man['files'].items():
        b = (IN / rel).read_bytes()
        assert len(b) == p['bytes'] and sha(b) == p['sha256'], rel
    return man

sys.dont_write_bytecode = True
sys.path[:0] = [str(IN / 'source/tools'), str(IN / 'source/test-data')]
from motion_field import read_mrc, read_motion_star
import check_motion_diagnostics as checker
import generate_motion_diagnostics as generator

NX, NY, NF, PIX = 128, 96, 5, .885
ROI = (12, 84, 12, 116)
CENTRES = [(20, 15), (62, 15), (104, 15), (20, 47), (62, 47), (104, 47), (20, 79), (62, 79), (104, 79)]
Q = np.stack(np.meshgrid(np.arange(NX), np.arange(NY)), axis=-1).astype(float)

def basis(x, y, z):
    return np.stack([p * t for p in (np.ones_like(x), x, x*x, y, y*y, x*y)
                     for t in (z, z*z, z*z*z)], axis=-1)

def fit(local, mode):
    """local: frame-zero shifts [patch,frame,xy]; unit groups only."""
    n, nf, _ = local.shape
    xy = np.array(CENTRES[:n], float)
    z = np.arange(nf, dtype=float)
    obs = local.copy()
    if mode == 'inherited':
        z += .5
        obs -= (1.5*local[:, :1] - .5*local[:, 1:2])
    elif mode != 'integer':
        raise ValueError(mode)
    A = basis(np.broadcast_to(xy[:, 0:1]/NX-.5, (n, nf)),
              np.broadcast_to(xy[:, 1:2]/NY-.5, (n, nf)), np.broadcast_to(z, (n, nf))).reshape(-1, 18)
    c, residual, rank, sv = np.linalg.lstsq(A, obs.reshape(-1, 2), rcond=None)
    assert rank == 18 and np.isfinite(c).all()
    return c, dict(rank=int(rank), condition=float(sv[0]/sv[-1]), residual_sum_squares=residual.tolist())

def field(g, coeff=None):
    nf = len(g)
    out = np.broadcast_to(g[:, None, None, :], (nf, NY, NX, 2)).copy()
    if coeff is not None:
        for f in range(nf):
            out[f] += basis(Q[..., 0]/NX-.5, Q[..., 1]/NY-.5, np.full((NY, NX), float(f))) @ coeff
    return out

def metrics(e):
    assert np.isfinite(e).all()
    v = np.linalg.norm(e, axis=-1)
    return dict(rms=float(np.sqrt(np.mean(v*v))), p95=float(np.percentile(v, 95)), max=float(v.max()))

def rms(e):
    return metrics(e)['rms']

def score(f, truth):
    m = metrics((f-truth)[:, ROI[0]:ROI[1], ROI[2]:ROI[3]] * PIX)
    return dict(**m, verdict='PASS' if all(m[k] <= l for k,l in [('rms',.20), ('p95',.40), ('max',.80)]) else 'FAIL')

def state(case='affine'):
    p = IN / f'repro/r275/runs/cpu-{case}-on'
    g = np.loadtxt(p / 'state/global.txt')[:, 1:]
    lines = (p / 'state/model.txt').read_text().splitlines()
    c = np.array([[float(v) for v in l.split()[1:]] for l in lines[1:]])
    return g, c if len(c) else None

def fixture(case):
    p = IN / 'fixtures'
    return (read_mrc(p / (case+'.mrcs'))[0],
            np.load(p / (case+'_target.npy'), allow_pickle=False),
            np.load(p / (case+'_field.npy'), allow_pickle=False))

def captured_local():
    rows = []
    for iy in range(1,4):
        for ix in range(1,4):
            p = IN / f'matched/captures/patch-{iy}-{ix}'
            aft = max(p.glob('c2-i*-after.bin'), key=lambda p: int(p.name.split('-')[1][1:]))
            rows.append(np.frombuffer(aft.read_bytes(), '<f8').reshape(5,2))
    return np.array(rows)

def oracle_helpers():
    """Import only the reviewed helper section, no W4 file IO/main code."""
    p = IN / 'retained/qualification_20261025/matched-native/scripts/w4_matched_native.py'
    src = p.read_text()
    section = src.split('# ------------------------------------------------ reviewed-oracle helpers (verbatim)')[1].split('# ------------------------------------------------ fixed inputs:')[0]
    ns = dict(np=np, PY=32, PX=42, NFXP=22, B=150., SEARCH=15, NF=5,
              TOL=.5, LOO_MAX=60, LOO_TOL=1e-9)
    exec(compile(section, str(p)+'[helper section]', 'exec'), ns)
    ns['est_S'] = lambda S: dict(xy=ns['same_sample'](S)[2])
    return ns

def save(name, obj):
    obj.update(input_manifest_sha256=PIN, python=sys.version, numpy=np.__version__,
               script_hashes={p.name: sha(p.read_bytes()) for p in sorted((ROOT/'scripts').glob('*.py'))})
    p = ROOT / 'results' / name
    assert not p.exists(), 'refusing to overwrite '+str(p)
    p.write_text(json.dumps(obj, indent=1, allow_nan=False)+'\n')
