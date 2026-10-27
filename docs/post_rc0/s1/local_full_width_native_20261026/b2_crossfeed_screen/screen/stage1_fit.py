"""Stage 1b: refit from observations only. Imports NumPy and the pinned w8 modules only; a Python audit hook records every file opened. No truth, generator or evaluator."""
import hashlib, json, os, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
OPENED = []
sys.addaudithook(lambda ev, args: OPENED.append(str(args[0])) if ev == 'open' and isinstance(args[0], str) else None)
W = Path('/tmp/mc-lfw-b2-crossfeed-20261026-r1').resolve(); ROOT = W / 'stage1_root'; SRC = W / 'src_w8'  # resolved: /tmp is a symlink on this host
sys.path.insert(0, str(SRC))
import numpy as np                      # noqa: E402
import w8_fit as F                      # noqa: E402  (pinned, unchanged)
import w8_refit as R                    # noqa: E402  (pinned, unchanged; only read_star is used)
R.NF = 5
t0 = time.time()
CEIL = 0.01313142874082845; EQ = 1e-9
CASES = ['noisy', 'affine', 'pedestal', 'zero', 'integer', 'fractional', 'flat', 'repeated']
LOCAL = ['noisy', 'affine', 'pedestal']
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
nf = 5
xs, ys = np.meshgrid(np.arange(12, 116, dtype=float), np.arange(12, 84, dtype=float))   # fixed ROI grid: rows 12:84, cols 12:116
def roi_uv(nx, ny): return xs.ravel() / nx - .5, ys.ravel() / ny - .5
def load(d, c):
    rt = json.loads((d / 'runtime.json').read_text())
    nx, ny, g_star, keys, obs = R.read_star(d / f'{c}.star')
    return rt, nx, ny, g_star, keys, obs
def sv_report(u, v, arm):
    A = F.design(u, v, nf, arm)
    raw = np.linalg.svd(A, compute_uv=False); sc = np.linalg.svd(A / np.linalg.norm(A, axis=0), compute_uv=False)
    return dict(raw_singular_values=raw.tolist(), scaled_singular_values=sc.tolist())
def analyse(d, c):
    rt, nx, ny, g_star, keys, obs = load(d, c)
    out = dict(local_enabled_native=bool(rt['local_enabled']), n_patches=int(len(keys)), global_runtime=rt['global'], global_star=g_star.tolist())
    if not rt['local_enabled'] or len(keys) == 0:
        out.update(status='NO_LOCAL', coeff_zero=not (np.any(rt['coeff_x']) or np.any(rt['coeff_y'])), rows=int(len(keys)))
        return out
    pu, pv = keys[:, 0] / nx - .5, keys[:, 1] / ny - .5
    lu, lv = roi_uv(nx, ny)
    out.update(status='LOCAL', patch_centres=keys.tolist(), obs_frames_per_patch=int(obs.shape[1]), complete=bool(not np.isnan(obs).any()))
    fits, cond = {}, {}
    for arm in ('native', 'B1', 'B2', 'C'):
        f = F.fit(obs, pu, pv, arm); fits[arm] = f
        cond[arm] = F.conditioning(pu, pv, nf, arm); cond[arm].update(sv_report(pu, pv, arm), fit_rank=f['rank'], fit_n_cols=f['n_cols'],
            full_rank=bool(f['rank'] == f['n_cols']), expected_cols=18 if arm == 'native' else 18 + len(keys))
    fld = {a: F.field(fits[a]['coeff'], lu, lv, nf) for a in fits}
    rtc = np.array([rt['coeff_x'], rt['coeff_y']])
    rtf = F.field(rtc, lu, lv, nf)
    out['conditioning'] = cond
    out['equivalence_B1_vs_B2_max_px'] = float(np.abs(fld['B1'] - fld['B2']).max())
    out['equivalence_C_vs_B2_max_px'] = float(np.abs(fld['C'] - fld['B2']).max())
    out['h0_B2_exactly_zero'] = bool((fld['B2'][0] == 0.0).all()); out['h0_B1_exactly_zero'] = bool((fld['B1'][0] == 0.0).all()); out['h0_C_exactly_zero'] = bool((fld['C'][0] == 0.0).all())
    out['legacy_replay_field_max_px'] = float(np.abs(fld['native'] - rtf).max())
    out['legacy_replay_coeff_max_abs'] = float(np.abs(fits['native']['coeff'] - rtc).max())
    out['native_runtime_coeff'] = rtc.tolist()
    out['legacy_coeff'] = fits['native']['coeff'].tolist(); out['B2_coeff'] = fits['B2']['coeff'].tolist(); out['B2_intercept'] = fits['B2']['intercept'].tolist()
    return out, fits, fld, (lu, lv), nx, ny
res = {'native': {}, 'controls': {}, 'checks': {}}
fields_for_controls = {}
for c in CASES:
    for a in ('OFF', 'ON'):
        r = analyse(ROOT / 'native' / c / a, c)
        if isinstance(r, tuple):
            r = r[0]
        res['native'][f'{c}/{a}'] = r
ctl = {}
for c in ('noisy', 'affine'):
    for a in ('UP_only', 'UP_B2'):
        ctl[f'{c}/{a}'] = analyse(ROOT / 'controls' / c / a, c)
for c in ('noisy', 'affine'):
    o = ctl[f'{c}/UP_only']; b = ctl[f'{c}/UP_B2']
    o_tuple, fits, fld, (lu, lv), nx, ny = o if isinstance(o, tuple) else (o, None, None, None, None, None)
    rt_b2 = np.array(json.loads((ROOT / 'controls' / c / 'UP_B2' / 'runtime.json').read_text())['coeff_x'] + json.loads((ROOT / 'controls' / c / 'UP_B2' / 'runtime.json').read_text())['coeff_y']).reshape(2, 18)
    d = float(np.abs(F.field(fits['B2']['coeff'], lu, lv, nf) - F.field(rt_b2, lu, lv, nf)).max())
    res['controls'][c] = dict(B2_projection_of_UP_only_obs_vs_native_UP_B2_field_max_px=d, UP_B2_coeff_max_abs_diff=float(np.abs(fits['B2']['coeff'] - rt_b2).max()), UP_B2_runtime_coeff=rt_b2.tolist(),
                               UP_only_obs_blocks_equal_UP_B2=bool(open(ROOT / 'controls' / c / 'UP_only' / f'{c}.star').read().split('data_local_shift')[1] == open(ROOT / 'controls' / c / 'UP_B2' / f'{c}.star').read().split('data_local_shift')[1]),
                               legacy_replay_field_max_px_on_UP_only=o_tuple['legacy_replay_field_max_px'], UP_only_B2_coeff=fits['B2']['coeff'].tolist())
# C1: bundle OFF == retained UP_only bytes
c1 = {}
for c in ('noisy', 'affine'):
    c1[c] = dict(star_equal=sha(ROOT / 'native' / c / 'OFF' / f'{c}.star') == sha(ROOT / 'controls' / c / 'UP_only' / f'{c}.star'), runtime_equal=sha(ROOT / 'native' / c / 'OFF' / 'runtime.json') == sha(ROOT / 'controls' / c / 'UP_only' / 'runtime.json'))
checks = {}
loc = {k: v for k, v in res['native'].items() if v['status'] == 'LOCAL'}
checks['C1_staged_only_runtime_and_star'] = sorted({p.name for p in ROOT.rglob('*') if p.is_file()}) == sorted({'runtime.json'} | {p.name for p in ROOT.rglob('*.star')})
checks['C1_OFF_equals_retained_UP_only_bytes'] = all(v['star_equal'] and v['runtime_equal'] for v in c1.values())
checks['C1_UP_only_UP_B2_observation_blocks_identical'] = all(v['UP_only_obs_blocks_equal_UP_B2'] for v in res['controls'].values())
checks['C2_local_sets_present'] = sorted(loc) == sorted(f'{c}/{a}' for c in LOCAL for a in ('OFF', 'ON'))
checks['C2_complete_patches'] = all(v['complete'] and v['obs_frames_per_patch'] == 5 for v in loc.values())
checks['C2_spatial_rank6_and_ge4_times'] = all(cd['spatial_rank'] == 6 and cd['distinct_times_per_patch'] >= 4 for v in loc.values() for cd in v['conditioning'].values())
checks['C2_full_rank_all_arms'] = all(cd['full_rank'] for v in loc.values() for cd in v['conditioning'].values())
checks['C2_equivalence_le_1e-9px'] = all(max(v['equivalence_B1_vs_B2_max_px'], v['equivalence_C_vs_B2_max_px']) <= EQ for v in loc.values())
checks['C2_h0_exactly_zero'] = all(v['h0_B2_exactly_zero'] and v['h0_B1_exactly_zero'] and v['h0_C_exactly_zero'] for v in loc.values())
checks['C3_legacy_replay_le_ceiling'] = all(v['legacy_replay_field_max_px'] <= CEIL for v in loc.values())
checks['C4_B2_vs_native_UP_B2_le_ceiling'] = all(v['B2_projection_of_UP_only_obs_vs_native_UP_B2_field_max_px'] <= CEIL for v in res['controls'].values())
dis = {k: v for k, v in res['native'].items() if v['status'] == 'NO_LOCAL'}
checks['C5_local_disabled_unchanged'] = sorted(dis) == sorted(f'{c}/{a}' for c in CASES if c not in LOCAL for a in ('OFF', 'ON')) and all(v['coeff_zero'] and v['rows'] == 0 and not v['local_enabled_native'] for v in dis.values())
mods = [m for m in ('generate_realistic_motion', 'check_realistic_motion', 'check_motion_diagnostics', 'motion_field', 'generate_known_motion_fixture', 'generate_motion_diagnostics', 'score_fields_v2', 'score_fields_v3') if m in sys.modules]
checks['isolation_no_truth_generator_evaluator_modules'] = not mods
env_roots = [str(Path(p)) for p in {sys.prefix, sys.base_prefix, sys.exec_prefix}] + [str(Path(np.__file__).parent.parent)]
cls = {'staged_root': [], 'pinned_w8_source': [], 'interpreter_numpy_tree': [], 'other': []}
for p in sorted(set(OPENED)):
    q = str(Path(p).resolve()) if os.path.exists(p) else p
    if q.startswith(str(ROOT)): cls['staged_root'].append(q)
    elif q.startswith(str(SRC)): cls['pinned_w8_source'].append(q)
    elif any(q.startswith(e) for e in env_roots): cls['interpreter_numpy_tree'].append(q)
    else: cls['other'].append(q)
forbidden_pat = ('_field.npy', 'truth', 'metrics.json', '_target.npy', 'MANIFEST', 'AUDIT-BUNDLE', 'B2-factorial-parent-audit')
cls['forbidden_pattern_hits'] = [p for p in OPENED if any(f in p for f in forbidden_pat)]
checks['isolation_audit_hook_no_forbidden_or_foreign_open'] = not cls['forbidden_pattern_hits']
res['checks'] = checks; res['c1_bytes'] = c1
res['overall_pass'] = all(checks.values())
res['isolation'] = dict(modules_found=mods, opened_counts={k: len(v) for k, v in cls.items() if isinstance(v, list)}, other_opened=cls['other'], forbidden_pattern_hits=cls['forbidden_pattern_hits'])
res['environment'] = dict(python=sys.version.split()[0], numpy=np.__version__, threads_env={k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')}, wall_s=time.time() - t0,
                          w8_fit_sha256=sha(SRC / 'w8_fit.py'), w8_refit_sha256=sha(SRC / 'w8_refit.py'), w8_gate_sha256=sha(SRC / 'w8_gate.py'), roi='rows 12:84, cols 12:116', compat_ceiling_px=CEIL, equivalence_bound_px=EQ)
(W / 'out' / 'stage1_fit.json').write_text(json.dumps(res, indent=1, allow_nan=False) + '\n')
(W / 'out' / 'stage1_audit_open_log.json').write_text(json.dumps({'classes': cls, 'all_opened': sorted(set(OPENED))}, indent=1) + '\n')
print(json.dumps({'checks': checks, 'overall_pass': res['overall_pass']}, indent=1))
print('legacy replay (px):', {k: v['legacy_replay_field_max_px'] for k, v in loc.items()})
print('control B2 vs native UP_B2 (px):', {k: v['B2_projection_of_UP_only_obs_vs_native_UP_B2_field_max_px'] for k, v in res['controls'].items()})
print('equivalence (px):', {k: max(v['equivalence_B1_vs_B2_max_px'], v['equivalence_C_vs_B2_max_px']) for k, v in loc.items()})
print('opened', res['isolation']['opened_counts'], 'other:', cls['other'][:5])
