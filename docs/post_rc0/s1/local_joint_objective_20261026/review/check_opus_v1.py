"""Opus independent checks (pre-registered in this header; no captured objective values, no optimisation, no truth).
A. Saved-array facts, both patches: saved weights vs formula; Nyquist row (y=16) / column (x=21) weight maxima;
   Nyquist share of the state-independent magnitude bound sum mW|F_j||F_f| over initial spectra; DC of initial
   spectra and of pre-dc/consumed CCF inputs; iter2 enter == iter1 exit bitwise; enter shifts.
B. Independent objective: native-literal leave-one-out (Fref - F_f) conj(F_f) W, DC zero, explicit slow raw-half-plane
   lag sum (no FFT), synthetic spectra WITH y16/x21 content, B=2; compare with Sonnet core value, FD gradient, Hessian.
C. C9 normalisation: for the Sonnet swap/sign mutants report |dJ|/Jscale and |dJ|/|J| and |J|/Jscale.
Pre-declared: B agreement rel <= 1e-12 (values), FD grad <= 1e-7*Jscale. C is descriptive only, no gate.
"""
import os, sys, json, hashlib
for v in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","VECLIB_MAXIMUM_THREADS","MKL_NUM_THREADS"): os.environ[v]="1"
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sonnet_core_copy as sc
CAP = "/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/native-map-bundle-r1/evidence/runs/ON/capture"
out = {"A": {}, "B": {}, "C": {}}
def ld(p, shape, dt):
    b = open(p, "rb").read(); return np.frombuffer(b, dtype=dt).reshape(shape), hashlib.sha256(b).hexdigest()
def cplx(p):
    a, h = ld(p, (32, 22, 2), "<f4"); return (a[..., 0].astype(np.float64) + 1j * a[..., 1]), h
for patch in ("patch-62-47", "patch-62-79"):
    P = os.path.join(CAP, patch); r = {}
    W, r["weights_sha256"] = ld(P + "/weights.bin", (32, 22), "<f4"); W = W.astype(np.float64)
    Wf = np.float32(sc.native_weight(150.0)).astype(np.float64)
    r["weights_vs_formula_f32_maxabs"] = float(np.abs(W - Wf).max())
    r["W_max_row_y16"] = float(W[16].max()); r["W_max_col_x21"] = float(W[:, 21].max())
    r["W_nonzero_count_x21"] = int((W[:, 21] != 0).sum()); r["W_min_positive"] = float(W[W > 0].min())
    F = []; r["initial_fft_sha256"] = []
    for f in range(5):
        c, h = cplx(f"{P}/initial-frame{f}-fft.bin"); F.append(c); r["initial_fft_sha256"].append(h)
    F = np.array(F); r["initial_DC_abs"] = [float(abs(x[0, 0])) for x in F]
    Wm = W * sc.MX[None, :]; Wm[0, 0] = 0
    M = sum(Wm * np.abs(F[j]) * np.abs(F[k]) for j, k in sc.PAIRS)
    ny = np.zeros((32, 22), bool); ny[16, :] = True; ny[:, 21] = True
    r["magnitude_bound_total"] = float(M.sum()); r["magnitude_bound_nyquist_row_col"] = float(M[ny].sum())
    r["nyquist_share_of_bound"] = float(M[ny].sum() / M.sum())
    # gradient bound share: |omega| <= pi on Nyquist
    r["grad_bound_nyquist_abs"] = float((np.pi * M[ny]).sum())
    dc = {}
    for it in (1, 2):
        for f in range(5):
            pre, _ = cplx(f"{P}/iter{it}-frame{f}-weighted-pre-dc.bin"); con, _ = cplx(f"{P}/iter{it}-frame{f}-weighted-api-consumed.bin")
            dc[f"it{it}f{f}"] = [float(abs(pre[0, 0])), float(abs(con[0, 0])), float(np.abs(pre - con).max()), float(np.abs(con[16]).max()), float(np.abs(con[:, 21]).max())]
    r["ccf_input_[preDC|DC|,consumedDC|,max|pre-consumed|,max|consumed y16|,max|consumed x21|]"] = dc
    same = []
    for f in range(5):
        a = open(f"{P}/iter1-frame{f}-exit-fft.bin", "rb").read(); b = open(f"{P}/iter2-frame{f}-enter-fft.bin", "rb").read(); same.append(a == b)
    r["iter2_enter_eq_iter1_exit_bitwise"] = same
    e1 = open(f"{P}/iter1-frame0-enter-fft.bin","rb").read(); i0 = open(f"{P}/initial-frame0-fft.bin","rb").read()
    r["iter1_enter_eq_initial_frame0_bitwise"] = e1 == i0
    for nm in ("iter1-enter-shifts", "iter2-enter-shifts", "iter1-applied-deltas"):
        a, _ = ld(f"{P}/{nm}.bin", (5, 2), "<f8"); r[nm] = a.tolist()
    out["A"][patch] = r
# ---- B: independent native-literal objective with explicit slow raw-half-plane lag-0 sum
rng = np.random.Generator(np.random.PCG64(20261026))
F0 = np.fft.rfft2(rng.normal(size=(5, 32, 42)))  # keeps y16 and x21 content, Hermitian-valid R2C
Wb = sc.native_weight(2.0)
def J_native_literal(F0, W, s):
    kx = np.arange(22.0); ky = np.array([y if y <= 16 else y - 32 for y in range(32)], float)
    Fs = np.empty_like(F0)
    for f in range(5):  # native shifter: multiply by exp(i 2pi (x*shiftx + ly*shifty)), shift = -s/pn
        Fs[f] = F0[f] * np.exp(1j * 2 * np.pi * (kx[None, :] * (-s[f, 0] / 42) + ky[:, None] * (-s[f, 1] / 32)))
    ref = Fs.sum(0); tot = 0.0
    for f in range(5):
        S = (ref - Fs[f]) * np.conj(Fs[f]) * W; S[0, 0] = 0
        lag0 = 0.0  # raw half-plane c2r value at r=0: full complex column sum, multiplicity 1 at x=0,21
        for x in range(22):
            lag0 += (1.0 if x in (0, 21) else 2.0) * S[:, x].sum().real
        tot += lag0
    return 0.5 * tot
obj = sc.JointObjective(F0, Wb); worst_v = 0; worst_g = 0; worst_h = 0
for t in range(10):
    s = np.vstack([np.zeros((1, 2)), rng.normal(0, 1.7, size=(4, 2))])
    worst_v = max(worst_v, abs(J_native_literal(F0, Wb, s) - obj.value(s)) / obj.jscale)
    _, g = obj.value_grad(s); h = 1e-5; gfd = np.zeros_like(s)
    for i in range(5):
        for a in range(2):
            sp = s.copy(); sm = s.copy(); sp[i, a] += h; sm[i, a] -= h
            gfd[i, a] = (J_native_literal(F0, Wb, sp) - J_native_literal(F0, Wb, sm)) / (2 * h)
    worst_g = max(worst_g, np.abs(g - gfd).max() / obj.jscale)
    H = obj.hessian(s); Hfd = np.zeros((10, 10))
    for i in range(10):
        sp = s.ravel().copy(); sm = sp.copy(); sp[i] += h; sm[i] -= h
        Hfd[:, i] = (obj.value_grad(sp.reshape(5, 2))[1].ravel() - obj.value_grad(sm.reshape(5, 2))[1].ravel()) / (2 * h)
    worst_h = max(worst_h, np.abs(H - Hfd).max() / obj.jscale)
out["B"] = {"value_rel_max": worst_v, "grad_vs_literalFD_rel_max": worst_g, "hess_vs_FD_rel_max": worst_h,
            "pass_value_1e-12": worst_v <= 1e-12, "pass_grad_1e-7": worst_g <= 1e-7}
# ---- C: mutant normalisation (descriptive)
rows = []
for Bv in (150.0, 2.0):
    W = sc.native_weight(Bv); F = np.fft.rfft2(rng.normal(size=(5, 32, 42)))
    o = sc.JointObjective(F, W); osw = sc.JointObjective(F, W, swap=True); osg = sc.JointObjective(F, W, sign=-1)
    for t in range(200):
        s = np.vstack([np.zeros((1, 2)), rng.normal(0, 1.7, size=(4, 2))]); J = o.value(s)
        rows.append((Bv, abs(osw.value(s) - J) / o.jscale, abs(osg.value(s) - J) / o.jscale, abs(J) / o.jscale,
                     abs(osw.value(s) - J) / max(abs(J), 1e-300)))
rows = np.array(rows)
for Bv in (150.0, 2.0):
    R = rows[rows[:, 0] == Bv]
    out["C"][f"B{int(Bv)}"] = {"swap_dJ_over_Jscale_min": float(R[:, 1].min()), "swap_dJ_over_Jscale_median": float(np.median(R[:, 1])),
        "frac_swap_below_1e-3": float((R[:, 1] < 1e-3).mean()), "sign_dJ_over_Jscale_min": float(R[:, 2].min()),
        "absJ_over_Jscale_median": float(np.median(R[:, 3])), "swap_dJ_over_absJ_median": float(np.median(R[:, 4]))}
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_opus_v1_result.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
