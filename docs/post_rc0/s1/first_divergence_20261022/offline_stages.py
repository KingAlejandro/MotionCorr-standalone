#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""W4 offline stage analysis of retained #273/#275 global-alignment arrays.

The winner search uses the CPU row-major strict-maximum rule for both backends;
CUDA's 256-lane reduction can choose a different exact tie (ties are counted).

No MotionCorr process is run. Inputs are the original NumPy 2.5.3 fixtures and
the #275 capture arrays, each bound by SHA-256 to the committed #275 receipt
index (6ae48678) and the fixture MANIFEST. Every replay below is an offline
reference, not a native trajectory.

usage: offline_stages.py RAW FILE_INDEX REPO OUT.json
"""
import hashlib, json, pathlib, subprocess, sys
import numpy as np
from scipy.optimize import minimize

RAW, INDEX, REPO, OUT = (pathlib.Path(a) for a in sys.argv[1:5])
sys.path[:0] = [str(REPO/'tools'), str(REPO/'test-data')]
from motion_field import read_mrc  # MRC reader only; no production numerics
import generate_motion_diagnostics as gen

NX, NY, NF, NFX, SEARCH, B, TOL, PIX = 128, 96, 5, 65, 47, 150.0, 0.5, 0.885
MANIFEST_SHA = '9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc'
P275 = '6ae486785334fca635cfc9ad9e86026d656f3943'

def sha(b): return hashlib.sha256(b).hexdigest()
committed = json.loads(subprocess.check_output(['git', 'show', P275 + ':docs/post_rc0/s1/residual_ccf_20261022/receipt-index.json'], cwd=REPO))
assert sha(INDEX.read_bytes()) == committed['array_product_index_sha256']
index = json.loads(INDEX.read_text())['files']
bound = {}
def load(rel):
    b = (RAW/rel).read_bytes()
    assert sha(b) == index[rel]['sha256'], rel
    bound[rel] = index[rel]['sha256']
    return b
manifest = json.loads(load('fixtures/MANIFEST.json'))
assert sha((RAW/'fixtures/MANIFEST.json').read_bytes()) == MANIFEST_SHA

def weight():
    ly = np.fft.fftfreq(NY) * NY
    x = np.arange(NFX)
    # Production normalisation: ly/nfy and x/nfx with nfx = nx/2+1 (inherited).
    return np.exp(-2*B*((ly[:, None]/NY)**2 + (x[None, :]/NFX)**2))

W = weight()

def ccf_map(F, f, fixed):
    ref = F[0] if fixed else F.sum(axis=0) - F[f]
    return np.fft.irfft2(ref*np.conj(F[f])*W, s=(NY, NX))*(NX*NY)  # unnormalised inverse

def winner(m):
    best, pos = -np.inf, (0, 0)
    for y in range(-SEARCH, SEARCH+1):        # CPU row-major strict-maximum order
        for x in range(-SEARCH, SEARCH+1):
            v = m[y % NY, x % NX]
            if v > best: best, pos = v, (x, y)
    return pos, best

def parabola(m):
    (px, py), mx = winner(m)
    mx = float(mx); out = []
    for (vp, vn, p) in ((m[py % NY, (px+1) % NX], m[py % NY, (px-1) % NX], px),
                        (m[(py+1) % NY, px % NX], m[(py-1) % NY, px % NX], py)):
        vp, vn = float(vp), float(vn); d = vp + vn - 2*mx
        out.append(p - 0.5*(vp-vn)/d if abs(d) > 1e-15 else float(p))
    return np.array(out), (px, py)

def continuous_argmax(S, start):
    """Maximise the band-limited CCF given by half-spectrum S in continuous coordinates."""
    ky = np.fft.fftfreq(NY)[:, None]; kx = (np.arange(NFX)/NX)[None, :]
    mult = np.full(NFX, 2.0); mult[0] = 1; mult[-1] = 1  # Hermitian multiplicity
    def f(p):
        ph = np.exp(2j*np.pi*(kx*p[0] + ky*p[1]))
        v = S*ph*mult
        return -float(np.real(v.sum())), -np.array([float(np.real((2j*np.pi*kx*v).sum())), float(np.real((2j*np.pi*ky*v).sum()))])
    r = minimize(f, np.array(start, float), jac=True, method='BFGS', options=dict(gtol=1e-10))
    return r.x

def shift(F, cur):
    ly = np.fft.fftfreq(NY)*NY; x = np.arange(NFX)
    return F*np.exp(2j*np.pi*(x[None, :]*(-cur[0]/NX) + ly[:, None]*(-cur[1]/NY)))

def replay(F0, fixed, quantize, max_iter=5, tol=TOL, estimator='parabola', truth=None):
    F = F0.astype(np.complex128).copy(); acc = np.zeros((NF, 2)); its = []
    for it in range(1, max_iter+1):
        cand = np.zeros((NF, 2))
        for f in range(NF):
            m = ccf_map(F, f, fixed)
            if estimator == 'parabola':
                cand[f] = parabola(m.astype(np.float32) if quantize else m)[0]
            else:  # exact continuous maximum of the same weighted band-limited objective
                S = (F[0] if fixed else F.sum(0)-F[f])*np.conj(F[f])*W
                cand[f] = continuous_argmax(S, winner(m)[0])
        cand -= cand[0]
        acc += cand
        for f in range(1, NF): F[f] = shift(F[f], cand[f])
        rmsd = float(np.sqrt((cand**2).sum()/NF))
        its.append(dict(iteration=it, rmsd=rmsd, truth_rms_px=err(acc, truth)['rms_px']))
        if rmsd < tol: break
    return acc, its, rmsd < tol

def err(traj, truth):
    v = np.linalg.norm(traj-truth, axis=1)
    return dict(rms_px=float(np.sqrt(np.mean(v*v))), max_px=float(v.max()), rms_angstrom=float(np.sqrt(np.mean(v*v))*PIX))

result = dict(kind='offline stage analysis of retained arrays; no MotionCorr execution',
              sources=dict(composition='805d9de27898b4a10e6212e65098d5995a40fdb1', native='d751ff28594902eca75d665ff116e662653481aa', capture=P275),
              numpy=np.__version__, cases={})
for case in ['integer', 'fractional']:
    for name in [f'{case}.mrcs', f'{case}_target.npy', f'{case}_field.npy']:
        assert sha(load('fixtures/'+name)) == manifest['cases'][case]['files'][name]
    movie, _ = read_mrc(RAW/'fixtures'/f'{case}.mrcs'); movie = movie.astype(np.float64)
    target = np.load(RAW/'fixtures'/f'{case}_target.npy').astype(np.float64)
    field = np.load(RAW/'fixtures'/f'{case}_field.npy')
    truth = field[:, 0, 0, :]
    assert np.array_equal(field, np.broadcast_to(truth[:, None, None, :], field.shape))
    r = manifest['cases'][case]['recipe']
    c = dict(truth_global_xy=truth.tolist())
    # S0 generator/input: stored float32 samples against an independent double re-render.
    q = gen.grid(r)
    rerender = np.stack([gen.signal(r, gen.inverse(r, f, q)) for f in range(NF)])
    c['S0_input'] = dict(stored_vs_double_render_max_abs=float(np.abs(movie-rerender).max()),
                         float32_ulp_at_pedestal=float(np.spacing(np.float32(100))),
                         frame0_equals_target=bool(np.array_equal(movie[0], target)))
    if case == 'integer':
        c['S0_input']['circular_shift_max_abs'] = [float(np.abs(movie[f]-np.roll(target, (-2*f, f), axis=(0, 1))).max()) for f in range(NF)]
    # S0 physical-template oracle on stored samples: double, continuous argmax.
    Ft = np.fft.rfft2(target)/(NX*NY); Fm = np.fft.rfft2(movie)/(NX*NY)
    tmpl = {}
    for label, w, demean in (('production_weight_with_pedestal', W, False), ('unweighted_pedestal_removed', np.ones_like(W), True)):
        est = []
        for f in range(NF):
            A, Bf = Ft.copy(), Fm[f].copy()
            if demean: A[0, 0] = 0; Bf[0, 0] = 0
            S = A*np.conj(Bf)*w*(NX*NY)
            m = np.fft.irfft2(S, s=(NY, NX))
            est.append(continuous_argmax(S, winner(m)[0]))
        est = np.array(est)
        tmpl[label] = dict(estimate_xy=est.tolist(), **err(est, truth))
    c['S0_template_oracle'] = tmpl
    c['backends'] = {}
    for backend in ['cpu', 'cuda']:
        base = f'runs/{backend}-{case}-on/capture/c1'
        meta = json.loads(load(base+'.json'))
        assert (meta['patch_nxy'], meta['ccf_nxy'], meta['search'], meta['scale_xy'], meta['B']) == ([NX, NY], [NX, NY], SEARCH, [1, 1], B)
        wcap = np.frombuffer(load(base+'-i0-weight.bin'), '<f4').reshape(NY, NFX)
        F1 = np.frombuffer(load(base+'-i1-input.bin'), '<c8').reshape(NF, NY, NFX)
        b = dict(weight_max_abs_vs_double=float(np.abs(wcap-W).max()),
                 S1_forward_max_abs_vs_double_rfft=float(np.abs(F1-Fm).max()),
                 S1_dc=float(F1[0, 0, 0].real))
        # S2 native map quantisation and float inverse error, every iteration/frame.
        rows = []
        it = 1
        while (RAW/f'{base}-i{it}-candidate.bin').exists():
            cand = np.frombuffer(load(f'{base}-i{it}-candidate.bin'), '<f8').reshape(NF, 2)
            if backend == 'cuda':  # one batched file per iteration; CUDA spectrum is post-Hermitian projection
                maps = np.frombuffer(load(f'{base}-i{it}-map.bin'), '<f4').reshape(NF, NY, NX)
                specs = np.frombuffer(load(f'{base}-i{it}-spectrum.bin'), '<c8').reshape(NF, NY, NFX)
            for f in range(NF):
                if backend == 'cuda':
                    m, spec = maps[f], specs[f]
                else:
                    m = np.frombuffer(load(f'{base}-i{it}-map-f{f}.bin'), '<f4').reshape(NY, NX)
                    spec = np.frombuffer(load(f'{base}-i{it}-spectrum-f{f}.bin'), '<c8').reshape(NY, NFX)
                exact = np.fft.irfft2(spec.astype(np.complex128), s=(NY, NX))*(NX*NY)
                (px, py), mx = winner(m); u = float(np.spacing(np.float32(mx)))
                win = np.array([[m[y % NY, x % NX] for x in range(-SEARCH, SEARCH+1)] for y in range(-SEARCH, SEARCH+1)])
                vx = (float(m[py % NY, (px+1) % NX]), float(m[py % NY, (px-1) % NX])); vy = (float(m[(py+1) % NY, px % NX]), float(m[(py-1) % NY, px % NX]))
                rows.append(dict(iteration=it, frame=f, winner=[px, py], peak=float(mx), ulp=u,
                    exact_ties=int((win == mx).sum()), window_range=float(win.max()-win.min()),
                    window_range_ulps=float((win.max()-win.min())/u),
                    d2x_ulps=(vx[0]+vx[1]-2*float(mx))/u, d1x_ulps=(vx[0]-vx[1])/u,
                    d2y_ulps=(vy[0]+vy[1]-2*float(mx))/u, d1y_ulps=(vy[0]-vy[1])/u,
                    inverse_max_abs_err_ulps=float(np.abs(m-exact).max()/u),
                    native_candidate=cand[f].tolist()))
            it += 1
        b['S2_map_rows'] = rows
        d2 = np.array([[r_['d2x_ulps'], r_['d2y_ulps']] for r_ in rows]).ravel()
        b['S2_summary'] = dict(records=len(rows), curvature_ulps_min=float(np.abs(d2).min()), curvature_ulps_max=float(np.abs(d2).max()),
            all_finite_differences_integer_ulps=bool(all(float(v).is_integer() for r_ in rows for v in (r_['d2x_ulps'], r_['d1x_ulps'], r_['d2y_ulps'], r_['d1y_ulps']))),
            window_range_ulps_max=float(max(r_['window_range_ulps'] for r_ in rows)),
            inverse_err_ulps_max=float(max(r_['inverse_max_abs_err_ulps'] for r_ in rows)),
            records_with_exact_ties=int(sum(r_['exact_ties'] > 1 for r_ in rows)))
        # Earliest stage: identical iteration-1 state; exact objective vs native candidate.
        F1d = F1.astype(np.complex128); n1 = np.frombuffer(load(base+'-i1-candidate.bin'), '<f8').reshape(NF, 2)
        i1 = []
        for f in range(NF):
            m = ccf_map(F1d, f, False); p, wpos = parabola(m)
            S = (F1d.sum(0)-F1d[f])*np.conj(F1d[f])*W
            i1.append(dict(frame=f, native=n1[f].tolist(), exact_objective_parabola=p.tolist(), exact_winner=list(wpos),
                           exact_objective_continuous=continuous_argmax(S, wpos).tolist(),
                           native_minus_exact_parabola_px=float(np.linalg.norm(n1[f]-p))))
        b['S2_iteration1_same_state'] = i1
        final_native = np.frombuffer(load(f'{base}-i{it-1}-after.bin'), '<f8').reshape(NF, 2)
        b['native_final'] = dict(trajectory_xy=final_native.tolist(), iterations=it-1, **err(final_native, truth))
        # S3 offline replays from the identical captured iteration-1 frame spectra.
        rep = {}
        # (label, fixed reference, float32 map, max_iter, tolerance, estimator). Only the
        # first row is the specified algorithm; the others each change one component.
        arms = (('sum_of_others_double', False, False, 5, TOL, 'parabola'),
                ('sum_of_others_float32_map', False, True, 5, TOL, 'parabola'),
                ('sum_of_others_double_max_iter20', False, False, 20, TOL, 'parabola'),
                ('sum_of_others_double_tol1e-9_max_iter50', False, False, 50, 1e-9, 'parabola'),
                ('sum_of_others_double_continuous', False, False, 5, TOL, 'continuous'),
                ('sum_of_others_double_continuous_tol1e-9_max_iter50', False, False, 50, 1e-9, 'continuous'),
                ('fixed_frame0_double', True, False, 5, TOL, 'parabola'),
                ('fixed_frame0_float32_map', True, True, 5, TOL, 'parabola'),
                ('fixed_frame0_double_tol1e-9_max_iter50', True, False, 50, 1e-9, 'parabola'),
                ('fixed_frame0_double_continuous', True, False, 5, TOL, 'continuous'))
        for label, fixed, quant, mi, tol, est in arms:
            acc, its, conv = replay(F1, fixed, quant, mi, tol, est, truth)
            rep[label] = dict(trajectory_xy=acc.tolist(), iterations=len(its), converged=conv,
                              per_iteration=its, **err(acc, truth))
        b['S3_offline_replays'] = rep
        c['backends'][backend] = b
    result['cases'][case] = c
result['bindings'] = bound
result['script_sha256'] = sha(pathlib.Path(__file__).read_bytes())
OUT.write_text(json.dumps(result, indent=1, allow_nan=False)+'\n')
for case, c in result['cases'].items():
    print(case, 'S0', c['S0_input'], {k: round(v['rms_px'], 9) for k, v in c['S0_template_oracle'].items()})
    for be, b in c['backends'].items():
        print(' ', be, 'fwd', b['S1_forward_max_abs_vs_double_rfft'], 'S2', b['S2_summary'])
        print('   i1 native-exact', [round(x['native_minus_exact_parabola_px'], 4) for x in b['S2_iteration1_same_state']])
        print('   native', round(b['native_final']['rms_px'], 4), {k: (round(v['rms_px'], 4), v['iterations'], v['converged']) for k, v in b['S3_offline_replays'].items()})
