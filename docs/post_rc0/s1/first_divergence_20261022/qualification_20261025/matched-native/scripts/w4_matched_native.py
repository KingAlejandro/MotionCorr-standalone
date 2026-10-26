#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""W4 matched-native-input pass over the nine retained CPU patch captures, protocol w4-matched-native/v1.

Offline, NumPy only, no MotionCorr execution, no new estimator. Extends the reviewed same-sample steps
of affine_patch_oracle.py (affine-patch-oracle/v1, sha256 fc3f11b6…4d31 at 83db13d2; functions copied
verbatim) from patch (2,1) iteration 1 to every accepted CPU patch and every captured iteration, on
the native stored inputs, maps and candidates. "Continuous" below is a stationary point reached by local
Newton refinement from the best integer sample (not a certified global maximum).

usage: w4_matched_native.py INPUTS_DIR OUT.json
"""
import hashlib, json, sys, time
from pathlib import Path
import numpy as np

IN, OUT = Path(sys.argv[1]), Path(sys.argv[2])
t0 = time.time()
MANIFEST_SHA = 'b1f044efc54024918b8f27a4dd5a780f2165e8981b7a28bb7334074f02fec381'
NX, NY, NF = 128, 96, 5
PX, PY = 42, 32
NFXP = PX // 2 + 1
B, SEARCH, TOL = 150.0, 15, 0.5
# Existing bounds reused (reviewed oracle GATE and the Phase D regression bound); none is new.
LIM = dict(weight=1e-6, replay=1e-6, cmap=1e-9, rel_ac=1e-3, reg21=1e-8)
MATERIAL_PX = 0.15     # REPORT section 6 lower routing threshold, reused as the frozen "material" label
LOO_TOL, LOO_MAX = 1e-9, 60
sha = lambda b: hashlib.sha256(b).hexdigest()

man_raw = (IN / 'manifest/MANIFEST.json').read_bytes()
if sha(man_raw) != MANIFEST_SHA:
    raise SystemExit('manifest pin mismatch')
MAN = json.loads(man_raw)['files']
for rel, e in MAN.items():
    raw = (IN / rel).read_bytes()
    if sha(raw) != e['sha256'] or len(raw) != e['bytes']:
        raise SystemExit(f'input pin mismatch {rel}')


def load(rel, dt, shape):
    return np.frombuffer((IN / rel).read_bytes(), dt).reshape(shape)


# ------------------------------------------------ reviewed-oracle helpers (verbatim)
LYP = np.arange(PY); LYP = np.where(LYP > PY // 2, LYP - PY, LYP).astype(float)
KX = np.arange(NFXP).astype(float)
MULT = np.full(NFXP, 2.0); MULT[0] = 1.0; MULT[-1] = 1.0
WEIGHT = np.exp(-2 * B * ((LYP[:, None] / PY) ** 2 + (KX[None, :] / NFXP) ** 2))
AX = 2j * np.pi * KX / PX
AY = 2j * np.pi * LYP / PY


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


def parabola(m, pos, mx, eps=1e-15):
    px, py = pos
    out = []
    for vp, vn, p in ((float(m[py % PY, (px + 1) % PX]), float(m[py % PY, (px - 1) % PX]), px),
                      (float(m[(py + 1) % PY, px % PX]), float(m[(py - 1) % PY, px % PX]), py)):
        d = vp + vn - 2.0 * mx
        out.append(p - 0.5 * (vp - vn) / d if abs(d) > eps else float(p))
    return np.array(out)


def cont_eval(M, d):
    ex = np.exp(2j * np.pi * KX * d[0] / PX)
    ey = np.exp(2j * np.pi * LYP * d[1] / PY)
    f = float(np.real(ey @ M @ ex))
    gx = float(np.real(ey @ M @ (AX * ex))); gy = float(np.real((AY * ey) @ M @ ex))
    hxx = float(np.real(ey @ M @ (AX * AX * ex))); hyy = float(np.real((AY * AY * ey) @ M @ ex))
    hxy = float(np.real((AY * ey) @ M @ (AX * ex)))
    return f, np.array([gx, gy]), np.array([[hxx, hxy], [hxy, hyy]])


def cont_max(S, start):
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
    return dict(xy=d.tolist(), converged=bool(converged), iterations=its)


def cont_map(S):
    M = S * MULT[None, :]
    Ey = np.exp(2j * np.pi * LYP[:, None] * np.arange(PY)[None, :] / PY)
    Ex = np.exp(2j * np.pi * KX[:, None] * np.arange(PX)[None, :] / PX)
    return np.real(Ey.T @ M @ Ex)


def soo_S(F, f):
    return (F.sum(axis=0) - F[f]) * np.conj(F[f]) * WEIGHT


def rel_ac(a, b):
    d = (a - b).copy(); d[0, 0] = 0
    r = b.copy(); r[0, 0] = 0
    return float(np.linalg.norm(d) / np.linalg.norm(r))


# ------------------------------------------------ bookkeeping shared by every objective evaluation
book = dict(cmap_rel=0.0, newton_all=True)


def same_sample(S):
    """Double map of S: grid winner, same-sample parabola, local Newton stationary point."""
    m = cmap(S)
    book['cmap_rel'] = max(book['cmap_rel'], float(np.abs(cont_map(S) - m).max() / np.abs(m).max()))
    pos, mx = cpu_winner(m)
    c = cont_max(S, pos)
    book['newton_all'] = book['newton_all'] and c['converged']
    return pos, parabola(m, pos, mx), np.array(c['xy'])


def loo(F, max_iter, tol, peak):
    """alignPatch iteration in double from stored iteration-1 frames; peak = 'parabola' (native rule on
    the double map) or 'continuous' (local Newton stationary point)."""
    s = np.zeros((NF, 2)); rmsd = []
    for _ in range(max_iter):
        Fs = np.stack([native_shift(F[j], s[j], PX, PY) for j in range(NF)])
        est = [same_sample(soo_S(Fs, f)) for f in range(NF)]
        c = np.array([e[1] if peak == 'parabola' else e[2] for e in est])
        c = c - c[0]
        s = s + c
        rmsd.append(float(np.sqrt((c * c).sum() / NF)))
        if rmsd[-1] < tol:
            return dict(state=s, rmsd=rmsd, converged=True)
    return dict(state=s, rmsd=rmsd, converged=False)


def rms(v): return float(np.sqrt(np.mean(np.sum(np.square(v), axis=-1))))


# ------------------------------------------------ fixed inputs: global state, pipeline windows, Phase D refs
g = np.array([[float(t) for t in l.split()[1:]] for l in (IN / 'state/global.txt').read_text().splitlines()])
assert g.shape == (NF, 2) and not g[0].any()
raw = (IN / 'fixtures/affine.mrcs').read_bytes()
nx_, ny_, nz_, mode = np.frombuffer(raw, '<i4', 4)
nsym = int(np.frombuffer(raw, '<i4', 1, 92)[0])
assert (nx_, ny_, nz_, mode) == (NX, NY, NF, 2)
movie = np.frombuffer(raw, '<f4', NX * NY * NF, 1024 + nsym).reshape(NF, NY, NX)
stored_Fg = np.stack([np.fft.rfft2(movie[f].astype(np.float64)) / (NX * NY) for f in range(NF)])
pipe = [np.fft.irfft2(native_shift(stored_Fg[f], g[f], NX, NY), s=(NY, NX)) * (NX * NY) for f in range(NF)]
ref02 = json.loads((IN / 'ref/attempt02.json').read_bytes())
phd = json.loads((IN / 'ref/w4_objective_oracle.json').read_bytes())
assert phd['state'] == 'COMPLETE_CONTROLS_PASS'
phd_cpu = phd['backends']['cpu']['patches']

# ------------------------------------------------ per patch
patches, ctl = {}, dict(gw=0.0, gn=0.0, ref=0.0, spec=0.0, chain=0.0, state=0.0, stop_ok=True)
neg = dict(gn_axes_swapped={}, chain_sign_flipped={})
chain_terms = {k: [] for k in ('float32_ties', 'integer_parabola', 'stopping', 'input_window')}
same_terms = dict(native_minus_b=[], b_minus_c=[])
for iy in range(1, 4):
    for ix in range(1, 4):
        lab = f'({iy},{ix})'; base = f'captures/patch-{iy}-{ix}/'
        meta = json.loads((IN / (base + 'c2.json')).read_bytes())
        assert meta['tag'] == 'cpu' and meta['patch_yx'] == [iy, ix] and meta['patch_nxy'] == [PX, PY] \
            and meta['ccf_nxy'] == [PX, PY] and meta['search'] == SEARCH and meta['B'] == B and meta['frames'] == NF
        K = 0
        while f'{base}c2-i{K + 1}-candidate.bin' in MAN: K += 1
        x0, y0 = (ix - 1) * PX, (iy - 1) * PY
        w = load(base + 'c2-i0-weight.bin', '<f4', (PY, NFXP))
        ctl['gw'] = max(ctl['gw'], float(np.abs(WEIGHT.astype(np.float32).astype(np.float64) - w).max()))
        it = {}
        for k in range(1, K + 1):
            p = f'{base}c2-i{k}-'
            it[k] = dict(input=load(p + 'input.bin', '<c8', (NF, PY, NFXP)).astype(np.complex128),
                         ref=load(p + 'reference.bin', '<c8', (PY, NFXP)).astype(np.complex128),
                         spec=np.stack([load(p + f'spectrum-f{f}.bin', '<c8', (PY, NFXP)) for f in range(NF)]).astype(np.complex128),
                         maps=np.stack([load(p + f'map-f{f}.bin', '<f4', (PY, PX)) for f in range(NF)]),
                         cand=load(p + 'candidate.bin', '<f8', (NF, 2)), before=load(p + 'before.bin', '<f8', (NF, 2)),
                         after=load(p + 'after.bin', '<f8', (NF, 2)))
        rows, rmsds, gn_swap = [], [], 0.0
        for k in range(1, K + 1):
            d = it[k]
            # stored-array consistency (structural; G-E rel_ac bound reused)
            ctl['ref'] = max(ctl['ref'], rel_ac(d['ref'], d['input'].sum(axis=0)))
            for f in range(NF):
                ctl['spec'] = max(ctl['spec'], rel_ac(d['spec'][f], (d['ref'] - d['input'][f]) * np.conj(d['input'][f]) * w))
            cur = d['cand'] - d['cand'][0]
            ctl['state'] = max(ctl['state'], float(np.abs(d['after'] - (d['before'] + cur)).max()),
                               float(np.abs(d['before'] - (it[k - 1]['after'] if k > 1 else 0.0)).max()))
            rmsds.append(float(np.sqrt((cur * cur).sum() / NF)))
            if k > 1:
                prev = it[k - 1]; pc = prev['cand'] - prev['cand'][0]
                ctl['chain'] = max(ctl['chain'], float(np.abs(d['input'][0] - prev['input'][0]).max()),
                                   *[rel_ac(d['input'][f], native_shift(prev['input'][f], pc[f], PX, PY)) for f in range(1, NF)])
                neg['chain_sign_flipped'].setdefault(lab, 0.0)
                neg['chain_sign_flipped'][lab] = max(neg['chain_sign_flipped'][lab], *[
                    rel_ac(d['input'][f], native_shift(prev['input'][f], -pc[f], PX, PY)) for f in range(1, NF)])
            nat, bb, cc = [], [], []
            for f in range(NF):
                m = d['maps'][f]
                pos_n, mx_n = cpu_winner(m)
                rep = parabola(m, pos_n, mx_n)
                ctl['gn'] = max(ctl['gn'], float(np.abs(rep - d['cand'][f]).max()))
                gn_swap = max(gn_swap, float(np.abs(rep[::-1] - d['cand'][f]).max()))
                pos_d, b, c = same_sample(soo_S(d['input'], f))
                md = cmap(soo_S(d['input'], f)); ulp = float(np.spacing(np.float32(md[pos_d[1] % PY, pos_d[0] % PX])))
                blk = m[np.ix_(np.arange(-SEARCH, SEARCH + 1) % PY, np.arange(-SEARCH, SEARCH + 1) % PX)]
                rows.append(dict(iteration=k, frame=f, native_candidate=d['cand'][f].tolist(), native_winner=list(pos_n),
                                 double_winner=list(pos_d), winner_equal=bool(pos_n == pos_d), float_map_exact_ties=int((blk == np.float32(mx_n)).sum()),
                                 double_parabola=b.tolist(), double_stationary=c.tolist(),
                                 stored_vs_double_map_max_ulps=float(np.abs(m.astype(np.float64) - md).max() / ulp)))
                nat.append(d['cand'][f]); bb.append(b); cc.append(c)
            nat, bb, cc = np.array(nat), np.array(bb), np.array(cc)
            q = (nat - nat[0]) - (bb - bb[0]); pr = (bb - bb[0]) - (cc - cc[0])
            same_terms['native_minus_b'].append(q[1:]); same_terms['b_minus_c'].append(pr[1:])
            rows.append(dict(iteration=k, anchored_native_minus_b=q.tolist(), anchored_b_minus_c=pr.tolist()))
        neg['gn_axes_swapped'][lab] = gn_swap
        ctl['stop_ok'] = ctl['stop_ok'] and K <= 5 and rmsds[-1] < TOL and all(r >= TOL for r in rmsds[:-1])
        # end-to-end chain from stored iteration-1 frames
        F1 = it[1]['input']
        R_par = loo(F1, 5, TOL, 'parabola'); R_con = loo(F1, 5, TOL, 'continuous'); R_inf = loo(F1, LOO_MAX, LOO_TOL, 'continuous')
        nat_final = it[K]['after']
        Rp = np.array(phd_cpu[lab]['R_pipe_loo']); known = np.array(phd_cpu[lab]['known'])
        terms = dict(float32_ties=nat_final[1:] - R_par['state'][1:], integer_parabola=R_par['state'][1:] - R_con['state'][1:],
                     stopping=R_con['state'][1:] - R_inf['state'][1:], input_window=R_inf['state'][1:] - Rp)
        ident = float(np.abs(sum(terms.values()) - (nat_final[1:] - Rp)).max())
        for kk in chain_terms: chain_terms[kk].append(terms[kk])
        pw = [wspec(pipe[f][y0:y0 + PY, x0:x0 + PX]) for f in range(NF)]
        patches[lab] = dict(
            iterations=K, native_rmsd=rmsds, rows=rows, native_final=nat_final[1:].tolist(),
            R_stop_parabola=dict(state=R_par['state'][1:].tolist(), rmsd=R_par['rmsd'], converged=R_par['converged']),
            R_stop_continuous=dict(state=R_con['state'][1:].tolist(), rmsd=R_con['rmsd'], converged=R_con['converged']),
            R_fixed_point_stored=dict(state=R_inf['state'][1:].tolist(), iterations=len(R_inf['rmsd']), converged=R_inf['converged']),
            R_pipe_loo_phaseD=Rp.tolist(), known_phaseD=known.tolist(), chain_terms={k: v.tolist() for k, v in terms.items()},
            chain_identity_max_abs=ident, R_fixed_point_stored_minus_known=(R_inf['state'][1:] - known).tolist(),
            # argument order as the reviewed oracle's stage E: rel_ac(pipeline, captured)
            input_window_witness=dict(rel_ac_stored_vs_pipeline=[rel_ac(pw[f], it[1]['input'][f]) for f in range(NF)],
                                      dc_stored=[float(it[1]['input'][f][0, 0].real) for f in range(NF)],
                                      dc_pipeline=[float(pw[f][0, 0].real) for f in range(NF)]))

# ------------------------------------------------ controls
r21 = ref02['decomposition']['cpu']['terms']
q21 = next(r['anchored_native_minus_b'] for r in patches['(2,1)']['rows'] if r.get('iteration') == 1 and 'anchored_native_minus_b' in r)
p21 = next(r['anchored_b_minus_c'] for r in patches['(2,1)']['rows'] if r.get('iteration') == 1 and 'anchored_b_minus_c' in r)
reg = dict(native_minus_b=float(np.abs(np.array(q21) - np.array(r21['quantization_native_minus_b'])).max()),
           b_minus_c=float(np.abs(np.array(p21) - np.array(r21['parabola_b_minus_c'])).max()),
           pipeline_rel_ac=float(np.abs(np.array(patches['(2,1)']['input_window_witness']['rel_ac_stored_vs_pipeline'])
                                        - np.array(ref02['stage_e']['cpu']['pipeline_from_stored_mrcs'])).max()))
controls = {
    'C-PIN': 'PASS',  # reached only if every manifest entry matched
    'G-W': 'PASS' if ctl['gw'] <= LIM['weight'] else 'FAIL',
    'G-N': 'PASS' if ctl['gn'] <= LIM['replay'] else 'FAIL',
    'N-N': 'PASS' if all(v > LIM['replay'] for v in neg['gn_axes_swapped'].values()) else 'FAIL',
    'G-M': 'PASS' if book['cmap_rel'] <= LIM['cmap'] else 'FAIL',
    'C-NEWTON': 'PASS' if book['newton_all'] else 'FAIL',
    'C-REF': 'PASS' if ctl['ref'] <= LIM['rel_ac'] else 'FAIL',
    'C-SPEC': 'PASS' if ctl['spec'] <= LIM['rel_ac'] else 'FAIL',
    'C-CHAIN': 'PASS' if ctl['chain'] <= LIM['rel_ac'] else 'FAIL',
    'N-CHAIN': 'PASS' if neg['chain_sign_flipped'] and all(v > LIM['rel_ac'] for v in neg['chain_sign_flipped'].values()) else 'FAIL',
    'C-STATE': 'PASS' if ctl['state'] == 0.0 else 'FAIL',
    'C-STOP': 'PASS' if ctl['stop_ok'] else 'FAIL',
    'C-IDENT': 'PASS' if max(p['chain_identity_max_abs'] for p in patches.values()) <= LIM['reg21'] else 'FAIL',
    'C-REG21': 'PASS' if max(reg.values()) <= LIM['reg21'] else 'FAIL',
}
ok = all(v == 'PASS' for v in controls.values())

# ------------------------------------------------ frozen routing (diagnostic labels, not gates)
chain_rms = {k: rms(np.concatenate(v)) for k, v in chain_terms.items()}
material = [k for k, v in chain_rms.items() if v >= MATERIAL_PX]
route = 'DISTRIBUTED_BELOW_0.15' if not material else (material[0] if len(material) == 1 else 'MIXED:' + '+'.join(material))
fp_all = all(p['R_fixed_point_stored']['converged'] for p in patches.values())
res = dict(protocol='w4-matched-native/v1', kind='offline same-sample/matched-input diagnostic; labels not gates; no MotionCorr execution',
           state='COMPLETE_CONTROLS_PASS' if ok else 'COMPLETE_CONTROLS_FAIL_NOT_CREDITED',
           numpy=np.__version__, python=sys.version.split()[0], limits=LIM, material_px=MATERIAL_PX, manifest_sha256=MANIFEST_SHA,
           controls=controls, control_values=dict(ctl, cmap_rel=book['cmap_rel']), negative_controls=neg, regression_21=reg,
           same_sample_rms_px={k: rms(np.concatenate(v)) for k, v in same_terms.items()},
           chain_rms_px=chain_rms, native_final_minus_R_pipe_loo_rms_px=rms(np.concatenate([np.array(p['native_final']) - np.array(p['R_pipe_loo_phaseD']) for p in patches.values()])),
           R_fixed_point_stored_minus_known_rms_px=rms(np.concatenate([np.array(p['R_fixed_point_stored_minus_known']) for p in patches.values()])),
           fixed_points_all_converged=fp_all, route=route if fp_all else 'UNDETERMINED_NO_FIXED_POINT',
           patches=patches, seconds=time.time() - t0, script_sha256=sha(Path(__file__).read_bytes()))
OUT.write_text(json.dumps(res, indent=1, allow_nan=False) + '\n')
print(json.dumps({k: res[k] for k in ('state', 'controls', 'regression_21', 'same_sample_rms_px', 'chain_rms_px', 'route',
                                     'native_final_minus_R_pipe_loo_rms_px', 'R_fixed_point_stored_minus_known_rms_px')}, indent=1))
raise SystemExit(0 if ok else 1)
