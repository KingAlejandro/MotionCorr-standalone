#!/usr/bin/env python3
"""Reviewer controls: (C4) G-E gate power against small global-state perturbations and a
cross-backend state swap, using own full-complex fft2 shift/crop chain; (C5) native
increment/state bookkeeping behind the RMSD replay; (C6) exact float32 ties at iteration 1.
usage: ge_power_and_rmsd.py RAW INDEX ATTEMPT02_JSON OUT.json"""
import hashlib, json, pathlib, sys
import numpy as np
RAW, INDEX, AJ, OUT = (pathlib.Path(a) for a in sys.argv[1:5])
idx = json.loads(INDEX.read_bytes())['files']
def load(rel):
    b = (RAW / rel).read_bytes(); assert hashlib.sha256(b).hexdigest() == idx[rel]['sha256'], rel; return b
A = json.loads(AJ.read_text())
NX, NY, PX, PY = 128, 96, 42, 32
def gstate(b):
    return np.array([[float(v) for v in l.split()[1:]] for l in load(f'runs/{b}-affine-on/state/global.txt').decode().split('\n') if l.strip()])
def full_from_half(H):  # Hermitian completion of an (NY, NX/2+1) half spectrum, then real image
    return np.fft.irfft2(H, s=(NY, NX))
def chain(Fg, g):
    out = []
    kx = np.fft.rfftfreq(NX, 1 / NX); ky = np.fft.fftfreq(NY, 1 / NY)
    ky = np.where(ky == -NY // 2, NY // 2, ky)  # native keeps Nyquist row at +ny/2
    for f in range(5):
        ph = np.exp(-2j * np.pi * (kx[None, :] * g[f, 0] / NX + ky[:, None] * g[f, 1] / NY))
        img = full_from_half(Fg[f] * ph) * NX * NY
        crop = img[32:64, 0:42]
        out.append(np.fft.rfft2(crop) / crop.size)
    return np.stack(out)
def relac(a, b):
    d = a - b; d[0, 0] = 0; r = b.copy(); r[0, 0] = 0; return float(np.linalg.norm(d) / np.linalg.norm(r))
out = {}
for b in ('cpu', 'cuda'):
    base = f'runs/{b}-affine-on/capture/'
    Fg = np.frombuffer(load(base + 'c1-i1-input.bin'), '<c8').reshape(5, NY, NX // 2 + 1).astype(complex)
    cap = np.frombuffer(load(base + 'c2-i1-input.bin'), '<c8').reshape(5, PY, PX // 2 + 1).astype(complex)
    g = gstate(b)
    row = dict(baseline=max(relac(c, k) for c, k in zip(chain(Fg, g), cap)))
    for dlt in (0.001, 0.003, 0.01, 0.03, 0.1):
        for ax in (0, 1):
            gg = g.copy(); gg[1:, ax] += dlt
            row[f'state_plus_{dlt}_axis{ax}'] = max(relac(c, k) for c, k in zip(chain(Fg, gg), cap))
    other = gstate('cuda' if b == 'cpu' else 'cpu')
    row['other_backend_state'] = max(relac(c, k) for c, k in zip(chain(Fg, other), cap))
    out[f'C4_{b}'] = row
    # C5: bookkeeping. after_k = before_k + (cand_k - cand_k[0]); rmsd from anchored increment
    k, bk = 1, []
    while f'{base}c2-i{k}-input.bin' in idx:
        c = np.frombuffer(load(f'{base}c2-i{k}-candidate.bin'), '<f8').reshape(5, 2)
        be = np.frombuffer(load(f'{base}c2-i{k}-before.bin'), '<f8').reshape(5, 2)
        af = np.frombuffer(load(f'{base}c2-i{k}-after.bin'), '<f8').reshape(5, 2)
        inc = c - c[0]
        bk.append(dict(iteration=k, after_minus_before_minus_anchored_cand=float(np.abs(af - be - inc).max()),
                       rmsd=float(np.sqrt((inc ** 2).sum() / 5))))
        k += 1
    out[f'C5_{b}'] = bk
    out[f'C6_{b}_exact_ties_iter1'] = [r['exact_ties'] for r in A['native_candidate_replay_rows'][b]['rows'] if r['iteration'] == 1]
    out[f'C6_{b}_exact_ties_all'] = [(r['iteration'], r['frame'], r['exact_ties']) for r in A['native_candidate_replay_rows'][b]['rows'] if r['exact_ties'] > 1]
OUT.write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
