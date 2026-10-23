#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Affine patch (2,1) known-template oracle, protocol affine-patch-oracle/v1.

Offline, NumPy only, no MotionCorr execution. Judges the retained #275 patch (2,1)
capture against an independently written forward model of the affine fixture.
The protocol (PROTOCOL.md / protocol.json) was committed before this script ran.

usage: affine_patch_oracle.py REPO RAW FILE_INDEX OUT.json
"""
import hashlib, json, pathlib, subprocess, sys, time
import numpy as np

REPO, RAW, INDEX, OUT = (pathlib.Path(a) for a in sys.argv[1:5])
t_start = time.time()
sys.path[:0] = [str(REPO / 'tools'), str(REPO / 'test-data')]

NX, NY, NF = 128, 96, 5
PX, PY, X0, Y0 = 42, 32, 0, 32           # window X[0,42) Y[32,64)
NFXG, NFXP = NX // 2 + 1, PX // 2 + 1    # 65, 22
B, SEARCH, TOL = 150.0, 15, 0.5
FILE_INDEX_SHA = '31255dab8eef81ee05f68271ac665429db9a48498b240fbe85ebe228ea3c65c3'
MANIFEST_SHA = '9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc'
P275 = '6ae486785334fca635cfc9ad9e86026d656f3943'
GATE = dict(weight=1e-6, render=1e-5, field=1e-12, gen=1e-12, cmap=1e-9, replay=1e-6, rel_ac=1e-3,
            sep=10.0, cs_ratio=0.5, pc=1e-6, wc_zero=1e-9, band=0.05, bias=0.05)


def sha(b): return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------ provenance
committed = json.loads(subprocess.check_output(
    ['git', 'show', P275 + ':docs/post_rc0/s1/residual_ccf_20261022/receipt-index.json'], cwd=REPO))
index_bytes = INDEX.read_bytes()
prov = dict(file_index_sha256=sha(index_bytes), committed_array_product_index_sha256=committed['array_product_index_sha256'])
assert prov['file_index_sha256'] == FILE_INDEX_SHA == committed['array_product_index_sha256'], prov
index = json.loads(index_bytes)['files']
bound = {}


def load(rel):
    raw = (RAW / rel).read_bytes()
    assert sha(raw) == index[rel]['sha256'], rel
    bound[rel] = sha(raw)
    return raw


assert sha(load('fixtures/MANIFEST.json')) == MANIFEST_SHA
from motion_field import read_mrc  # noqa: E402
import generate_motion_diagnostics as gen  # noqa: E402  (cross-check only)

import tempfile  # noqa: E402
_tmp = pathlib.Path(tempfile.mkdtemp(prefix='motioncorr-affine-patch-oracle-', dir='/tmp'))
for rel in ('fixtures/affine.mrcs',):
    (_tmp / 'affine.mrcs').write_bytes(load(rel))
stored_movie, _ = read_mrc(_tmp / 'affine.mrcs')
import io  # noqa: E402
target_stored = np.load(io.BytesIO(load('fixtures/affine_target.npy')))
field_stored = np.load(io.BytesIO(load('fixtures/affine_field.npy')))

# ------------------------------------------------------------------ independent forward model
CEN = np.array([64.0, 48.0])
G_UNIT = np.array([3.25, -2.125])
A_UNIT = np.array([[0.012, -0.008], [0.006, -0.010]])
WAVES = [(3, 2, 1.0, 0.2), (7, -3, 0.7, 1.1), (11, 5, 0.5, -0.4), (19, -13, 0.25, 0.7)]
LAND = [(31, 23, 3.0, 3.0), (82, 57, -2.0, 5.0), (103, 34, 2.0, 4.0)]


def motion(f):
    t = f / 4.0
    return G_UNIT * t, A_UNIT * t


def fwd(f, q):
    g, a = motion(f)
    return q + g + (q - CEN) @ a.T


def inv(f, p):
    g, a = motion(f)
    rhs = (p - g - CEN).reshape(-1, 2).T
    return (CEN + np.linalg.solve(np.eye(2) + a, rhs).T).reshape(p.shape)


def sig(q):
    x, y = q[..., 0], q[..., 1]
    s = np.zeros(x.shape)
    for kx, ky, amp, ph in WAVES:
        s += amp * np.cos(2 * np.pi * (kx * x / NX + ky * y / NY) + ph)
    for cx, cy, amp, w in LAND:
        s += amp * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * w * w))
    return 100.0 + s


def grid(nx, ny, x0=0, y0=0):
    y, x = np.mgrid[y0:y0 + ny, x0:x0 + nx]
    return np.stack((x, y), axis=-1).astype(float)


checks = {}
# cross-check against the generator functions (not used for the oracle itself)
r = gen.recipe('affine')
rng = np.random.default_rng(12345)
pts = rng.uniform([-10, -10], [140, 110], size=(1000, 2))
dmax = 0.0
for f in range(NF):
    dmax = max(dmax, float(np.abs(fwd(f, pts) - gen.forward(r, f, pts)).max()),
               float(np.abs(inv(f, pts) - gen.inverse(r, f, pts)).max()))
dmax = max(dmax, float(np.abs(sig(pts) - gen.signal(r, pts)).max()))
checks['generator_cross_check_max_abs'] = dmax
Q = grid(NX, NY)
analytic_movie = np.stack([sig(inv(f, Q)) for f in range(NF)])
checks['render_vs_stored_frames_max_abs'] = float(np.abs(analytic_movie - stored_movie.astype(np.float64)).max())
checks['render_vs_stored_target_max_abs'] = float(np.abs(sig(Q) - target_stored.astype(np.float64)).max())
field_closed = np.stack([Q - fwd(f, Q) for f in range(NF)])
checks['field_vs_closed_form_max_abs'] = float(np.abs(field_closed - field_stored).max())
G_R = (checks['generator_cross_check_max_abs'] <= GATE['gen'] and checks['render_vs_stored_frames_max_abs'] <= GATE['render']
       and checks['field_vs_closed_form_max_abs'] <= GATE['field'])
checks['G-R'] = 'PASS' if G_R else 'FAIL'

UW = grid(PX, PY, X0, Y0)  # window pixel coordinates (x,y)
TARGET_W = sig(UW)

# ------------------------------------------------------------------ spectral helpers (native conventions)
LYP = np.arange(PY); LYP = np.where(LYP > PY // 2, LYP - PY, LYP).astype(float)   # native: y>ny/2 -> y-ny
KX = np.arange(NFXP).astype(float)
MULT = np.full(NFXP, 2.0); MULT[0] = 1.0; MULT[-1] = 1.0
WEIGHT = np.exp(-2 * B * ((LYP[:, None] / PY) ** 2 + (KX[None, :] / NFXP) ** 2))


def native_shift(F, cur, nx, ny):
    nfx = nx // 2 + 1
    ly = np.arange(ny); ly = np.where(ly > ny // 2, ly - ny, ly).astype(float)
    ph = 2 * np.pi * (np.arange(nfx)[None, :] * (-cur[0] / nx) + ly[:, None] * (-cur[1] / ny))
    return F * np.exp(1j * ph)


def wspec(img):
    return np.fft.rfft2(img) / img.size


def cmap(S):
    return np.fft.irfft2(S, s=(PY, PX)) * (PX * PY)


def cpu_winner(m):
    best, pos = -1e30, (0, 0)
    for y in range(-SEARCH, SEARCH + 1):
        for x in range(-SEARCH, SEARCH + 1):
            v = float(m[y % PY, x % PX])
            if v > best:
                best, pos = v, (x, y)
    return pos, best


def cuda_winner(m):
    R = 2 * SEARCH + 1
    lm = np.full(256, -1e30, np.float32); lp = [(0, 0)] * 256
    for idx in range(R * R):
        lane = idx % 256; sy = idx // R - SEARCH; sx = idx % R - SEARCH
        v = np.float32(m[sy % PY, sx % PX])
        if v > lm[lane]:
            lm[lane] = v; lp[lane] = (sx, sy)
    stride = 128
    while stride > 0:
        for t in range(stride):
            if lm[t + stride] > lm[t]:
                lm[t] = lm[t + stride]; lp[t] = lp[t + stride]
        stride >>= 1
    return lp[0], float(lm[0])


def parabola(m, pos, mx, eps=1e-15):
    px, py = pos
    out = []
    for vp, vn, p in ((float(m[py % PY, (px + 1) % PX]), float(m[py % PY, (px - 1) % PX]), px),
                      (float(m[(py + 1) % PY, px % PX]), float(m[(py - 1) % PY, px % PX]), py)):
        d = vp + vn - 2.0 * mx
        out.append(p - 0.5 * (vp - vn) / d if abs(d) > eps else float(p))
    return np.array(out)


AX = 2j * np.pi * KX / PX
AY = 2j * np.pi * LYP / PY


def cont_eval(M, d):
    ex = np.exp(2j * np.pi * KX * d[0] / PX)
    ey = np.exp(2j * np.pi * LYP * d[1] / PY)
    f = float(np.real(ey @ M @ ex))
    gx = float(np.real(ey @ M @ (AX * ex))); gy = float(np.real((AY * ey) @ M @ ex))
    hxx = float(np.real(ey @ M @ (AX * AX * ex))); hyy = float(np.real((AY * AY * ey) @ M @ ex))
    hxy = float(np.real((AY * ey) @ M @ (AX * ex)))
    return f, np.array([gx, gy]), np.array([[hxx, hxy], [hxy, hyy]])


def cont_max(S, start):
    """Newton ascent on the exact band-limited CCF; protocol v1 settings."""
    M = S * MULT[None, :]
    d = np.array(start, float)
    converged = False; its = 0
    for its in range(1, 51):
        f, g, H = cont_eval(M, d)
        if np.linalg.norm(g) < 1e-12 * abs(f):
            converged = True; break
        ev = np.linalg.eigvalsh(H)
        step = -np.linalg.solve(H, g) if ev.max() < 0 else g / max(abs(H).max(), 1e-300)
        n = np.linalg.norm(step)
        if n > 1.0: step = step / n
        t = 1.0
        while t > 1e-6 and cont_eval(M, d + t * step)[0] < f - 1e-14 * abs(f):
            t *= 0.5
        d = d + t * step
    f, g, H = cont_eval(M, d)
    ev = np.linalg.eigvalsh(-H)
    return dict(xy=d.tolist(), value=f, grad_norm=float(np.linalg.norm(g)), converged=bool(converged), iterations=its,
                hessian=H.tolist(), curvature_eigenvalues=ev.tolist(), condition_ratio=float(ev.max() / ev.min()) if ev.min() > 0 else None)


def cont_map(S):
    M = S * MULT[None, :]
    Ey = np.exp(2j * np.pi * LYP[:, None] * np.arange(PY)[None, :] / PY)      # (ky, dy)
    Ex = np.exp(2j * np.pi * KX[:, None] * np.arange(PX)[None, :] / PX)       # (kx, dx)
    return np.real(Ey.T @ M @ Ex)


def estimate(Sx, m_for_winner=None, backend_rule='cpu'):
    m = cmap(Sx) if m_for_winner is None else m_for_winner
    pos, mx = cpu_winner(m) if backend_rule == 'cpu' else cuda_winner(m)
    par = parabola(m, pos, mx)
    c = cont_max(Sx, pos)
    return pos, mx, par, c


def fixed_est(Ft, Ff):
    """Fixed-template objective: its own integer winner, then the continuous maximum."""
    S = Ft * np.conj(Ff) * WEIGHT
    pos, _ = cpu_winner(cmap(S))
    return cont_max(S, pos)


def soo_S(F, f):
    return (F.sum(axis=0) - F[f]) * np.conj(F[f]) * WEIGHT


def fix_S(F, f):
    return F[0] * np.conj(F[f]) * WEIGHT


def rel_ac(a, b):
    d = (a - b).copy(); d[0, 0] = 0
    r = b.copy(); r[0, 0] = 0
    return float(np.linalg.norm(d) / np.linalg.norm(r))


# ------------------------------------------------------------------ captured data
def arr(rel, dt, shape):
    return np.frombuffer(load(rel), dt).reshape(shape)


def global_state(backend):
    txt = load(f'runs/{backend}-affine-on/state/global.txt').decode()
    rows = [[float(v) for v in l.split()[1:]] for l in txt.strip().splitlines()]
    assert len(rows) == NF
    return np.array(rows)


BACK = {}
for backend in ('cpu', 'cuda'):
    base = f'runs/{backend}-affine-on/capture/'
    c1 = json.loads(load(base + 'c1.json')); c2 = json.loads(load(base + ('c2.json')))
    assert c1['patch_nxy'] == [NX, NY] and c2['patch_yx'] == [2, 1] and c2['patch_nxy'] == [PX, PY] and c2['search'] == SEARCH and c2['B'] == B
    cap = 'c2'
    its = 1
    while f'{base}{cap}-i{its + 1}-input.bin' in index: its += 1
    d = dict(g=global_state(backend), Fg=arr(base + 'c1-i1-input.bin', '<c8', (NF, NY, NFXG)).astype(np.complex128),
             weight=arr(base + 'c2-i0-weight.bin', '<f4', (PY, NFXP)), iters=its, base=base, meta=c2, iter={})
    for k in range(1, its + 1):
        d['iter'][k] = dict(
            input=arr(f'{base}c2-i{k}-input.bin', '<c8', (NF, PY, NFXP)).astype(np.complex128),
            # CPU capture writes one map file per frame; the CUDA overlay writes one concatenated map.
            maps=(np.stack([arr(f'{base}c2-i{k}-map-f{f}.bin', '<f4', (PY, PX)) for f in range(NF)]) if backend == 'cpu'
                  else arr(f'{base}c2-i{k}-map.bin', '<f4', (NF, PY, PX))),
            cand=arr(f'{base}c2-i{k}-candidate.bin', '<f8', (NF, 2)), before=arr(f'{base}c2-i{k}-before.bin', '<f8', (NF, 2)),
            after=arr(f'{base}c2-i{k}-after.bin', '<f8', (NF, 2)))
    BACK[backend] = d
log_rmsd = {}
for backend in ('cpu', 'cuda'):
    key = f'runs/{backend}-affine-on/out/affine.log'
    log_rmsd[backend] = key in index

# ------------------------------------------------------------------ G-W, G-X
gw = max(float(np.abs(WEIGHT.astype(np.float32).astype(np.float64) - BACK[b]['weight'].astype(np.float64)).max()) for b in BACK)
G_W = 'PASS' if gw <= GATE['weight'] else 'FAIL'

gx_names = sorted(k for k in index if k.startswith('runs/cuda-affine-on/capture/c2-'))
gx_mismatch = [k for k in gx_names if ('runs/cuda-affine-on/capture/c3-' + k.split('/c2-', 1)[1]) not in index
               or index[k]['sha256'] != index['runs/cuda-affine-on/capture/c3-' + k.split('/c2-', 1)[1]]['sha256']]
G_X = 'PASS' if not gx_mismatch and len(gx_names) > 0 else 'FAIL'

# ------------------------------------------------------------------ Stage E
def pipe_spec(Fg, g, ys=(Y0, Y0 + PY), xs=(X0, X0 + PX), sign=1.0, swap=False, noshift=False, transpose_crop=None):
    out = []
    for f in range(NF):
        cur = np.array(g[f]) * sign
        if swap: cur = cur[::-1].copy()
        Fs = Fg[f] if noshift else native_shift(Fg[f], cur, NX, NY)
        img = np.fft.irfft2(Fs, s=(NY, NX)) * (NX * NY)
        if transpose_crop is not None:
            crop = img[transpose_crop[0][0]:transpose_crop[0][1], transpose_crop[1][0]:transpose_crop[1][1]].T
        else:
            crop = img[ys[0]:ys[1], xs[0]:xs[1]]
        out.append(wspec(crop))
    return np.stack(out)


def analytic_spec(g):
    out = []
    for f in range(NF):
        out.append(wspec(sig(inv(f, UW - np.array(g[f])))))
    return np.stack(out)


stage_e = {}
stored_Fg = np.stack([np.fft.rfft2(stored_movie[f].astype(np.float64)) / (NX * NY) for f in range(NF)])
mutant_defs = {
    'N-E1': dict(sign=-1.0), 'N-E2': dict(swap=True), 'N-E3': dict(xs=(1, PX + 1)), 'N-E4': dict(ys=(Y0 + 1, Y0 + PY + 1)),
    'N-E5': dict(ys=(0, PY), xs=(42, 84)), 'N-E6': dict(transpose_crop=((0, 42), (32, 64))), 'N-E7': dict(noshift=True)}
for backend, d in BACK.items():
    cap_in = d['iter'][1]['input']
    row = dict()
    pipe = pipe_spec(d['Fg'], d['g'])
    row['pipeline_from_captured_global_input'] = [rel_ac(pipe[f], cap_in[f]) for f in range(NF)]
    pipe_stored = pipe_spec(stored_Fg, d['g'])
    row['pipeline_from_stored_mrcs'] = [rel_ac(pipe_stored[f], cap_in[f]) for f in range(NF)]
    ana = analytic_spec(d['g'])
    row['analytic_render_no_fourier_shift'] = [rel_ac(ana[f], cap_in[f]) for f in range(NF)]
    row['analytic_minus_pipeline'] = [rel_ac(ana[f], pipe[f]) for f in range(NF)]
    row['dc_captured'] = [float(cap_in[f][0, 0].real) for f in range(NF)]
    row['dc_pipeline'] = [float(pipe[f][0, 0].real) for f in range(NF)]
    row['mutants'] = {}
    for name, kw in mutant_defs.items():
        sp = pipe_spec(d['Fg'], d['g'], **kw)
        row['mutants'][name] = [rel_ac(sp[f], cap_in[f]) for f in range(NF)]
    stage_e[backend] = row
base_max = max(max(stage_e[b]['pipeline_from_captured_global_input']) for b in BACK)
G_E = 'PASS' if base_max <= GATE['rel_ac'] else 'FAIL'
mut_verdict = {}
for name in mutant_defs:
    per = {b: max(stage_e[b]['mutants'][name]) for b in BACK}
    rejected = all(v > GATE['rel_ac'] for v in per.values())
    sep = min(per.values()) / base_max if base_max > 0 else float('inf')
    mut_verdict[name] = dict(max_rel_ac=per, rejected_by_gate=bool(rejected), separation_vs_baseline_max=float(sep),
                             verdict='REJECTED' if rejected and sep >= GATE['sep'] else 'NOT_REJECTED')
N_E = 'PASS' if all(v['verdict'] == 'REJECTED' for v in mut_verdict.values()) else 'FAIL'

# ------------------------------------------------------------------ G-M, G-N (native maps)
gm_err = 0.0
gn = {}
for backend, d in BACK.items():
    rule = backend
    worst = 0.0; rows = []
    for k in range(1, d['iters'] + 1):
        it = d['iter'][k]
        for f in range(NF):
            m = it['maps'][f]
            pos, mx = cpu_winner(m) if rule == 'cpu' else cuda_winner(m)
            par = parabola(m, pos, mx)
            err = float(np.abs(par - it['cand'][f]).max())
            worst = max(worst, err)
            rows.append(dict(iteration=k, frame=f, winner=list(pos), replay=par.tolist(), captured=it['cand'][f].tolist(), err=err,
                             exact_ties=int((m[np.ix_(np.arange(-SEARCH, SEARCH + 1) % PY, np.arange(-SEARCH, SEARCH + 1) % PX)] == np.float32(mx)).sum())))
    gn[backend] = dict(max_err_px=worst, rows=rows)
G_N = 'PASS' if all(v['max_err_px'] <= GATE['replay'] for v in gn.values()) else 'FAIL'
for backend, d in BACK.items():
    F1 = d['iter'][1]['input']
    for f in range(NF):
        S = soo_S(F1, f)
        gm_err = max(gm_err, float(np.abs(cont_map(S) - cmap(S)).max() / np.abs(cmap(S)).max()))
G_M = 'PASS' if gm_err <= GATE['cmap'] else 'FAIL'

# ------------------------------------------------------------------ truth interval
def sstar(f, g, u):
    q = inv(f, u - np.array(g)); return q - u


truth = {}
for backend, d in BACK.items():
    rows = []
    for f in range(NF):
        s = sstar(f, d['g'][f], UW)
        band = [[float(s[..., a].min()), float(s[..., a].max())] for a in range(2)]
        rows.append(dict(frame=f, band_xy=band, range_xy=[band[a][1] - band[a][0] for a in range(2)],
                         centre_geometric_20p5_47p5=sstar(f, d['g'][f], np.array([[20.5, 47.5]]))[0].tolist(),
                         centre_logged_20_47=sstar(f, d['g'][f], np.array([[20.0, 47.0]]))[0].tolist()))
    truth[backend] = rows
# Explicit closed-form consistency: s*(u) = field_f(q) - g with q = inv_f(u-g)
cons = 0.0
for backend, d in BACK.items():
    for f in range(NF):
        u = UW[::7, ::5]
        q = inv(f, u - np.array(d['g'][f]))
        cons = max(cons, float(np.abs((q - u) - ((q - fwd(f, q)) - np.array(d['g'][f]))).max()))
checks['sstar_vs_field_minus_g_max_abs'] = cons

# ------------------------------------------------------------------ G-CS (image-domain sign/frame check)
cs = {}
cs_pass = True
for f in (2, 3, 4):
    uc = np.array([[20.5, 47.5]])
    tc = (inv(f, uc) - uc)[0]
    cand = {'true': tc, 'sign_flipped': -tc, 'axis_swapped': tc[::-1].copy(), 'zero_shift': np.zeros(2)}
    res = {k: float(np.linalg.norm(sig(inv(f, UW - v)) - TARGET_W)) for k, v in cand.items()}
    ratios = {k: res['true'] / res[k] for k in ('sign_flipped', 'axis_swapped', 'zero_shift')}
    cs[f] = dict(total_shift_centre=tc.tolist(), residual=res, ratio_true_over_mutant=ratios)
    cs_pass = cs_pass and all(v <= GATE['cs_ratio'] for v in ratios.values())
G_CS = 'PASS' if cs_pass else 'FAIL'

# ------------------------------------------------------------------ PC / WC controls
T_spec = wspec(TARGET_W)
OFFSETS = dict(zero=[(0, 0)], integer=[(1, 0), (0, -2), (-3, 2)], fractional=[(0.25, 0), (0, -0.5), (0.375, -0.625), (-1.3, 0.7)])
pc_rows = []


def run_est(Ft, Ff):
    S = Ft * np.conj(Ff) * WEIGHT
    m = cmap(S)
    pos, mx = cpu_winner(m)
    return pos, parabola(m, pos, mx), np.array(cont_max(S, pos)['xy'])


for kind, lst in OFFSETS.items():
    for mu in lst:
        mu = np.array(mu, float)
        ph = np.exp(2j * np.pi * (KX[None, :] * mu[0] / PX + LYP[:, None] * mu[1] / PY))
        pos, par, con = run_est(T_spec, T_spec * ph)
        _, par_m4, con_m4 = run_est(T_spec, T_spec * np.conj(ph))
        pc_rows.append(dict(kind=kind, mu=mu.tolist(), winner=list(pos), parabola=par.tolist(), continuous=con.tolist(),
                            continuous_err=float(np.abs(con - mu).max()), parabola_err=float(np.abs(par - mu).max()),
                            n_c4_rendered_opposite_continuous=con_m4.tolist(), mu_tuple=tuple(mu)))
pc_ok = all(r['continuous_err'] <= GATE['pc'] for r in pc_rows) and all(r['parabola_err'] <= GATE['pc'] for r in pc_rows if r['kind'] in ('zero', 'integer'))
PC = 'PASS' if pc_ok else 'FAIL'
nc = {}
for name, fn in (('N-C1', lambda mu: -mu), ('N-C2', lambda mu: mu[::-1].copy()), ('N-C3', lambda mu: mu + np.array([1.0, 0.0]))):
    errs = [(r['kind'], float(np.abs(np.array(r['continuous']) - fn(np.array(r['mu']))).max())) for r in pc_rows if r['kind'] != 'zero']
    nc[name] = dict(rejected=any(e > GATE['pc'] for _, e in errs), max_err=max(e for _, e in errs))
errs4 = [float(np.abs(np.array(r['n_c4_rendered_opposite_continuous']) - np.array(r['mu'])).max()) for r in pc_rows if r['kind'] != 'zero']
nc['N-C4'] = dict(rejected=any(e > GATE['pc'] for e in errs4), max_err=max(errs4))
N_C = 'PASS' if all(v['rejected'] for v in nc.values()) else 'FAIL'
for r in pc_rows: r.pop('mu_tuple')

wc_rows = []
for kind, lst in OFFSETS.items():
    for mu in lst:
        mu = np.array(mu, float)
        Fw = wspec(sig(UW + mu))      # content must move by +mu to align
        pos, par, con = run_est(T_spec, Fw)
        wc_rows.append(dict(kind=kind, mu=mu.tolist(), winner=list(pos), parabola=par.tolist(), continuous=con.tolist(),
                            continuous_bias=(con - mu).tolist(), parabola_bias=(par - mu).tolist(),
                            continuous_bias_norm=float(np.linalg.norm(con - mu)), parabola_bias_norm=float(np.linalg.norm(par - mu))))
WC_zero = 'PASS' if all(r['continuous_bias_norm'] <= GATE['wc_zero'] and r['parabola_bias_norm'] <= GATE['wc_zero'] for r in wc_rows if r['kind'] == 'zero') else 'FAIL'
wc_bias_max = max(r['continuous_bias_norm'] for r in wc_rows if r['kind'] != 'zero')

# ------------------------------------------------------------------ pure-translation validity
range_max = max(max(row['range_xy']) for b in truth for row in truth[b] if row['frame'] >= 1)
translation_valid = bool(range_max <= GATE['band'] and wc_bias_max <= GATE['bias'])

# ------------------------------------------------------------------ Stage C/P estimates, decomposition, states
ANA = {b: analytic_spec(BACK[b]['g']) for b in BACK}
PIPE = {b: pipe_spec(BACK[b]['Fg'], BACK[b]['g']) for b in BACK}
est = {}
decomp = {}
states = {}
accept = {}
for backend, d in BACK.items():
    rule = backend
    k1 = d['iter'][1]
    F1 = k1['input']
    rows = []
    for f in range(NF):
        S = soo_S(F1, f)
        m_d = cmap(S)
        pos_d, mx_d, par_d, con_c = estimate(S, m_d, 'cpu')
        m_nat = k1['maps'][f]
        pos_n, mx_n = cpu_winner(m_nat) if rule == 'cpu' else cuda_winner(m_nat)
        pk = float(m_d[pos_d[1] % PY, pos_d[0] % PX])
        ulp = float(np.spacing(np.float32(pk)))
        sdx = float(m_d[pos_d[1] % PY, (pos_d[0] + 1) % PX] + m_d[pos_d[1] % PY, (pos_d[0] - 1) % PX] - 2 * pk)
        sdy = float(m_d[(pos_d[1] + 1) % PY, pos_d[0] % PX] + m_d[(pos_d[1] - 1) % PY, pos_d[0] % PX] - 2 * pk)
        flat = np.sort(np.array([m_d[y % PY, x % PX] for y in range(-SEARCH, SEARCH + 1) for x in range(-SEARCH, SEARCH + 1)]))[::-1]
        cT = fixed_est(F1[0], F1[f]) if f else dict(xy=[0.0, 0.0])
        cTp = fixed_est(PIPE[backend][0], PIPE[backend][f]) if f else dict(xy=[0.0, 0.0])
        dRef = fixed_est(T_spec, ANA[backend][f]) if f else dict(xy=[0.0, 0.0])
        # analytic template/analytic frame, soo objective too (reference blending in the render)
        S_a = soo_S(ANA[backend], f)
        pos_a, mx_a, par_a, con_a = estimate(S_a, None, 'cpu')
        rows.append(dict(frame=f, native_candidate=k1['cand'][f].tolist(), native_float_map_winner=list(pos_n),
                         double_map_winner=list(pos_d), winner_equal=bool(pos_n == pos_d),
                         double_soo_parabola=par_d.tolist(), double_soo_continuous=con_c['xy'],
                         double_soo_hessian_eig=con_c['curvature_eigenvalues'], double_soo_condition=con_c['condition_ratio'],
                         double_soo_converged=con_c['converged'],
                         native_input_fixed_template_continuous=cT['xy'], pipeline_input_fixed_template_continuous=cTp['xy'],
                         analytic_fixed_template_continuous_Rfm=dRef['xy'],
                         analytic_soo_parabola=par_a.tolist(), analytic_soo_continuous=con_a['xy'],
                         peak_value=pk, float32_ulp_at_peak=ulp, second_diff_x_ulps=sdx / ulp, second_diff_y_ulps=sdy / ulp,
                         top1_top2_gap_ulps=float((flat[0] - flat[1]) / ulp), float_vs_double_map_max_ulps=float(np.abs(m_nat.astype(np.float64) - m_d).max() / ulp)))
    est[backend] = rows
    # decomposition, anchored to frame 0, telescoping order fixed by the protocol
    anch = lambda key: np.array([np.array(r[key]) - np.array(rows[0][key]) for r in rows])
    native_a = k1['cand'] - k1['cand'][0]
    b_a = anch('double_soo_parabola'); c_a = anch('double_soo_continuous')
    cT_a = np.array([r['native_input_fixed_template_continuous'] for r in rows])
    cTp_a = np.array([r['pipeline_input_fixed_template_continuous'] for r in rows])
    d_a = np.array([r['analytic_fixed_template_continuous_Rfm'] for r in rows])
    t_a = np.array([row['centre_geometric_20p5_47p5'] for row in truth[backend]])
    terms = dict(quantization_native_minus_b=native_a - b_a, parabola_b_minus_c=b_a - c_a, blending_c_minus_cT=c_a - cT_a,
                 input_cT_minus_d=cT_a - d_a, window_deformation_d_minus_t=d_a - t_a)
    total = native_a - t_a
    ident = float(np.abs(sum(terms.values()) - total).max())
    decomp[backend] = dict(identity_max_abs=ident, native_anchored=native_a.tolist(), truth_centre=t_a.tolist(),
                           total_native_minus_truth_centre=total.tolist(),
                           terms={k: v.tolist() for k, v in terms.items()},
                           input_split=dict(float32_cT_minus_cTpipe=(cT_a - cTp_a).tolist(), ringing_cTpipe_minus_d=(cTp_a - d_a).tolist()),
                           norms_px={k: [float(np.linalg.norm(x)) for x in v] for k, v in terms.items()})
    # states and acceptance
    st = []
    for k in range(1, d['iters'] + 1):
        it = d['iter'][k]
        cur = it['cand'] - it['cand'][0]
        rmsd = float(np.sqrt((cur ** 2).sum() / NF))
        rows_k = []
        for f in range(1, NF):
            s = it['after'][f]
            bnd = truth[backend][f]['band_xy']
            rows_k.append(dict(frame=f, state=s.tolist(), minus_Rfm=(s - d_a[f]).tolist(), minus_truth_centre=(s - t_a[f]).tolist(),
                               inside_translation_band=[bool(bnd[a][0] <= s[a] <= bnd[a][1]) for a in range(2)]))
        st.append(dict(iteration=k, rmsd=rmsd, below_tolerance=bool(rmsd < TOL), per_frame=rows_k))
    states[backend] = st
    accept[backend] = dict(converged=any(x['below_tolerance'] for x in st), captured_iterations=d['iters'],
                           rmsd=[x['rmsd'] for x in st])

# ------------------------------------------------------------------ result
verdict = {'G-W': G_W, 'G-R': checks['G-R'], 'G-M': G_M, 'G-N': G_N, 'G-X': G_X, 'G-E': G_E, 'N-E': N_E, 'G-CS': G_CS,
           'PC': PC, 'N-C': N_C, 'WC-zero': WC_zero}
res = dict(protocol='affine-patch-oracle/v1', kind='offline affine patch (2,1) known-template oracle; no MotionCorr execution',
           numpy=np.__version__, python=sys.version.split()[0], gates=GATE, provenance=prov,
           bound_inputs=bound, checks=checks, weight_max_abs_diff=gw, cuda_c2_c3_mismatched_files=gx_mismatch,
           cuda_c2_c3_files_compared=len(gx_names), controls=verdict,
           stage_e=stage_e, stage_e_baseline_max_rel_ac=base_max, mutants_e=mut_verdict,
           map_check_max_rel=gm_err, native_candidate_replay={k: dict(max_err_px=v['max_err_px']) for k, v in gn.items()},
           native_candidate_replay_rows=gn,
           truth_interval=truth, pure_translation_valid=translation_valid, truth_range_max_px=range_max,
           window_crop_bias_max_px=wc_bias_max, cs=cs, periodic_control=pc_rows, mutants_c=nc, window_crop_control=wc_rows,
           estimates=est, decomposition=decomp, states=states, acceptance=accept,
           native_log_present_in_index=log_rmsd,
           script_sha256=sha(pathlib.Path(__file__).read_bytes()), seconds=time.time() - t_start)
OUT.write_text(json.dumps(res, indent=1, allow_nan=False) + '\n')
print(json.dumps(dict(controls=verdict, base_max_rel_ac=base_max, mutants={k: (v['max_rel_ac'], v['verdict']) for k, v in mut_verdict.items()},
                      gw=gw, gm=gm_err, gn={k: v['max_err_px'] for k, v in gn.items()}, checks=checks,
                      translation_valid=translation_valid, range_max=range_max, wc_bias_max=wc_bias_max,
                      accept=accept, decomposition_identity={k: v['identity_max_abs'] for k, v in decomp.items()}), indent=1))
