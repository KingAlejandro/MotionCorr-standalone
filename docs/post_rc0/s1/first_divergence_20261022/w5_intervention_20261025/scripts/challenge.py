#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Truth-aligned leave-one-out stationarity test on SAME captured native spectra."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *

verify()
h = oracle_helpers()
print('helpers loaded', sorted(k for k in h if callable(h[k])), flush=True)
g, native_coeff = state()
_, _, truth = fixture('affine')
L = captured_local()
c, fitinfo = fit(L, 'inherited')
closure = float(np.abs(field(g,c)-field(g,native_coeff)).max())
assert closure < 1e-11
old = json.loads((IN/'retained/qualification_20261025/matched-native/actual/out/w4_matched_native.json').read_text())
patches = {}
all_updates, all_oracle, all_fp, all_k = [], [], [], []
max_reg = 0.
for ip, (x,y) in enumerate(CENTRES):
    lab = f'({ip//3+1},{ip%3+1})'
    p = IN / f'matched/captures/patch-{ip//3+1}-{ip%3+1}/c2-i1-input.bin'
    F = np.frombuffer(p.read_bytes(), '<c8').reshape(5,32,22).astype(np.complex128)
    K = truth[:,y,x] - g
    Fs = np.array([h['native_shift'](F[f], K[f],42,32) for f in range(5)])
    total = Fs.sum(0)
    cand, details, direct = [], [], []
    for f in range(5):
        S = (total-Fs[f])*np.conj(Fs[f])*h['WEIGHT']
        # Derivative and gain are evaluated after removing only the constant DC
        # in double, to make this diagnostic independent of the huge DC scale.
        Sac = S.copy(); Sac[0,0] = 0
        M = Sac*h['MULT'][None,:]
        v0, grad, H = h['cont_eval'](M, np.zeros(2))
        peak = h['cont_max'](Sac, [0,0])
        v1 = h['cont_eval'](M, np.array(peak['xy']))[0]
        cand.append(peak['xy'])
        details.append(dict(gradient_at_truth=grad.tolist(), hessian_at_truth=H.tolist(),
                            local_peak_update=peak, ac_gain=v1-v0, ac_gain_fraction=(v1-v0)/abs(v0)))
        # Requested oracle-reference test: truth-aligned sum of OTHERS vs original frame.
        Sref = (total-Fs[f])*np.conj(F[f])*h['WEIGHT']
        Sref[0,0] = 0
        direct.append(h['est_S'](Sref)['xy'])
    cand = np.array(cand); update = cand-cand[0]
    direct = np.array(direct); direct -= direct[0]
    # Pure-translation control has identical content and known Fourier shifts.
    Ft = np.array([h['native_shift'](F[0], -K[f],42,32) for f in range(5)])
    Fa = np.array([h['native_shift'](Ft[f], K[f],42,32) for f in range(5)])
    tc = []
    for f in range(5):
        S = (Fa.sum(0)-Fa[f])*np.conj(Fa[f])*h['WEIGHT']; S[0,0]=0
        tc.append(h['cont_max'](S, [0,0])['xy'])
    tc = np.array(tc); tc -= tc[0]
    assert np.abs(tc).max() < 1e-8
    # Reproduce W4 continuous fixed point; then restart at truth to check basin.
    fp = h['loo'](F,60,1e-9,'continuous')
    restart = h['loo'](Fs,60,1e-9,'continuous')
    ref = np.array(old['patches'][lab]['R_fixed_point_stored']['state'])
    reg = float(np.abs(fp['state'][1:]-ref).max()); max_reg = max(max_reg,reg)
    assert fp['converged'] and restart['converged'] and reg < 1e-6
    patches[lab] = dict(known=K.tolist(), truth_stationarity_update=update.tolist(), oracle_reference_trajectory=direct.tolist(),
                       oracle_reference_error_rms_px=rms((direct-K)[1:]), truth_update_rms_px=rms(update[1:]),
                       direct_vs_shifted_equivariance_max_px=float(np.abs(direct-(K+update)).max()),
                       pure_translation_update_max_px=float(np.abs(tc).max()), details=details,
                       fixed_point=fp['state'].tolist(), fixed_point_truth_error_px=rms((fp['state']-K)[1:]),
                       truth_restart_fixedpoint_max_diff_px=float(np.abs(K+restart['state']-fp['state']).max()),
                       W4_fixedpoint_reproduction_max_px=reg)
    all_updates.append(update[1:]); all_oracle.append((direct-K)[1:]); all_fp.append((fp['state']-K)[1:]); all_k.append(K)
ideal = np.array(all_k)
ideal_results = {}
for label, gg, ll in [('actual_global',g,ideal), ('true_global',truth[:,48,64],
    np.array([truth[:,y,x]-truth[:,48,64] for x,y in CENTRES]))]:
    ideal_results[label] = {}
    for mode in ('inherited','integer'):
        cc, info = fit(ll,mode)
        ideal_results[label][mode] = dict(runtime=score(field(gg,cc),truth), fit=info)
out = dict(kind='W5 challenge, same stored CPU input; no native execution',
           inherited_fit_closure_max_px=closure, inherited_fit=fitinfo,
           W4_fixedpoint_reproduction_max_px=max_reg,
           truth_stationarity_anchored_update_rms_px=rms(np.concatenate(all_updates)),
           oracle_reference_error_rms_px=rms(np.concatenate(all_oracle)),
           continuous_fixedpoint_error_rms_px=rms(np.concatenate(all_fp)),
           max_truth_restart_fixedpoint_diff_px=max(v['truth_restart_fixedpoint_max_diff_px'] for v in patches.values()),
           ideal_observation_fit=ideal_results, patches=patches)
save('challenge.json',out)
print(json.dumps({k:v for k,v in out.items() if k not in ('patches','script_hashes')},indent=1))
