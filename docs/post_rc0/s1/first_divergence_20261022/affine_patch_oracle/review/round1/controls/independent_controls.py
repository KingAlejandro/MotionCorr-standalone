#!/usr/bin/env python3
"""Reviewer controls for the W4 affine patch oracle (R1). Independent code paths:
full complex fft2 (no rfft/Hermitian multiplicity), 64x zero-padded upsampled CCF
grid search plus local golden refinement (no analytic Newton), own render.
usage: independent_controls.py RAW INDEX ATTEMPT02_JSON OUT.json"""
import hashlib, json, pathlib, sys
import numpy as np
RAW, INDEX, AJ, OUT = (pathlib.Path(a) for a in sys.argv[1:5])
idx = json.loads(INDEX.read_bytes())['files']
def load(rel):
    b = (RAW / rel).read_bytes(); assert hashlib.sha256(b).hexdigest() == idx[rel]['sha256'], rel; return b
A = json.loads(AJ.read_text())
NX, NY, PX, PY, X0, Y0, B, S = 128, 96, 42, 32, 0, 32, 150.0, 15
# own signal from the fixture constants (generator test-data/generate_motion_diagnostics.py, read not imported)
WAVES = [(3, 2, 1.0, 0.2), (7, -3, 0.7, 1.1), (11, 5, 0.5, -0.4), (19, -13, 0.25, 0.7)]
LAND = [(31, 23, 3.0, 3.0), (82, 57, -2.0, 5.0), (103, 34, 2.0, 4.0)]
def sig(x, y):
    s = 100.0 + 0 * x
    for kx, ky, a, p in WAVES: s = s + a * np.cos(2 * np.pi * (kx * x / NX + ky * y / NY) + p)
    for cx, cy, a, w in LAND: s = s + a * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * w * w))
    return s
yy, xx = np.mgrid[Y0:Y0 + PY, X0:X0 + PX].astype(float)
# full-plane weight, same inherited formula: |kx|/(PX//2+1), ky/PY
kx = np.fft.fftfreq(PX, 1 / PX); ky = np.fft.fftfreq(PY, 1 / PY)
W = np.exp(-2 * B * ((ky[:, None] / PY) ** 2 + (np.abs(kx)[None, :] / (PX // 2 + 1)) ** 2))
UP = 64
def ccf_max(ref, img):
    """argmax of IFFT[F(ref) conj(F(img)) W] via zero-padded upsampling, then local refinement."""
    P = np.fft.fft2(ref) * np.conj(np.fft.fft2(img)) * W
    big = np.zeros((PY * UP, PX * UP), complex)
    # place spectrum (drop Nyquist row/col: weight there is < 1e-30)
    for j, vy in enumerate(ky):
        for i, vx in enumerate(kx):
            if abs(vy) == PY // 2 or abs(vx) == PX // 2: continue
            big[int(vy) % (PY * UP), int(vx) % (PX * UP)] = P[j, i]
    m = np.real(np.fft.ifft2(big))
    dy = (np.arange(PY * UP) + PY * UP // 2) % (PY * UP) - PY * UP // 2
    dx = (np.arange(PX * UP) + PX * UP // 2) % (PX * UP) - PX * UP // 2
    mask = (np.abs(dy)[:, None] <= S * UP) & (np.abs(dx)[None, :] <= S * UP)
    j, i = np.unravel_index(np.argmax(np.where(mask, m, -np.inf)), m.shape)
    d = np.array([dx[i] / UP, dy[j] / UP])
    def f(dd):
        ex = np.exp(2j * np.pi * kx * dd[0] / PX); ey = np.exp(2j * np.pi * ky * dd[1] / PY)
        return float(np.real(ey @ P @ ex))
    # coordinate refinement by shrinking pattern search (derivative-free)
    h = 1.0 / UP
    while h > 1e-9:
        best = f(d); moved = False
        for v in ((h, 0), (-h, 0), (0, h), (0, -h), (h, h), (-h, -h), (h, -h), (-h, h)):
            if f(d + v) > best: d = d + np.array(v); best = f(d); moved = True; break
        if not moved: h /= 2
    return d
out = {}
T = sig(xx, yy)
# C2: window-crop control, independent route
wc = []
for mu in [(1, 0), (0, -2), (-3, 2), (0.25, 0), (0, -0.5), (0.375, -0.625), (-1.3, 0.7)]:
    est = ccf_max(T, sig(xx + mu[0], yy + mu[1]))
    a = [r for r in A['window_crop_control'] if r['mu'] == list(map(float, mu))][0]
    wc.append(dict(mu=mu, independent=est.tolist(), author=a['continuous'], diff=float(np.abs(est - np.array(a['continuous'])).max())))
out['C2_window_crop_independent'] = wc
# C2b: same control with periodic content only (waves only, integer cycles per 42x32? no: per 128x96), and with
# the window-periodic harmonics, to show the bias is crop/edge driven, not estimator code
def sig_waves(x, y):
    s = 100.0 + 0 * x
    for k1, k2, a, p in [(3, 2, 1.0, 0.2), (7, -3, 0.7, 1.1), (11, 5, 0.5, -0.4)]:
        s = s + a * np.cos(2 * np.pi * (k1 * x / PX + k2 * y / PY) + p)
    return s
out['C2b_window_periodic_content_mu_0_-2'] = ccf_max(sig_waves(xx, yy), sig_waves(xx, yy - 2)).tolist()
# C3: R_fm independent: analytic deformed window vs analytic target window, per backend/frame
CEN = np.array([64.0, 48.0]); G = np.array([3.25, -2.125]); AU = np.array([[0.012, -0.008], [0.006, -0.010]])
def inv(f, px, py):
    t = f / 4; a = AU * t; g = G * t
    M = np.linalg.inv(np.eye(2) + a)
    rx, ry = px - g[0] - CEN[0], py - g[1] - CEN[1]
    return CEN[0] + M[0, 0] * rx + M[0, 1] * ry, CEN[1] + M[1, 0] * rx + M[1, 1] * ry
rfm = {}
for b in ('cpu', 'cuda'):
    gs = np.array([[float(v) for v in l.split()[1:]] for l in load(f'runs/{b}-affine-on/state/global.txt').decode().split('\n') if l.strip()])
    rows = []
    for f in range(1, 5):
        qx, qy = inv(f, xx - gs[f, 0], yy - gs[f, 1])
        est = ccf_max(T, sig(qx, qy))
        auth = A['estimates'][b][f]['analytic_fixed_template_continuous_Rfm']
        cx, cy = inv(f, 20.5 - gs[f, 0], 47.5 - gs[f, 1])
        tc = np.array([cx - 20.5, cy - 47.5])
        rows.append(dict(frame=f, independent=est.tolist(), author=auth, diff=float(np.abs(est - np.array(auth)).max()),
                         truth_centre_independent=tc.tolist(), truth_centre_author=A['decomposition'][b]['truth_centre'][f]))
    rfm[b] = rows
out['C3_Rfm_independent'] = rfm
# C1: frame-0 attribution (CPU). Double map from captured iteration-1 input, sum-of-others for frame 0.
def frame0(b):
    base = f'runs/{b}-affine-on/capture/'
    F = np.frombuffer(load(base + 'c2-i1-input.bin'), '<c8').reshape(5, PY, PX // 2 + 1).astype(complex)
    cand = np.frombuffer(load(base + 'c2-i1-candidate.bin'), '<f8').reshape(5, 2)
    ref = F[1:].sum(0)
    Wr = W[:, :PX // 2 + 1]
    m = np.fft.irfft2(ref * np.conj(F[0]) * Wr, s=(PY, PX)) * PX * PY
    if b == 'cpu':
        nm = np.stack([np.frombuffer(load(f'{base}c2-i1-map-f{f}.bin'), '<f4').reshape(PY, PX) for f in range(5)])[0]
    else:
        nm = np.frombuffer(load(f'{base}c2-i1-map.bin'), '<f4').reshape(5, PY, PX)[0]
    def par(mm, x, y):
        g = lambda xx_, yy_: float(mm[yy_ % PY, xx_ % PX])
        c = g(x, y); dx_ = g(x + 1, y) + g(x - 1, y) - 2 * c; dy_ = g(x, y + 1) + g(x, y - 1) - 2 * c
        return [x - 0.5 * (g(x + 1, y) - g(x - 1, y)) / dx_, y - 0.5 * (g(x, y + 1) - g(x, y - 1)) / dy_]
    ulp = float(np.spacing(np.float32(m[0, 0])))
    return dict(native_candidate_f0=cand[0].tolist(),
                double_parabola_at_00=par(m, 0, 0), double_parabola_at_m10=par(m, -1, 0),
                float32_parabola_at_m10=par(nm.astype(float), -1, 0), float32_parabola_at_00=par(nm.astype(float), 0, 0),
                double_values_ulps_rel_00={f'{x},{y}': (float(m[y % PY, x % PX] - m[0, 0]) / ulp) for x in (-2, -1, 0, 1) for y in (-1, 0, 1)},
                float32_values_ulps_rel_00={f'{x},{y}': (float(nm[y % PY, x % PX]) - float(nm[0, 0])) / ulp for x in (-2, -1, 0, 1) for y in (-1, 0, 1)})
out['C1_frame0_attribution'] = {b: frame0(b) for b in ('cpu', 'cuda')}
OUT.write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
