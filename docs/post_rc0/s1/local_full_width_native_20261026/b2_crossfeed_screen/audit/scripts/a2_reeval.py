"""A2: independent re-evaluation from saved metadata + truth NPY only. Own STAR parser, own bases, own solvers
(QR for legacy; per-patch demeaning (Frisch-Waugh) for B2; explicit-intercept QR for C-form), own field and metrics.
Does not import w8_*, score_fields_* or any repo tool."""
import hashlib, json, sys
from pathlib import Path
import numpy as np
P = Path('/tmp/mc-lfw-b2-crossfeed-20261026-r1').resolve()
B = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Native-local-full-width-AUDIT-BUNDLE-r1')
RAW = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-factorial-parent-audit-r1/raw')
CASES = ['noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional', 'flat', 'repeated']
LOCAL = ['noisy', 'affine', 'pedestal']
LIM = {'rms': .20, 'p95': .40, 'max': .80}; CEIL = 0.01313142874082845; MARG = CEIL * .885
TM = json.loads((B / 'truth/MANIFEST.json').read_text())
NF, NY, NX = 5, 96, 128; Y0, Y1, X0, X1 = 12, 84, 12, 116

def star(path):
    """Generic RELION STAR loop/pair parser -> {block: {'pairs':{}, 'cols':[...], 'rows':[[...]]}}."""
    out, blk, cols = {}, None, None
    for raw in Path(path).read_text().splitlines():
        s = raw.strip()
        if not s or s.startswith('#'): continue
        if s.startswith('data_'): blk = s[5:]; out[blk] = {'pairs': {}, 'cols': [], 'rows': []}; cols = None; continue
        if s == 'loop_': cols = out[blk]['cols']; continue
        if s.startswith('_'):
            t = s.split()
            if cols is not None and (len(t) == 1 or t[1].startswith('#')): cols.append(t[0])
            else: out[blk]['pairs'][t[0]] = t[1]
            continue
        out[blk]['rows'].append(s.split())
    return out

def col(b, name): return [float(r[b['cols'].index(name)]) for r in b['rows']]

def load(case, d, star_name):
    rt = json.loads((d / 'runtime.json').read_text()); st = star(d / star_name)
    g = st['global_shift']; fn = col(g, '_rlnMicrographFrameNumber')
    assert fn == [1., 2., 3., 4., 5.]
    gstar = np.c_[col(g, '_rlnMicrographShiftX'), col(g, '_rlnMicrographShiftY')]
    cstar = np.zeros(36)
    if 'local_motion_model' in st:
        m = st['local_motion_model']
        for i, c in zip(col(m, '_rlnMotionModelCoeffsIdx'), col(m, '_rlnMotionModelCoeff')): cstar[int(i)] = c
    obs = None; centres = []
    if 'local_shift' in st and st['local_shift']['rows']:
        L = st['local_shift']; f = col(L, '_rlnMicrographFrameNumber'); x = col(L, '_rlnCoordinateX'); y = col(L, '_rlnCoordinateY')
        sx = col(L, '_rlnMicrographShiftX'); sy = col(L, '_rlnMicrographShiftY')
        centres = sorted(set(zip(x, y)))
        obs = np.full((len(centres), NF, 2), np.nan)
        for fi, xi, yi, a, b_ in zip(f, x, y, sx, sy): obs[centres.index((xi, yi)), int(fi) - 1] = (a, b_)
        assert not np.isnan(obs).any()
    nx = int(st['general']['pairs']['_rlnImageSizeX']); ny = int(st['general']['pairs']['_rlnImageSizeY'])
    return dict(rt=rt, gstar=gstar, cstar=cstar, obs=obs, centres=np.array(centres), nx=nx, ny=ny)

def S(u, v): return np.stack([np.ones_like(u), u, u * u, v, v * v, u * v], -1)       # (..., 6)
def poly_field(coeff36, gl, x, y, nx, ny):
    """Published field: global(f) + sum_{s,k} c[a, s, k] S_s(u,v) z^k, z = f = 0..4, k = 1..3; coeff layout a*18 + 3*s + (k-1)."""
    c = np.asarray(coeff36, float).reshape(2, 6, 3); z = np.arange(NF, dtype=float); Z = np.stack([z, z ** 2, z ** 3], -1)   # (f, 3)
    sp = S(x / nx - .5, y / ny - .5)                                     # (p, 6)
    loc = np.einsum('ps,ask,fk->fpa', sp, c, Z)
    return loc + np.asarray(gl, float)[:, None, :]

def phys(centres, nx, ny, tk):
    sp = S(centres[:, 0] / nx - .5, centres[:, 1] / ny - .5)               # (p, 6)
    return np.einsum('ps,fk->pfsk', sp, tk).reshape(len(centres) * NF, 18)  # rows (patch, frame); cols 3*s + k

def qr_solve(A, Y):
    Q, Rr = np.linalg.qr(A); return np.linalg.solve(Rr, Q.T @ Y)

def fit_legacy(obs, centres, nx, ny):
    t = np.arange(NF) + .5; X = phys(centres, nx, ny, np.stack([t, t ** 2, t ** 3], -1))
    return qr_solve(X, obs.reshape(-1, 2)).T.reshape(36), X

def fit_b2_fw(obs, centres, nx, ny):
    g = np.arange(NF, dtype=float); X = phys(centres, nx, ny, np.stack([g, g ** 2, g ** 3], -1))
    n = len(centres); Xd = (X.reshape(n, NF, 18) - X.reshape(n, NF, 18).mean(1, keepdims=True)).reshape(-1, 18)
    Yd = (obs - obs.mean(1, keepdims=True)).reshape(-1, 2)
    Xi = np.hstack([X, np.kron(np.eye(n), np.ones((NF, 1)))])
    return qr_solve(Xd, Yd).T.reshape(36), Xi

def field_c_form(obs, centres, nx, ny, x, y):
    """Fit q(t) with t = f + .5 plus per-patch intercept, publish h(f) = q(f+.5) - q(.5) evaluated directly (no coefficient remap)."""
    t = np.arange(NF) + .5; n = len(centres)
    X = np.hstack([phys(centres, nx, ny, np.stack([t, t ** 2, t ** 3], -1)), np.kron(np.eye(n), np.ones((NF, 1)))])
    c = qr_solve(X, obs.reshape(-1, 2))[:18].T.reshape(2, 6, 3)
    T = np.stack([t, t ** 2, t ** 3], -1) - np.array([.5, .25, .125])
    return np.einsum('ps,ask,fk->fpa', S(x / nx - .5, y / ny - .5), c, T)

yy, xx = np.mgrid[:NY, :NX]; XF, YF = xx.ravel().astype(float), yy.ravel().astype(float)
roi = np.zeros((NY, NX), bool); roi[Y0:Y1, X0:X1] = True; XR, YR = XF[roi.ravel()], YF[roi.ravel()]

def metrics(field_full, case):
    ps = TM['cases'][case]['recipe']['pixel_size']; assert TM['cases'][case]['roi'] == [Y0, Y1, X0, X1]
    tr = np.load(B / 'truth' / f'{case}_field.npy', allow_pickle=False); assert tr.shape == (NF, NY, NX, 2)
    e = (field_full.reshape(NF, NY, NX, 2) - tr)[:, Y0:Y1, X0:X1] * ps
    v = np.sqrt((e ** 2).sum(-1)).ravel()
    return {'rms': float(np.sqrt(np.mean(v * v))), 'p95': float(np.percentile(v, 95)), 'max': float(v.max())}
gate = lambda m: 'PASS' if all(m[k] <= LIM[k] for k in LIM) else 'FAIL'
rtc = lambda rt: np.r_[rt['coeff_x'], rt['coeff_y']]
def fdiff(c1, c2, g=np.zeros((NF, 2))):
    a = poly_field(c1, g, XR, YR, NX, NY) - poly_field(c2, g, XR, YR, NX, NY)
    return {'component_abs_max_px': float(np.abs(a).max()), 'vector_norm_max_px': float(np.linalg.norm(a, axis=-1).max())}

out = {'native': {}, 'offline': {}, 'replay': {}, 'equiv': {}, 'rank': {}, 'control': {}, 'hyb_vs_star': {}, 'globals': {}}
cache = {}
for c in CASES:
    for a in ('OFF', 'ON'):
        d = load(c, B / 'runs' / c / a, f'{c}.star'); cache[(c, a)] = d
        rtf = poly_field(rtc(d['rt']), d['rt']['global'], XF, YF, NX, NY); stf = poly_field(d['cstar'], d['gstar'], XF, YF, NX, NY)
        out['native'][f'{c}/{a}'] = {'runtime': metrics(rtf, c), 'STAR': metrics(stf, c), 'local_enabled': d['rt']['local_enabled'], 'n_patches': 0 if d['obs'] is None else len(d['centres'])}
        out['globals'][f'{c}/{a}'] = float(np.abs(np.array(d['rt']['global']) - d['gstar']).max())
        if c in LOCAL:
            cl, Xl = fit_legacy(d['obs'], d['centres'], NX, NY); cb, Xi = fit_b2_fw(d['obs'], d['centres'], NX, NY)
            out['rank'][f'{c}/{a}'] = {'n_patch': len(d['centres']), 'legacy_rank': int(np.linalg.matrix_rank(Xl)), 'legacy_cols': Xl.shape[1],
                                       'B2_rank': int(np.linalg.matrix_rank(Xi)), 'B2_cols': Xi.shape[1], 'B2_raw_cond': float(np.linalg.cond(Xi)),
                                       'spatial_rank': int(np.linalg.matrix_rank(S(d['centres'][:, 0] / NX - .5, d['centres'][:, 1] / NY - .5)))}
            out['replay'][f'{c}/{a}'] = {'coeff_abs_max': float(np.abs(cl - rtc(d['rt'])).max()), **fdiff(cl, rtc(d['rt']))}
            fb = poly_field(cb, np.zeros((NF, 2)), XR, YR, NX, NY); fc = field_c_form(d['obs'], d['centres'], NX, NY, XR, YR)
            out['equiv'][f'{c}/{a}'] = {'C_form_vs_B2_component_abs_max_px': float(np.abs(fb - fc).max()), 'h0_B2_exact_zero': bool((fb[0] == 0).all())}
            s1 = json.loads((P / 'out/stage1_fit.json').read_text())['native'][f'{c}/{a}']
            out['equiv'][f'{c}/{a}']['own_B2_vs_sealed_B2_coeff_abs_max'] = float(np.abs(cb - np.ravel(s1['B2_coeff'])).max())
            out['equiv'][f'{c}/{a}']['own_legacy_vs_sealed_legacy_coeff_abs_max'] = float(np.abs(cl - np.ravel(s1['legacy_coeff'])).max())
            for fit_name, cf in (('legacy', cl), ('B2', cb)):
                for gk, gl in (('rt', d['rt']['global']), ('hyb', d['gstar'])):
                    m = metrics(poly_field(cf, gl, XF, YF, NX, NY), c)
                    out['offline'][f'{c}/{a}/{fit_name}/R_{gk}'] = {'angstrom': m, 'gate': gate(m), 'margin_sensitive': [k for k in LIM if abs(m[k] - LIM[k]) <= MARG]}
            # R-hyb vs actual native STAR field for the same arm (legacy only is native): what serialization would add
            out['hyb_vs_star'][f'{c}/{a}/legacy'] = fdiff(cl, d['cstar'])
# controls: B2 on old-weight (bundle OFF == retained UP_only) observations vs retained native UP_B2
for c in ('noisy', 'affine'):
    up = load(c, RAW / c / 'UP_only', f'output/{c}.star'); ub = load(c, RAW / c / 'UP_B2', f'output/{c}.star')
    off = cache[(c, 'OFF')]
    assert np.array_equal(up['obs'], off['obs']) and np.array_equal(up['obs'], ub['obs'])
    cb, _ = fit_b2_fw(off['obs'], off['centres'], NX, NY)
    m = metrics(poly_field(cb, off['rt']['global'], XF, YF, NX, NY), c)
    ret_b2 = json.loads((RAW / c / 'UP_B2/metrics.json').read_text()); ret_up = json.loads((RAW / c / 'UP_only/metrics.json').read_text())
    own_ub_rt = metrics(poly_field(rtc(ub['rt']), ub['rt']['global'], XF, YF, NX, NY), c)
    own_ub_star = metrics(poly_field(ub['cstar'], ub['gstar'], XF, YF, NX, NY), c)
    out['control'][c] = {'offline_B2_old_weight_R_rt': m, 'gate': gate(m), 'retained_UP_B2_runtime_metrics_json': ret_b2['runtime']['angstrom'],
                         'retained_UP_B2_STAR_metrics_json': ret_b2['STAR']['angstrom'], 'retained_UP_only_runtime_metrics_json': ret_up['runtime']['angstrom'],
                         'own_UP_B2_runtime_field_metrics': own_ub_rt, 'own_UP_B2_STAR_field_metrics': own_ub_star,
                         'metric_abs_diff_vs_retained_A': {k: abs(m[k] - ret_b2['runtime']['angstrom'][k]) for k in LIM},
                         'UP_B2_vs_UP_only_global_equal': bool(np.array_equal(np.array(ub['rt']['global']), np.array(up['rt']['global']))),
                         'coeff_abs_max_vs_UP_B2_runtime': float(np.abs(cb - rtc(ub['rt'])).max()),
                         'field_vs_UP_B2_runtime': fdiff(cb, rtc(ub['rt'])),
                         'field_vs_UP_B2_STAR_coeffs': fdiff(cb, ub['cstar']),
                         'native_UP_B2_runtime_vs_STAR_coeffs': fdiff(rtc(ub['rt']), ub['cstar'])}
json.dump(out, sys.stdout, indent=1, allow_nan=False); print()
