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
 'integer': dict(category='estimator limit (separable parabola on an anisotropic weighted peak) with parabola-driven nonconvergence; float32 map quantization contributes',
   first_divergence='sub-pixel peak estimate in global iteration 1: the sum-of-others reference makes offsets fractional and the 3-point separable parabola is biased; upstream input, forward FFT and weights verified; downstream reconstruction and STAR verified natively by truth injection',
   uncertainty='quantization share is not separately bounded natively; exact native tie choices are backend-specific',
   next='separate held issue for the estimator/weight shape (RELION-inherited); any repair needs its own versioned gate contract and review. W2 DC arms change the quantization term only'),
 'fractional': dict(category='estimator limit (separable parabola bias) with parabola-driven nonconvergence; float32 map quantization contributes',
   first_divergence='sub-pixel peak estimate: biased even against a single known template (offline 0.26 px double; native fixed-template CPU 0.31 px, CUDA 0.49 px); reconstruction and STAR verified natively',
   uncertainty='native fixed-template CUDA magnitude (0.495 px) was outside the frozen 0.2-0.45 px band; frame 4 iteration-1 candidate differs from CPU by about one integer winner per axis, inferred near-tie flip, no map capture for that arm',
   next='capture the fixed-template CUDA map for frame 4 if the tie flip matters; otherwise as integer'),
 'affine': dict(category='global stage: same estimator mechanism (descriptive); local stage unresolved',
   first_divergence='not localized: global replay against the frame-centre displacement gives specified double 0.358 px vs exact maximum 0.023 px (a global shift is not the affine field); 5/9 patches stop after one update below 0.5 px',
   uncertainty='patch CCFs measure patch-average motion; no patch-level known-template oracle yet; #276 validates the fit only with constructed observations',
   next='patch-level known-template CCF/peak oracle on the #275 (2,1) capture, then feed exact patch observations through the #276-validated fit path'),
 'pedestal': dict(category='float32 CCF map resolution under the 4096 pedestal (CCF DC, #262 domain): no information survives',
   first_divergence='CCF map, global iteration 1: exact window range 0.125 vs float32 ULP 8 at the 6.7e7 DC term; the float map is one value over all 9025 window points, every frame ties, zero motion; all 9 patches also log RMSD 0 at iteration 1',
   uncertainty='offline from regenerated hash-identical fixtures plus native logs/STAR; no native map capture; patch maps not computed',
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
out = dict(kind='W4 16-arm attribution ledger; diagnosis only, historical outcomes unchanged', historical_totals=totals,
           estimator_oracle=E['summary'], rows=rows,
           inputs={k: sha(k) for k in ['ledger/attempt01.json', 'offline/attempt03.json', 'estimator/attempt02.json', 'native/evaluation-attempt01.json']},
           script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
pathlib.Path(sys.argv[1]).write_text(json.dumps(out, indent=1, allow_nan=False)+'\n')
print(totals)
