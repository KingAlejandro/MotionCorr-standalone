"""Independent reviewer reproduction of the fixed-G native-18 RMS floor.

Different route from oracle_floor.py: Kronecker projector P_T (exact rational,
5x3 temporal) x P_S (Householder QR, spatial 6 columns), own STAR/JSON parsing,
no import of the parent adapters or consumer tools. Truth-accessible oracle
only; no movie intensities, no native producer.
"""
from fractions import Fraction
from pathlib import Path
import hashlib, json, sys
import numpy as np

RAW = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-factorial-parent-audit-r1/raw')
FIX = Path('/tmp/motioncorr-b2-retained-challenge-20261026/v2fixtures')
PARENT = Path('/tmp/mc-local-full-width-pilot-20261026/ORACLE_FLOOR_RESULT.json')
LIM = {'rms': .20, 'p95': .40, 'max': .80}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def star_global(path, nf):
    lines = Path(path).read_text().splitlines()
    i = lines.index('data_global_shift')
    g = {}
    for ln in lines[i + 1:]:
        if ln.startswith('data_'): break
        w = ln.split()
        if len(w) == 3 and not w[0].startswith(('_', '#')): g[int(w[0])] = (float(w[1]), float(w[2]))
    assert sorted(g) == list(range(1, nf + 1))
    return np.array([g[k] for k in range(1, nf + 1)])

def metrics(e_px, ps):
    v = np.linalg.norm(e_px * ps, axis=-1).ravel()
    return dict(rms=float(np.sqrt(np.mean(v * v))), p95=float(np.percentile(v, 95)), max=float(v.max()))

# Exact temporal projector onto span{f,f^2,f^3}, f=0..4.
F = [[Fraction(f ** k) for k in (1, 2, 3)] for f in range(5)]
def matmul(a, b): return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]
def transpose(a): return [list(r) for r in zip(*a)]
def inv(m):
    n = len(m); a = [r[:] + [Fraction(int(i == j)) for j in range(n)] for i, r in enumerate(m)]
    for c in range(n):
        p = next(r for r in range(c, n) if a[r][c] != 0); a[c], a[p] = a[p], a[c]
        a[c] = [x / a[c][c] for x in a[c]]
        for r in range(n):
            if r != c: a[r] = [x - a[r][c] * y for x, y in zip(a[r], a[c])]
    return [r[n:] for r in a]
Tpinv = matmul(inv(matmul(transpose(F), F)), transpose(F))      # 3x5 exact
PT_exact = matmul(F, Tpinv)                                      # 5x5 exact
PT = np.array([[float(x) for x in r] for r in PT_exact]); Tp = np.array([[float(x) for x in r] for r in Tpinv])
null_exact = [[int(i == j) - PT_exact[i][j] for j in range(5)] for i in range(5)]

manifest = json.loads((FIX / 'MANIFEST.json').read_text())
assert sha(FIX / 'MANIFEST.json') == '9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc'
parent = {(r['case'], r['fixed_global']): r for r in json.loads(PARENT.read_text())['rows']}
out = dict(temporal_null_projector_exact=[[str(x) for x in r] for r in null_exact], rows=[])
for case in ['noisy', 'affine']:
    m = manifest['cases'][case]; r = m['recipe']; y0, y1, x0, x1 = m['roi']; ps = r['pixel_size']
    truth_full = np.load(FIX / f'{case}_field.npy', allow_pickle=False)
    assert sha(FIX / f'{case}_field.npy') == m['files'][f'{case}_field.npy']
    truth = truth_full[:, y0:y1, x0:x1].reshape(5, -1, 2)
    yy, xx = np.mgrid[y0:y1, x0:x1]; u = xx.ravel() / r['nx'] - .5; v = yy.ravel() / r['ny'] - .5
    S = np.column_stack([np.ones_like(u), u, u * u, v, v * v, u * v])
    Q, Rr = np.linalg.qr(S)                                     # Householder QR
    rt = json.loads((RAW / case / 'UP_only/runtime.json').read_text())
    Gs = {'runtime': np.array(rt['global'], float),
          'STAR': star_global(RAW / case / 'UP_only/output' / f'{case}.star', 5)}
    # Basis identity: native runtime local part must lie exactly in span(T (x) S).
    C = np.array([rt['coeff_x'], rt['coeff_y']]).reshape(2, 6, 3)
    z = np.arange(5.); T = np.column_stack([z, z * z, z ** 3])
    native_local = np.einsum('agt,ft,pg->fpa', C, T, S)
    nl_res = max(np.abs(native_local[..., a] - PT @ native_local[..., a] @ Q @ Q.T).max() for a in range(2))
    for label, G in Gs.items():
        X = truth - G[:, None, :]
        fit = np.stack([PT @ X[..., a] @ Q @ Q.T for a in range(2)], -1)
        res = fit - X                                            # field - truth
        temporal_null = np.stack([(np.eye(5) - PT) @ X[..., a] for a in range(2)], -1)
        spatial_nonrep = np.stack([PT @ X[..., a] - PT @ X[..., a] @ Q @ Q.T for a in range(2)], -1)
        coeff = np.stack([np.linalg.solve(Rr, Q.T @ (Tp @ X[..., a]).T) for a in range(2)])  # (2,6,3)
        recon = np.einsum('ags,fs,pg->fpa', coeff, T, S) - X
        mt = metrics(res, ps); pr = parent[(case, label)]
        # STAR serialisation bound: |delta field| <= sum_k|S_k| * sum_s|T_s| * eps per axis.
        smax = np.abs(S).sum(1).max(); tmax = np.abs(T).sum(1).max()
        rows = {}
        for eps in (5e-6, 1e-4):
            d = float(np.sqrt(2) * smax * tmax * eps * ps)
            rows[str(eps)] = dict(vector_bound_A=d, rms_upper_A=mt['rms'] + d, p95_upper_A=mt['p95'] + d, max_upper_A=mt['max'] + d,
                                  passes_all=bool(mt['rms'] + d <= .2 and mt['p95'] + d <= .4 and mt['max'] + d <= .8))
        rounded = np.round(coeff, 5)
        rmet = metrics(np.einsum('ags,fs,pg->fpa', rounded, T, S) - X, ps)
        out['rows'].append(dict(
            case=case, fixed_global=label, G_px=G.tolist(), roi=m['roi'], n_points=int(u.size),
            reviewer_metrics_A=mt, parent_rms_A=pr['rms_floor_A'], abs_diff_rms_A=abs(mt['rms'] - pr['rms_floor_A']),
            abs_diff_p95_A=abs(mt['p95'] - pr['p95_at_RMS_optimum_A_NOT_FLOOR']), abs_diff_max_A=abs(mt['max'] - pr['max_at_RMS_optimum_A_NOT_FLOOR']),
            coeff_max_abs_diff_vs_parent_px=float(np.abs(coeff.reshape(2, 18).T - np.array(pr['oracle_coefficients_px'])).max()),
            coeff_max_abs_px=float(np.abs(coeff).max()),
            native_local_in_span_max_px=float(nl_res),
            reconstruction_closure_px=float(np.abs(recon - res).max()),
            ss_temporal_null_A2=float(np.sum((temporal_null * ps) ** 2)),
            ss_spatial_nonrep_A2=float(np.sum((spatial_nonrep * ps) ** 2)),
            ss_total_A2=float(np.sum((res * ps) ** 2)),
            pythagoras_closure_rel=float(abs(np.sum(res ** 2) - np.sum(temporal_null ** 2) - np.sum(spatial_nonrep ** 2)) / np.sum(res ** 2)),
            frame0_rms_A=float(np.sqrt(np.mean(np.sum((X[0] * ps) ** 2, -1)))),
            truth_frame0_max_px=float(np.abs(truth[0]).max()),
            G_tv_component_px=[float(np.array([0, -4, 6, -4, 1]) @ G[:, a] / np.sqrt(69)) for a in range(2)],
            truth_mean_tv_component_px=[float(np.array([0, -4, 6, -4, 1]) @ truth[:, :, a].mean(1) / np.sqrt(69)) for a in range(2)],
            star_serialisation_bound=rows,
            rounded_5dp_coeff_metrics_A=rmet, rounded_5dp_passes_all=all(rmet[k] <= LIM[k] for k in LIM)))
out['python'] = sys.version; out['numpy'] = np.__version__
Path(sys.argv[1]).write_text(json.dumps(out, indent=2, allow_nan=False) + '\n')
for row in out['rows']:
    print(row['case'], row['fixed_global'], row['reviewer_metrics_A'], 'drms', row['abs_diff_rms_A'], 'dcoef', row['coeff_max_abs_diff_vs_parent_px'],
          'span', row['native_local_in_span_max_px'], 'tn/sn', row['ss_temporal_null_A2'], row['ss_spatial_nonrep_A2'], 'f0', row['frame0_rms_A'], 'rnd', row['rounded_5dp_passes_all'], row['star_serialisation_bound']['0.0001']['passes_all'], 'cmax', row['coeff_max_abs_px'])
