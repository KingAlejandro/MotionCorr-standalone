#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Assemble the 16-arm W4 attribution ledger from the retained evidence files.

usage: final_ledger.py OUT.json
Historical #273 statuses are copied unchanged. Attribution text is a diagnosis
with stated uncertainty, never an accuracy outcome.
"""
import hashlib, json, pathlib, sys

here = pathlib.Path(__file__).resolve().parent
def load(rel): return json.loads((here/rel).read_text())
def sha(rel): return hashlib.sha256((here/rel).read_bytes()).hexdigest()
L = load('ledger/attempt01.json'); O = load('offline/attempt03.json')
E = load('estimator/attempt02.json'); N = load('native/evaluation-attempt01.json')
R = load('review/round1/indep.json')  # independent reviewer outputs, preserved as received

def simple(case, be):
    b = O['cases'][case]['backends'][be]; r = b['S3_offline_replays']
    n = N['summary']
    return dict(native_retained_rms_px=b['native_final']['rms_px'],
                offline_specified_double_rms_px=r['sum_of_others_double']['rms_px'],
                offline_exact_maximum_rms_px=r['sum_of_others_double_continuous']['rms_px'],
                offline_parabola_tol1e9_50_rms_px=r['sum_of_others_double_tol1e-9_max_iter50']['rms_px'],
                offline_fixed_frame0_double_rms_px=r['fixed_frame0_double']['rms_px'],
                iteration1_native_vs_exact_max_px=max(x['native_minus_exact_parabola_px'] for x in b['S2_iteration1_same_state']),
                native_truth_injection=n[f'truth-{be}-{case}'], native_fixed_frame0=n[f'fixedref-{be}-{case}'],
                native_neutral=n.get(f'neutral-{be}-{case}'))

TEXT = {
 'zero': dict(category='control; no divergence',
   first_divergence='none: identical frames give symmetric CCFs and exact zero candidates',
   uncertainty='does not exercise sub-pixel estimation', next='none'),
 'integer': dict(category='co-causes: inherited weight shape (x normalized by nx/2+1) and separable 3-point quadratic interpolation on a correlated peak, with parabola-driven nonconvergence at N=5; float32 map quantization contributes; no single exclusive cause',
   first_divergence='relative to the inherited objective: sub-pixel peak estimate in global iteration 1 departs from the maximum of the objective it estimates (the source specifies quadratic interpolation); the sum-of-others reference makes offsets fractional and the cross term biases the slice fits; input, forward FFT and reconstruction/STAR verified; weights verified for fidelity to the inherited formula only',
   uncertainty='quantization share not separately bounded natively; native tie choices are backend-specific; nonconvergence shown for N=5 only (reviewer N=9/13/20 probes converge by 50 iterations, so stopping can be a co-cause); isotropic weight alone passes offline but fails a reviewer N=20 fractional probe',
   next='two separate cross-linked HELD/file-only questions: (1) alignment weight x-normalization, (2) peak estimate with sum-of-others gain and stopping; no fix or adoption recommended. W2 DC arms change the quantization term only'),
 'fractional': dict(category='same co-causes as integer; under the inherited weight the parabola bias persists with an ideal template',
   first_divergence='relative to the inherited objective: sub-pixel peak estimate, biased even against a single known template (offline 0.26 px double; native fixed-template CPU 0.31 px, CUDA 0.49 px); reconstruction and STAR verified natively',
   uncertainty='fixedref-cuda-fractional 0.495 px is NOT MET under both the frozen manifest band (roughly 0.26-0.34 px, daaa2217) and the evaluator band 0.2-0.45 px (analyze_native.py, 98855b28); frame 4 iteration-1 candidate differs from CPU by about one integer winner per axis, inferred near-tie flip, no map capture; N=5 bound as for integer',
   next='capture the fixed-template CUDA map for frame 4 if the tie flip matters; otherwise as integer'),
 'affine': dict(category='global stage: same estimator mechanism (descriptive); local stage unresolved',
   first_divergence='not localized: global replay against the frame-centre displacement gives specified double 0.358 px vs exact maximum 0.023 px (a global shift is not the affine field); 5/9 patches stop after one update below 0.5 px',
   uncertainty='patch CCFs measure patch-average motion; no patch-level known-template oracle yet; #276 validates the fit only with constructed observations',
   next='patch-level known-template CCF/peak oracle on the #275 (2,1) capture, then feed exact patch observations through the #276-validated fit path'),
 'pedestal': dict(category='inferred: float32 CCF map resolution under the 4096 pedestal (CCF DC, #262 domain)',
   first_divergence='inferred CCF map, global iteration 1: exact window range 0.125 vs float32 ULP 8 at the 6.7e7 DC term; offline float32 rounding gives one value over all 9025 window points, so every frame would tie; native global and all 9 patches (model 1) return zero motion with RMSD 0',
   uncertainty='offline from regenerated hash-identical fixtures plus native logs/STAR; no native map capture; patch maps not computed; ran model 1 with 9 patches, so #264/#265 are not excluded by proof (zero polynomial cannot exceed either guard domain: inference; guard decision not logged; runtime coefficients not captured)',
   next='W2 DC-conditioning arms already target this; a native global-map capture would confirm the single-value map directly'),
 'noisy': dict(category='unresolved; global estimate appears noise-limited',
   first_divergence='not localized: exact-maximum global replay does not improve against the frame-centre displacement (0.99 px vs specified double 0.84 px); local stage and OUTSIDE_FIXED_ROI sampling follow',
   uncertainty='single noise seed; centre displacement is only a descriptive reference for an affine field',
   next='#238 plan C repeated independent noise seeds with a known-template oracle, after the simple-case estimator question is dispositioned'),
 'flat': dict(category='intrinsic unidentifiability (no signal)',
   first_divergence='none in arithmetic: exact window range is 0; the zero estimate is the only information-free output; field distance equals truth magnitude',
   uncertainty='no quality state is emitted, so this is not a declared abstention (#268/M4)',
   next='quality-state policy (M4); no accuracy work'),
 'repeated': dict(category='intrinsic periodic ambiguity (x mod 16, y unidentifiable) with float32 ties; out-of-ROI sampling is a consequence',
   first_divergence='CCF maximum selection: exact window range ~0.04 (~10 ULPs), 475-1710 tied float maxima; native picks large aliases (CPU x 14.5/30/13.5/12.5), which sample outside the fixed ROI',
   uncertainty='alias choice is tie-order dependent (CPU 18.7 px vs CUDA 68.7 px RMS)',
   next='quality-state policy (M4); no accuracy work'),
}
rows = []
for r in L['ledger']:
    row = dict(backend=r['backend'], case=r['case'], historical=dict(accuracy=r['accuracy_status'], sampling=r['sampling_status'],
               identifiable=r['identifiable'], field_rms_px=r['field_px']['rms'], field_rms_angstrom=r['field_angstrom']['rms'],
               global_mean_error_rms_px=r['global_mean_error_px']['rms'], local_error_rms_px=r['local_error_px']['rms'],
               published_sum_cnrmse=(r['signal'].get('published_sum_divided_by_frames') or {}).get('contrast_normalized_rmse')),
               **TEXT[r['case']])
    if r['case'] in ('integer', 'fractional'): row['stage_evidence'] = simple(r['case'], r['backend'])
    if r['case'] in ('affine', 'noisy'): row['global_replay_descriptive'] = {k: v['vs_centre']['rms_px'] if isinstance(v, dict) and 'vs_centre' in v else None
                                          for k, v in L['affine_noisy_global'][f"{r['backend']}-{r['case']}"].items() if k != 'native_final_xy'}
    if r['case'] in ('pedestal', 'flat', 'repeated'): row['first_iteration_objective'] = L['first_iteration_global_objective'][r['case']]
    rows.append(row)
assert len(rows) == 16
totals = {}
for r in rows: totals[r['historical']['accuracy']] = totals.get(r['historical']['accuracy'], 0) + 1
assert totals == {'PASS': 2, 'FAIL': 10, 'UNIDENTIFIABLE': 4}, totals
guard_exclusion = dict(excluded_model0_1x1=['integer', 'fractional', 'flat', 'repeated'],
    pedestal='model 1, 9 patches: #264/#265 not excluded by proof; all-zero observations and coefficients make an effect unlikely (inference)',
    untested=['affine', 'noisy'])
review = dict(response='review/round1-response.md', artifacts='review/round1-artifacts.json',
    isotropic_weight_parabola_5it_rms_px={c: R[c]['sumothers_parabola_5it_isotropicW']['rms_px'] for c in ('integer', 'fractional')},
    linearized_sum_of_others_eigenvalues_N5=dict(production=R['oracle_production']['eig_sumothers_iteration'], isotropic=R['oracle_isotropic']['eig_sumothers_iteration']),
    frame_count_probe_log='review/round1/ndep.log (synthetic phase-ramp frames; N=9/13/20 reach truth by 50 iterations with the production weight; isotropic N=20 fractional 11.8 px)',
    disagreement_F7='same-state comparator is the parabola rule on the double map (1.221 px frame 1), not the continuous maximum (0.576 px)')
out = dict(kind='W4 16-arm attribution ledger; diagnosis only, historical outcomes unchanged; revised after independent review round 1 (pre-review version at 7d85898d)',
           historical_totals=totals,
           scope='earliest divergence is relative to the inherited objective including its weight; nonconvergence bounded to N=5; no single exclusive cause; no fix or adoption recommendation',
           held_questions=['alignment B-factor weight x-normalization nx/2+1 vs nx (inconsistent with dose weighting nx^2)',
                           'separable 3-point peak estimate on correlated peaks with sum-of-others gain N/(N-1) and the 5-iteration/0.5 px stop'],
           fixedref_fractional_bands=dict(frozen_manifest='roughly 0.26-0.34 px (daaa2217)', evaluator='0.2-0.45 px (analyze_native.py, 98855b28)',
                                         cpu_px=N['summary']['fixedref-cpu-fractional']['field_rms_px'], cuda_px=N['summary']['fixedref-cuda-fractional']['field_rms_px'],
                                         cuda_outcome='NOT MET under both bands'),
           guard_exclusion=guard_exclusion, review_round1=review,
           estimator_oracle=E['summary'], rows=rows,
           inputs={k: sha(k) for k in ['ledger/attempt01.json', 'offline/attempt03.json', 'estimator/attempt02.json', 'native/evaluation-attempt01.json', 'review/round1/indep.json', 'review/round1/ndep.log']},
           script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
pathlib.Path(sys.argv[1]).write_text(json.dumps(out, indent=1, allow_nan=False)+'\n')
print(totals)
