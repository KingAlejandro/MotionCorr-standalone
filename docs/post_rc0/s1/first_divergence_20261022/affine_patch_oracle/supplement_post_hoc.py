#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""POST-HOC supplement to protocol affine-patch-oracle/v1 (not frozen before results).

Written after attempt02 results were read. Reuses, verbatim and asserted, the
forward-model and spectral helper blocks of the attempt02 script and the
attempt02 output, and adds descriptive splits only. No gate, label or
acceptance criterion is created here.

  S1  frame-0 anchor split of the native-minus-double-map term
  S2  deformation versus finite-window split of (R_fm - centre truth)
  S3  same-state native-versus-double-map parabola at every captured iteration
  S4  double-precision replays of the specified algorithm from the captured
      iteration-1 input, against native states, R_fm and the truth interval
  S5  fit coverage count

usage: supplement_post_hoc.py REPO RAW FILE_INDEX ATTEMPT_SCRIPT ATTEMPT_JSON OUT.json
"""
import hashlib, json, pathlib, sys
import numpy as np

REPO, RAW, INDEX, ASCRIPT, AJSON, OUT = (pathlib.Path(a) for a in sys.argv[1:7])
def sha(b): return hashlib.sha256(b).hexdigest()

src = ASCRIPT.read_text()
def block(a, b):
    i = src.index(a); j = src.index(b, i)
    return src[i:j]

NX, NY, NF = 128, 96, 5
PX, PY, X0, Y0 = 42, 32, 0, 32
NFXG, NFXP = NX // 2 + 1, PX // 2 + 1
B, SEARCH, TOL = 150.0, 15, 0.5
ns = dict(np=np, NX=NX, NY=NY, NF=NF, PX=PX, PY=PY, X0=X0, Y0=Y0, NFXG=NFXG, NFXP=NFXP, B=B, SEARCH=SEARCH, TOL=TOL)
exec(block('# ------------------------------------------------------------------ independent forward model',
           'checks = {}'), ns)
exec(block('# ------------------------------------------------------------------ spectral helpers (native conventions)',
           '# ------------------------------------------------------------------ captured data'), ns)
sig, inv, grid = ns['sig'], ns['inv'], ns['grid']
native_shift, wspec, cmap, cont_max = ns['native_shift'], ns['wspec'], ns['cmap'], ns['cont_max']
cpu_winner, cuda_winner, parabola, WEIGHT = ns['cpu_winner'], ns['cuda_winner'], ns['parabola'], ns['WEIGHT']
fixed_est, soo_S = ns['fixed_est'], ns['soo_S']
UW = grid(PX, PY, X0, Y0)
T_spec = wspec(sig(UW))

index = json.loads(INDEX.read_bytes())['files']
bound = {}
def load(rel):
    raw = (RAW / rel).read_bytes(); assert sha(raw) == index[rel]['sha256'], rel; bound[rel] = sha(raw); return raw
def arr(rel, dt, shape): return np.frombuffer(load(rel), dt).reshape(shape)

A = json.loads(AJSON.read_text())
assert A['protocol'] == 'affine-patch-oracle/v1' and A['script_sha256'] == sha(ASCRIPT.read_bytes())

def iterations(backend):
    base = f'runs/{backend}-affine-on/capture/'
    k, out = 1, {}
    while f'{base}c2-i{k}-input.bin' in index:
        out[k] = dict(input=arr(f'{base}c2-i{k}-input.bin', '<c8', (NF, PY, NFXP)).astype(np.complex128),
                      maps=(np.stack([arr(f'{base}c2-i{k}-map-f{f}.bin', '<f4', (PY, PX)) for f in range(NF)]) if backend == 'cpu'
                            else arr(f'{base}c2-i{k}-map.bin', '<f4', (NF, PY, PX))),
                      cand=arr(f'{base}c2-i{k}-candidate.bin', '<f8', (NF, 2)), after=arr(f'{base}c2-i{k}-after.bin', '<f8', (NF, 2)))
        k += 1
    return out

res = dict(protocol='affine-patch-oracle/v1 POST-HOC supplement', post_hoc=True,
           attempt_script_sha256=sha(ASCRIPT.read_bytes()), attempt_json_sha256=sha(AJSON.read_bytes()))
for backend in ('cpu', 'cuda'):
    its = iterations(backend)
    est = A['estimates'][backend]; dec = A['decomposition'][backend]
    t_c = np.array(dec['truth_centre'])
    Rfm = np.array([e['analytic_fixed_template_continuous_Rfm'] for e in est])
    out = {}
    # S1: anchor split at iteration 1
    cand = its[1]['cand']; b = np.array([e['double_soo_parabola'] for e in est])
    out['S1_anchor_split'] = dict(
        frame_term_cand_minus_b=[(cand[f] - b[f]).tolist() for f in range(NF)],
        frame0_term_cand0_minus_b0=(cand[0] - b[0]).tolist(),
        native_minus_b_anchored=[((cand[f] - cand[0]) - (b[f] - b[0])).tolist() for f in range(NF)],
        frame0_native_winner=est[0]['native_float_map_winner'], frame0_double_winner=est[0]['double_map_winner'])
    # S2: deformation vs finite-window split of R_fm - t
    rows = []
    for f in range(1, NF):
        w = fixed_est(T_spec, wspec(sig(UW + t_c[f])))['xy']      # pure translation by the centre value
        rows.append(dict(frame=f, pure_translation_equivalent=list(w), window_only_w_minus_t=(np.array(w) - t_c[f]).tolist(),
                         deformation_only_Rfm_minus_w=(Rfm[f] - np.array(w)).tolist(),
                         total_Rfm_minus_t=(Rfm[f] - t_c[f]).tolist()))
    out['S2_deformation_vs_window'] = rows
    # S3: per-iteration same-state native vs double-map parabola
    s3 = []
    for k, it in its.items():
        F = it['input']; per = []
        for f in range(NF):
            m = cmap(soo_S(F, f)); pos, mx = cpu_winner(m); p = parabola(m, pos, mx)
            wn = cpu_winner(it['maps'][f]) if backend == 'cpu' else cuda_winner(it['maps'][f])
            per.append(dict(frame=f, native_candidate=it['cand'][f].tolist(), double_parabola=p.tolist(),
                            diff=(it['cand'][f] - p).tolist(), winner_native=list(wn[0]), winner_double=list(pos), winner_equal=bool(wn[0] == pos)))
        a = it['cand'] - it['cand'][0]; bb = np.array([x['double_parabola'] for x in per]); bb = bb - bb[0]
        s3.append(dict(iteration=k, per_frame=per, anchored_native_minus_double_norm=[float(np.linalg.norm(a[f] - bb[f])) for f in range(NF)],
                       winner_flips=int(sum(not x['winner_equal'] for x in per))))
    out['S3_same_state_per_iteration'] = s3
    # S4: double replays from the captured iteration-1 input
    F0 = its[1]['input']
    def replay(kind, max_iter, tol):
        F = F0.copy(); acc = np.zeros((NF, 2)); hist = []; conv = False
        for it_ in range(1, max_iter + 1):
            cur = np.zeros((NF, 2))
            for f in range(NF):
                if kind == 'fixed_continuous':
                    S = F[0] * np.conj(F[f]) * WEIGHT; m = cmap(S); pos, _ = cpu_winner(m); cur[f] = cont_max(S, pos)['xy']
                else:
                    S = soo_S(F, f); m = cmap(S); pos, mx = cpu_winner(m)
                    cur[f] = parabola(m, pos, mx) if kind == 'parabola' else cont_max(S, pos)['xy']
            cur -= cur[0]; acc = acc + cur
            for f in range(1, NF): F[f] = native_shift(F[f], cur[f], PX, PY)
            rmsd = float(np.sqrt((cur ** 2).sum() / NF)); hist.append(rmsd)
            if rmsd < tol: conv = True; break
        return acc, hist, conv
    arms = {}
    for name, kind, mi, tol in (('specified_double_5it_tol0.5', 'parabola', 5, TOL), ('parabola_double_50it_tol1e-9', 'parabola', 50, 1e-9),
                                ('continuous_soo_double_5it_tol0.5', 'continuous', 5, TOL), ('continuous_soo_double_50it_tol1e-9', 'continuous', 50, 1e-9),
                                ('fixed_template_continuous_double_5it_tol0.5', 'fixed_continuous', 5, TOL)):
        acc, hist, conv = replay(kind, mi, tol)
        nat = its[max(its)]['after']
        arms[name] = dict(final_state=acc.tolist(), rmsd=hist, iterations=len(hist), converged=bool(conv),
                          minus_Rfm_norm=[float(np.linalg.norm(acc[f] - Rfm[f])) for f in range(1, NF)],
                          minus_truth_centre_norm=[float(np.linalg.norm(acc[f] - t_c[f])) for f in range(1, NF)],
                          minus_native_final_norm=[float(np.linalg.norm(acc[f] - nat[f])) for f in range(1, NF)],
                          inside_truth_band=[[bool(A['truth_interval'][backend][f]['band_xy'][a][0] <= acc[f][a] <= A['truth_interval'][backend][f]['band_xy'][a][1]) for a in range(2)] for f in range(1, NF)])
    nat = its[max(its)]['after']
    arms['native_captured_final'] = dict(final_state=nat.tolist(), iterations=max(its), converged=A['acceptance'][backend]['converged'],
                                         minus_Rfm_norm=[float(np.linalg.norm(nat[f] - Rfm[f])) for f in range(1, NF)],
                                         minus_truth_centre_norm=[float(np.linalg.norm(nat[f] - t_c[f])) for f in range(1, NF)])
    # control: replay iteration 1 anchored equals the attempt02 'b' anchored
    r1 = replay('parabola', 1, 0.0)[0]
    out['S4_control_iter1_equals_attempt02_b_anchored_max_abs'] = float(np.abs(r1 - (b - b[0])).max())
    out['S4_replays'] = arms
    res[backend] = out

# S5: fit coverage
res['S5_fit_coverage'] = dict(
    rows_per_accepted_patch=NF, native_requirement='n_obs > 18 (motioncorr_runner.cpp: n_obs <= n_params -> no model)',
    patches_captured=1, patches_in_grid=9,
    cpu_patch_2_1_accepted=bool(A['acceptance']['cpu']['converged']), cuda_patch_2_1_accepted=bool(A['acceptance']['cuda']['converged']),
    max_rows_available_from_capture=dict(cpu=NF if A['acceptance']['cpu']['converged'] else 0, cuda=NF if A['acceptance']['cuda']['converged'] else 0),
    verdict='UNRUN: one patch gives at most 5 observations; at least 19 (four accepted patches) are required and only a nine-patch lattice constrains the fitted field')
res['bound_inputs'] = bound
res['script_sha256'] = sha(pathlib.Path(__file__).read_bytes())
OUT.write_text(json.dumps(res, indent=1, allow_nan=False) + '\n')
np.set_printoptions(precision=3, suppress=True, linewidth=150)
for backend in ('cpu', 'cuda'):
    o = res[backend]; print('====', backend)
    print('S1 frame0 term', np.round(o['S1_anchor_split']['frame0_term_cand0_minus_b0'], 3), 'winners native/double', o['S1_anchor_split']['frame0_native_winner'], o['S1_anchor_split']['frame0_double_winner'])
    print('S1 frame terms', np.round(o['S1_anchor_split']['frame_term_cand_minus_b'], 3).tolist())
    for r in o['S2_deformation_vs_window']:
        print('S2 f', r['frame'], 'window', np.round(r['window_only_w_minus_t'], 3), 'deform', np.round(r['deformation_only_Rfm_minus_w'], 3), 'total', np.round(r['total_Rfm_minus_t'], 3))
    for s in o['S3_same_state_per_iteration']:
        print('S3 iter', s['iteration'], 'flips', s['winner_flips'], 'anch diff norms', np.round(s['anchored_native_minus_double_norm'], 3))
    print('S4 control', o['S4_control_iter1_equals_attempt02_b_anchored_max_abs'])
    for k, v in o['S4_replays'].items():
        print('S4', f'{k:46s}', 'it', v['iterations'], 'conv', v['converged'], 'to Rfm', np.round(v['minus_Rfm_norm'], 3), 'to t', np.round(v['minus_truth_centre_norm'], 3))
print(json.dumps(res['S5_fit_coverage'], indent=1))
