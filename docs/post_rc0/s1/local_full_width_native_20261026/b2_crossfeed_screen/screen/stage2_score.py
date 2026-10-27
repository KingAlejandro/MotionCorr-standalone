"""Stage 2: truth enters here, after the stage-1 seal. Scores the stage-1 offline refits with the pinned field evaluator (score_fields_v3.field_metrics_bound) under the criteria frozen in PLAN.md."""
import hashlib, json, os, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
W = Path('/tmp/mc-lfw-b2-crossfeed-20261026-r1').resolve()
REPO = Path('/Users/alex.konstantinov/.t3/worktrees/MotionCorr/experiment-local-full-width-weight-20261026/docs/post_rc0/s1/local_full_width_native_20261026/pilot')
B = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Native-local-full-width-AUDIT-BUNDLE-r1')
RAW = Path('/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/B2-factorial-parent-audit-r1/raw')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
t0 = time.time()
seal = json.loads((W / 'out/stage1_seal.json').read_text())
bad = [n for n, h in {**seal['files'], **seal['staged_root_files']}.items() if sha(W / n) != h]
if bad or not seal['stage1_overall_pass']:
    sys.exit('STAGE-1 SEAL BROKEN OR NOT PASSED: %s' % bad)
pins = json.loads((W / 'PINS.json').read_text())
sys.path.insert(0, str(REPO))
import numpy as np                                  # noqa: E402
import score_fields_v3 as V3                        # noqa: E402  (pinned evaluator wrapper)
assert sha(REPO / 'score_fields_v3.py') == pins['scoring_modules']['score_fields_v3.py']
S1 = json.loads((W / 'out/stage1_fit.json').read_text())
CASES = ['noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional', 'flat', 'repeated']
IDENT = ['noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional']
LIMS = {'rms': .20, 'p95': .40, 'max': .80}
CEIL = 0.01313142874082845; MARG = CEIL * 0.885
TRUTH = B / 'truth'
(W / 'out' / 'candidates').mkdir(exist_ok=True)
def gate(a): return 'PASS' if all(a[k] <= LIMS[k] for k in LIMS) else 'FAIL'
def margin(a): return [k for k in LIMS if abs(a[k] - LIMS[k]) <= MARG]
def score_model(case, model, star, tag):
    p = W / 'out' / 'candidates' / f'{tag}.json'
    p.write_text(json.dumps(model, allow_nan=False))
    return V3.field_metrics_bound(case, p, star, TRUTH / f'{case}_field.npy', TRUTH)
def cand(case, arm, fitter, g_kind):
    s = S1['native'][f'{case}/{arm}']
    coeff = np.array(s['legacy_coeff' if fitter == 'legacy' else 'B2_coeff'])
    g = s['global_runtime'] if g_kind == 'rt' else s['global_star']
    return {'global': g, 'coeff_x': coeff[0].tolist(), 'coeff_y': coeff[1].tolist(), 'local_enabled': True}
out = {'schema': 'b2-crossfeed-stage2/1', 'plan_sha256': sha(W / 'PLAN.md'), 'stage1_seal_sha256': sha(W / 'out/stage1_seal.json'), 'native': {}, 'offline': {}, 'control': {}}
def star(case, arm): return B / 'runs' / case / arm / f'{case}.star'
def rtjson(case, arm): return B / 'runs' / case / arm / 'runtime.json'
# native measured baselines (actual runtime and actual STAR fields), all 8 cases, OFF and ON
for c in CASES:
    for a in ('OFF', 'ON'):
        m = V3.field_metrics_bound(c, rtjson(c, a), star(c, a), TRUTH / f'{c}_field.npy', TRUTH)
        out['native'][f'{c}/{a}'] = {'runtime': m['runtime']['angstrom'], 'STAR': m['STAR']['angstrom'], 'runtime_gate': m['runtime']['gate'], 'STAR_gate': m['STAR']['gate'], 'local_enabled': m['local_enabled']}
# (i) control first: offline B2 on the OLD-weight observations vs the retained native UP_B2 metrics
ctl = {}
for c in ('noisy', 'affine'):
    r = score_model(c, cand(c, 'OFF', 'B2', 'rt'), star(c, 'OFF'), f'control_{c}_B2_OFF_rt')['runtime']['angstrom']
    ret = json.loads((RAW / c / 'UP_B2/metrics.json').read_text())['runtime']['angstrom']
    ret_only = json.loads((RAW / c / 'UP_only/metrics.json').read_text())['runtime']['angstrom']
    d = {k: abs(r[k] - ret[k]) for k in LIMS}
    ctl[c] = {'offline_B2_old_weight_R_rt': r, 'retained_native_UP_B2': ret, 'retained_native_UP_only': ret_only, 'abs_diff_A': d, 'within_ceiling_x_0.885': all(v <= MARG for v in d.values()), 'gate_offline': gate(r), 'gate_retained_UP_B2': gate(ret)}
out['control'] = ctl
nc = ctl['noisy']
control_ok = all(v['within_ceiling_x_0.885'] for v in ctl.values()) and all(nc['offline_B2_old_weight_R_rt'][k] > LIMS[k] for k in LIMS) and nc['offline_B2_old_weight_R_rt']['rms'] > nc['retained_native_UP_only']['rms']
out['control_ok'] = control_ok
if not control_ok:
    out['status'] = 'STOPPED_AT_CONTROL'
    (W / 'out' / 'stage2_result.json').write_text(json.dumps(out, indent=1, allow_nan=False) + '\n')
    print('CONTROL FAILED; no candidate scored:', json.dumps(ctl)); sys.exit(5)
# (ii) full table
off = out['offline']
for c in CASES:
    if c in ('noisy', 'affine', 'pedestal'):
        for a in ('OFF', 'ON'):
            for fitter in ('legacy', 'B2'):
                for g in ('rt', 'hyb'):
                    m = score_model(c, cand(c, a, fitter, g if g == 'rt' else 'hyb'), star(c, a), f'{c}_{a}_{fitter}_{g}')['runtime']['angstrom']
                    off[f'{c}/{a}/{fitter}/R_{g}'] = {'angstrom': m, 'gate': gate(m), 'margin_sensitive_metrics': margin(m)}
    else:
        for a in ('OFF', 'ON'):
            n = out['native'][f'{c}/{a}']
            for fitter in ('legacy', 'B2'):
                off[f'{c}/{a}/{fitter}/R_rt'] = {'angstrom': n['runtime'], 'gate': n['runtime_gate'], 'note': 'local disabled: unchanged native field', 'margin_sensitive_metrics': margin(n['runtime'])}
                off[f'{c}/{a}/{fitter}/R_hyb'] = {'angstrom': n['STAR'], 'gate': n['STAR_gate'], 'note': 'local disabled: unchanged native STAR field', 'margin_sensitive_metrics': margin(n['STAR'])}
# criteria
prim = {}
for c in IDENT:
    for g in ('rt', 'hyb'):
        e = off[f'{c}/ON/B2/R_{g}']; prim[f'{c}/R_{g}'] = e['gate']
out['primary'] = {'per_case_field_gate_B2_fullwidth': prim, 'all_six_identifiable_pass_both_fields': all(v == 'PASS' for v in prim.values()),
                  'five_original_passes_retained': all(prim[f'{c}/R_{g}'] == 'PASS' for c in ('affine', 'pedestal', 'zero', 'integer', 'fractional') for g in ('rt', 'hyb'))}
out['status'] = 'CANDIDATE_SUGGESTED_NOT_ACCEPTANCE' if out['primary']['all_six_identifiable_pass_both_fields'] else 'NOT_A_CANDIDATE'
dd = {}
for g, nat in (('rt', 'runtime'), ('hyb', 'STAR')):
    b2 = off[f'noisy/ON/B2/R_{g}']['angstrom']; nv = out['native']['noisy/ON'][nat]
    dd[f'R_{g}_vs_native_{nat}_ON'] = {k: {'native_legacy_fullwidth': nv[k], 'B2_fullwidth': b2[k], 'improves': b2[k] < nv[k], 'tie': b2[k] == nv[k], 'regresses': b2[k] > nv[k]} for k in LIMS}
out['directional_noisy'] = dd
inc = []
for c in CASES:
    for g, nat in (('rt', 'runtime'), ('hyb', 'STAR')):
        b2 = off[f'{c}/ON/B2/R_{g}']['angstrom']
        for ref in ('ON', 'OFF'):
            nv = out['native'][f'{c}/{ref}'][nat]
            for k in LIMS:
                if b2[k] > nv[k]:
                    inc.append({'case': c, 'field': f'R_{g}', 'metric': k, 'versus': f'native {nat} {ref}', 'native': nv[k], 'B2_fullwidth': b2[k], 'gate_transition': '%s->%s' % (gate(nv), gate(b2))})
out['increases_B2_fullwidth'] = inc
out['environment'] = {'python': sys.version.split()[0], 'numpy': np.__version__, 'threads_env': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')}, 'wall_s': time.time() - t0, 'score_fields_v3_sha256': sha(REPO / 'score_fields_v3.py'), 'margin_A': MARG}
(W / 'out' / 'stage2_result.json').write_text(json.dumps(out, indent=1, allow_nan=False) + '\n')
print('status', out['status'], '| control_ok', control_ok)
