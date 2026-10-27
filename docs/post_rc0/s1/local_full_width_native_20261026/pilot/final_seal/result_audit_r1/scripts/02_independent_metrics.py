"""Independent field recomputation for the 16 native runs (own STAR parser, own 18-term basis; no pinned/author code).
Truth: bundle truth/<case>_field.npy (F,ny,nx,2) px, frame-0 gauge. Field = global[f] + sum_g S_g(u,v) * sum_k c[3g+k] z^(k+1),
z = frame index (0..4; STAR: frame - StartFrame), u = x/nx - .5, v = y/ny - .5, S = [1,u,u^2,v,v^2,uv].
ROI rows 12:84, cols 12:116; pixel 0.885 A; vector norm per pixel/frame over all 5 frames; rms/p95(linear)/max.
Usage: python3 -I -B 02_independent_metrics.py BUNDLE OUT.json"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
B, OUT = Path(sys.argv[1]), Path(sys.argv[2])
CASES = ['noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional', 'flat', 'repeated']
P1C = ['affine', 'pedestal', 'zero', 'integer', 'fractional']
LIM = {'rms': .20, 'p95': .40, 'max': .80}
ROI = (12, 84, 12, 116); PIX = 0.885; NX, NY, NF = 128, 96, 5
EXPECTED_TRUTH_MANIFEST = '9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def parse_star(path):
    blocks, cur = {}, None
    for line in Path(path).read_text().splitlines():
        s = line.strip()
        if s.startswith('data_'): cur = s; blocks[cur] = {'labels': [], 'rows': [], 'pairs': {}}; continue
        if not s or s.startswith('#') or s == 'loop_' or cur is None: continue
        if s.startswith('_'):
            t = s.split()
            if len(t) >= 2 and not t[1].startswith('#'): blocks[cur]['pairs'][t[0]] = t[1]
            else: blocks[cur]['labels'].append(t[0])
        else: blocks[cur]['rows'].append(s.split())
    return blocks

def basis(z, x, y):
    u, v = x / NX - .5, y / NY - .5
    S = np.stack([np.ones_like(u), u, u * u, v, v * v, u * v])            # (6,P)
    T = np.stack([z, z ** 2, z ** 3])                                       # (3,F)
    return S, T

def poly_field(cx, cy, glob, frames_z):
    yy, xx = np.mgrid[:NY, :NX].astype(float)
    S, T = basis(np.asarray(frames_z, float), xx.ravel(), yy.ravel())
    out = np.zeros((len(frames_z), NY * NX, 2))
    for a, c in enumerate((cx, cy)):
        C = np.asarray(c, float).reshape(6, 3)                              # group g, power k
        out[..., a] = np.einsum('gk,kf,gp->fp', C, T, S)
    out += np.asarray(glob, float)[:, None, :]
    return out.reshape(len(frames_z), NY, NX, 2)

def metrics(err):
    n = np.sqrt((err ** 2).sum(-1)).ravel()
    return {'rms': float(np.sqrt(np.mean(n * n))), 'p95': float(np.percentile(n, 95)), 'max': float(n.max())}

res = {'checks': {}, 'runs': {}}
tm = B / 'truth' / 'MANIFEST.json'
res['checks']['truth_manifest_sha256_ok'] = sha(tm) == EXPECTED_TRUTH_MANIFEST
man = json.loads(tm.read_text())
truth = {}
for c in CASES:
    meta = man['cases'][c]; r = meta['recipe']
    assert (r['nx'], r['ny'], r['frames'], r['pixel_size']) == (NX, NY, NF, PIX), c
    assert list(meta['roi']) == list(ROI), c
    p = B / 'truth' / f'{c}_field.npy'
    assert sha(p) == meta['files'][f'{c}_field.npy'], c
    t = np.load(p, allow_pickle=False)
    assert t.shape == (NF, NY, NX, 2) and t.dtype == np.float64 and np.isfinite(t).all(), c
    truth[c] = t
    res['checks'][f'truth_{c}'] = {'shape': list(t.shape), 'dtype': str(t.dtype), 'finite': True, 'frame0_max_abs_px': float(np.abs(t[0]).max()),
                                   'motion': r['motion'], 'noise': r['noise'], 'role': r.get('role')}
res['checks']['case_names'] = {'list': CASES, 'unique': len(set(CASES)) == 8, 'manifest_cases': sorted(man['cases'])}
roi_mask = np.zeros((NY, NX), bool); roi_mask[ROI[0]:ROI[1], ROI[2]:ROI[3]] = True
res['checks']['roi'] = {'rows': ROI[1] - ROI[0], 'cols': ROI[3] - ROI[2], 'pixels_per_frame': int(roi_mask.sum()), 'vectors_total': int(roi_mask.sum()) * NF}

for c in CASES:
    for a in ('OFF', 'ON'):
        d = B / 'runs' / c / a
        rt = json.loads((d / 'runtime.json').read_text(), parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
        g = np.asarray(rt['global'], float); cx = np.asarray(rt['coeff_x'], float); cy = np.asarray(rt['coeff_y'], float)
        assert g.shape == (5, 2) and cx.shape == cy.shape == (18,) and type(rt['local_enabled']) is bool
        assert np.isfinite(g).all() and np.isfinite(cx).all() and np.isfinite(cy).all()
        st = parse_star(d / f'{c}.star')
        gen = st['data_general']['pairs']
        assert gen['_rlnMicrographMovieName'] == f'{c}.mrcs', (c, a)
        assert (int(gen['_rlnImageSizeX']), int(gen['_rlnImageSizeY']), int(gen['_rlnImageSizeZ'])) == (NX, NY, NF)
        f0 = int(gen['_rlnMicrographStartFrame']); assert f0 == 1
        gs = st['data_global_shift']; frames = [int(r[0]) for r in gs['rows']]
        assert frames == [1, 2, 3, 4, 5], frames
        sg = np.array([[float(r[1]), float(r[2])] for r in gs['rows']])
        lm = st.get('data_local_motion_model')
        if lm is not None:
            idx = [int(r[0]) for r in lm['rows']]; assert idx == list(range(36))
            co = np.array([float(r[1]) for r in lm['rows']]); scx, scy = co[:18], co[18:]
        else: scx = scy = np.zeros(18)
        ls = st.get('data_local_shift'); nls = len(ls['rows']) if ls else 0
        patch_centres = sorted({(float(r[1]), float(r[2])) for r in ls['rows']}) if ls else []
        z = np.arange(NF, dtype=float)
        frt = poly_field(cx, cy, g, z)
        fst = poly_field(scx, scy, sg, np.array(frames, float) - f0)
        assert np.isfinite(frt).all() and np.isfinite(fst).all()
        t = truth[c]
        row = {'local_enabled': rt['local_enabled'], 'runtime_global_frame0': g[0].tolist(), 'star_global_frame0': sg[0].tolist(),
               'runtime_coeffs_all_zero': bool(not cx.any() and not cy.any()), 'star_has_local_model': lm is not None,
               'star_local_shift_rows': nls, 'star_local_patches_listed': len(patch_centres), 'patch_centres': patch_centres,
               'star_vs_runtime_global_max_abs_px': float(np.abs(sg - g).max()),
               'star_vs_runtime_coeff_max_abs': float(max(np.abs(scx - cx).max(), np.abs(scy - cy).max())),
               'roundtrip_vector_max_px': float(np.sqrt(((frt - fst) ** 2).sum(-1)).max())}
        for lab, f in (('runtime', frt), ('STAR', fst)):
            e = (f - t)[:, ROI[0]:ROI[1], ROI[2]:ROI[3]]
            assert e.shape == (5, 72, 104, 2)
            mA = metrics(e * PIX)
            row[lab] = {'angstrom': mA, 'px': metrics(e), 'gate': 'PASS' if all(mA[k] <= LIM[k] for k in LIM) else 'FAIL'}
        res['runs'][f'{c}/{a}'] = row

# frozen-rule derivations
R = res['runs']
p1 = {c: {a: {f: R[f'{c}/{a}'][f]['gate'] for f in ('runtime', 'STAR')} for a in ('OFF', 'ON')} for c in P1C}
p1_ok = all(v == 'PASS' for c in p1.values() for a in c.values() for v in a.values())
p2 = {f: {k: {'OFF': R['noisy/OFF'][f]['angstrom'][k], 'ON': R['noisy/ON'][f]['angstrom'][k],
              'strictly_lower': R['noisy/ON'][f]['angstrom'][k] < R['noisy/OFF'][f]['angstrom'][k]} for k in ('rms', 'p95', 'max')} for f in ('runtime', 'STAR')}
p2_ok = all(p2[f][k]['strictly_lower'] for f in p2 for k in p2[f])
increases, equal = [], []
for c in CASES:
    for f in ('runtime', 'STAR'):
        for k in ('rms', 'p95', 'max'):
            o, n = R[f'{c}/OFF'][f]['angstrom'][k], R[f'{c}/ON'][f]['angstrom'][k]
            if n > o: increases.append({'case': c, 'field': f, 'metric': k, 'OFF': o, 'ON': n, 'gates': [R[f'{c}/OFF'][f]['gate'], R[f'{c}/ON'][f]['gate']]})
            elif n == o: equal.append(f'{c}/{f}/{k}')
noisy_gate = {f: R['noisy/ON'][f]['gate'] for f in ('runtime', 'STAR')}
res['derived'] = {'P1': p1, 'P1_ok': p1_ok, 'P2': p2, 'P2_ok': p2_ok, 'increases': increases, 'exactly_equal_OFF_ON': equal,
                  'noisy_raw_gate_ON': noisy_gate, 'noisy_raw_gate_OFF': {f: R['noisy/OFF'][f]['gate'] for f in ('runtime', 'STAR')},
                  'prediction_if_P1_and_P2': 'SUPPORTED' if (p1_ok and p2_ok) else 'NOT_SUPPORTED'}

# compare to DECISION.json and to the user's expected values
dec = json.loads((B / 'decision_r2' / 'DECISION.json').read_text())
diffs = []
for f in ('runtime', 'STAR'):
    for k in ('rms', 'p95', 'max'):
        for a in ('OFF', 'ON'): diffs.append(abs(p2[f][k][a] - dec['P2']['noisy'][f][k][a]))
        assert p2[f][k]['strictly_lower'] == dec['P2']['noisy'][f][k]['strictly_lower']
for c in ('flat', 'repeated'):
    assert dec['unidentifiable'][c]['status'] == 'UNIDENTIFIABLE'
    for a in ('OFF', 'ON'):
        for f in ('runtime', 'STAR'):
            for k in ('rms', 'p95', 'max'):
                diffs.append(abs(R[f'{c}/{a}'][f]['angstrom'][k] - dec['unidentifiable'][c]['raw_distances_angstrom'][a][f][k]))
                diffs.append(abs(R[f'{c}/{a}'][f]['px'][k] - dec['unidentifiable'][c]['raw_distances_px'][a][f][k]))
exp = {'rms': (1.6453708531561486, 1.095426088140216), 'p95': (3.337290305991788, 2.240216728988467), 'max': (7.284025716813742, 4.4692154437241225)}
ediff = max(abs(p2['runtime'][k][i] - exp[k][j]) for k in exp for i, j in (('OFF', 0), ('ON', 1)))
res['vs_decision'] = {'max_abs_diff_A_or_px': max(diffs), 'within_1e-12': max(diffs) <= 1e-12, 'P1_equal': p1 == dec['P1']['cases'], 'P1_ok_equal': p1_ok == dec['P1']['ok'],
                      'P2_ok_equal': p2_ok == dec['P2']['ok'], 'increases_equal': increases == dec['increases'], 'noisy_raw_gate_equal': noisy_gate == dec['noisy_raw_gate_by_field'],
                      'prediction_equal': res['derived']['prediction_if_P1_and_P2'] == dec['prediction'], 'user_expected_runtime_max_abs_diff_A': ediff}
OUT.write_text(json.dumps(res, indent=1, allow_nan=False) + '\n')
print(json.dumps(res['vs_decision'], indent=1)); print('P1_ok', p1_ok, 'P2_ok', p2_ok, 'increases', increases, 'noisy gate ON', noisy_gate)
for k, v in R.items():
    print(f"{k:16s} rt {v['runtime']['angstrom']['rms']:.6f} {v['runtime']['angstrom']['p95']:.6f} {v['runtime']['angstrom']['max']:.6f} {v['runtime']['gate']} | "
          f"STAR {v['STAR']['angstrom']['rms']:.6f} {v['STAR']['angstrom']['p95']:.6f} {v['STAR']['angstrom']['max']:.6f} {v['STAR']['gate']} | rt {v['roundtrip_vector_max_px']:.2e} "
          f"le={v['local_enabled']} lsrows={v['star_local_shift_rows']} g0={v['runtime_global_frame0']}/{v['star_global_frame0']}")
