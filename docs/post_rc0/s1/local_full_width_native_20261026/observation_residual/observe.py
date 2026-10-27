"""Saved-metadata observation-residual diagnostic (formulas frozen in PLAN.md). No fitting, no CCF, no pixels, no native run.

Usage: observe.py OUTDIR      (run with OMP/OPENBLAS/MKL/VECLIB threads = 1)
"""
import hashlib, json, os, re, resource, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import resid_lib as R

t0 = time.time()
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
OUT = Path(sys.argv[1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)

# ---- frozen-state verification: scripts against FREEZE.txt, every input against PINS.json
freeze = dict(reversed(l.split('  ', 1)) for l in (HERE / 'FREEZE.txt').read_text().splitlines() if '  ' in l)
for name in ('PLAN.md', 'PINS.json', 'resid_lib.py', 'test_resid_lib.py', 'observe.py', 'make_tables.py', 'build_pins.py'):
    if freeze.get(name) != sha(HERE / name):
        sys.exit(f'FREEZE MISMATCH: {name}')
PINS = json.loads((HERE / 'PINS.json').read_text())
for label, e in PINS['inputs'].items():
    if sha(e['path']) != e['sha256']:
        sys.exit(f'INPUT PIN MISMATCH: {label}')
P = lambda label: Path(PINS['inputs'][label]['path'])
assert sys.version.split()[0] == PINS['python'] and np.__version__ == PINS['numpy']
for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    assert os.environ.get(k) == '1', f'{k} must be 1'

sys.path.insert(0, str(P('w8/w8_fit.py').parent))
import w8_fit as WF                      # noqa: E402 pinned; only field() is used
import w8_refit as WR                    # noqa: E402 pinned; only read_star() is used
WR.NF = 5
NF = 5
CASES = ('noisy', 'affine', 'pedestal')
ARMS = ('OFF', 'ON')
S1 = json.loads(P('screen_out/stage1_fit.json').read_text())['native']
STAGED = json.loads(P('screen_out/stage1_staged_manifest.json').read_text())
S2 = json.loads(P('screen_out/stage2_result.json').read_text())
FIT_SETS = ('native_runtime_coeff', 'legacy_coeff', 'B2_coeff')

# provenance: bundle files equal the files the sealed stage 1 consumed
for c in CASES:
    for a in ARMS:
        for f in ('runtime.json', f'{c}.star'):
            m = STAGED[f'native/{c}/{a}/{f}']
            assert m['sha256'] == m['staged_sha256'] == PINS['inputs'][f'run/{c}/{a}/{f}']['sha256'], (c, a, f)

def parse_log(path):
    """Per-patch iteration RMSD sequences from a MotionCorr log (iteration criterion; no truth)."""
    pats, cur = {}, None
    hdr = re.compile(r'^Patch \((\d+), (\d+)\): (\d+) / (\d+), X range = \[(\d+), (\d+)\), Y range = \[(\d+), (\d+)\), Center = \((\d+), (\d+)\)')
    it = re.compile(r'^\s*Iteration (\d+): RMSD = ([0-9.eE+-]+) px')
    for line in Path(path).read_text().splitlines():
        m = hdr.match(line)
        if m:
            cur = (int(m.group(9)), int(m.group(10))); pats[cur] = dict(row=int(m.group(1)), col=int(m.group(2)), iterations=[])
            continue
        if cur is None: continue
        if not line.strip(): cur = None; continue
        m = it.match(line)
        if m: pats[cur]['iterations'].append(float(m.group(2)))
    for v in pats.values():
        v['n_iterations'] = len(v['iterations']); v['final_rmsd_px'] = v['iterations'][-1] if v['iterations'] else None
    return pats

def rank(rows, key):
    return sorted(rows, key=lambda r: -r[key])

def frame_sets(q, frames):
    return R.summarise(q[:, list(frames), :])

def block(q, ref_frames_note):
    """per-frame, per-patch and overall summaries of a (patch, frame, 2) quantity; frames 1..4 are the non-reference frames."""
    pf = {str(g): R.summarise(q[:, g, :]) for g in range(NF)}
    pp = [dict(g1_4=R.summarise(q[p, 1:5, :]), g1_3=R.summarise(q[p, 1:4, :]), g4=R.summarise(q[p, 4:5, :]), g0_4=R.summarise(q[p, 0:5, :])) for p in range(q.shape[0])]
    ov = dict(g1_4=frame_sets(q, range(1, 5)), g1_3=frame_sets(q, range(1, 4)), g4=frame_sets(q, [4]), g0_4=frame_sets(q, range(5)))
    return dict(per_frame=pf, per_patch=pp, overall=ov, note=ref_frames_note)

def full_rows(q, patches, frames):
    n = R.norm(q)
    return [dict(patch=patches[p], g=int(g), norm=float(n[p, g]), x=float(q[p, g, 0]), y=float(q[p, g, 1])) for p in range(q.shape[0]) for g in frames]

res = {'schema': 'observation-residual/1', 'frozen': {k: freeze[k] for k in freeze}, 'cases': {}}
logs = {}
for c in CASES:
    truth = np.load(P(f'truth/{c}_field.npy'))
    if truth.shape != (NF, 96, 128, 2) or not np.isfinite(truth).all():
        raise R.StopDefinition(f'{c}: truth shape/finite {truth.shape}')
    for a in ARMS:
        key = f'{c}/{a}'
        rt = json.loads(P(f'run/{c}/{a}/runtime.json').read_text())
        nx, ny, g_star, keys, obs = WR.read_star(P(f'run/{c}/{a}/{c}.star'))
        assert (nx, ny) == (128, 96)
        G = R.check_patch_array(np.array(rt['global'], float)[None], NF, 'G')[0]          # (frame, 2)
        assert np.array_equal(G, np.array(S1[key]['global_runtime'], float))
        y = R.check_patch_array(obs, NF, 'y')                                             # all frames 1..5 present (read_star asserts no NaN)
        assert keys.shape == (y.shape[0], 2) and np.array_equal(keys, np.array(S1[key]['patch_centres'], float))
        assert np.array_equal(keys, np.round(keys)) and keys[:, 0].min() >= 0 and keys[:, 0].max() < 128 and keys[:, 1].min() >= 0 and keys[:, 1].max() < 96
        xi, yi = keys[:, 0].astype(int), keys[:, 1].astype(int)
        tp = truth[:, yi, xi, :].transpose(1, 0, 2)                                        # (patch, frame, 2), same indexing as the pinned tiny_challenge
        if np.any(G[0] != 0.0) or np.any(tp[:, 0, :] != 0.0):
            raise R.StopDefinition(f'{key}: G or truth at g=0 not exactly zero')
        H = tp - G[None, :, :]
        r = R.residuals(y, H)
        clo = R.closure(r)
        g3 = float(np.abs(y[:, 1] - 3 * y[:, 0]).max())      # existing pinned G3 relation y1 = 3*y0 (w8_refit gate bound 2e-5 px)
        patches = [[int(k[0]), int(k[1])] for k in keys]
        e = dict(patches=patches, G=G.tolist(), g0_exact_zero=True, G3_max_px=g3, closure_max_abs_px=float(np.abs(clo).max()),
                 closure_raw=clo.tolist(), n_patches=int(len(keys)))
        for name in ('y', 'H', 'TrH', 'e_tr', 's', 'eta'):
            e[name] = r[name].tolist(); e[name + '_norm'] = R.norm(r[name]).tolist()
        e['H_block'] = block(r['H'], 'H=truth(centre)-G')
        e['e_tr_block'] = block(r['e_tr'], 'g=0 entry is the observed reference offset/nuisance')
        e['eta_block'] = block(r['eta'], 'g=0 is identically zero by construction')
        e['rank_eta_g1_4'] = rank(full_rows(r['eta'], patches, range(1, 5)), 'norm')
        e['rank_e_tr_g0_4'] = rank(full_rows(r['e_tr'], patches, range(5)), 'norm')
        e['rank_patch_eta_rms'] = rank([dict(patch=patches[p], norm=e['eta_block']['per_patch'][p]['g1_4']['rms']) for p in range(len(keys))], 'norm')
        e['rank_patch_e_tr_rms'] = rank([dict(patch=patches[p], norm=e['e_tr_block']['per_patch'][p]['g1_4']['rms']) for p in range(len(keys))], 'norm')
        # fitted published field (sealed coefficients) at the same patch centres: total field - G - H = F_pub - H
        pu, pv = keys[:, 0] / nx - .5, keys[:, 1] / ny - .5
        e['fitted'] = {}
        for fs in FIT_SETS:
            coeff = np.array(S1[key][fs], float)
            assert coeff.shape == (2, 18) and np.isfinite(coeff).all()
            Fp = WF.field(coeff, pu, pv, NF).transpose(1, 0, 2)                            # (patch, frame, 2)
            assert np.all(Fp[:, 0, :] == 0.0)
            err = Fp - r['H']
            e['fitted'][fs] = dict(F_pub=Fp.tolist(), err=err.tolist(), err_norm=R.norm(err).tolist(), block=block(err, 'F_pub(centre,g) - H; g=0 is zero by construction'),
                                   rank_g1_4=rank(full_rows(err, patches, range(1, 5)), 'norm'),
                                   rank_patch_rms=rank([dict(patch=patches[p], norm=R.summarise(err[p, 1:5])['rms']) for p in range(len(keys))], 'norm'))
        logs[key] = parse_log(P(f'run/{c}/{a}/{c}.log'))
        accepted = {tuple(p) for p in patches}
        e['log_patches'] = [dict(centre=list(k), accepted_in_star=(k in accepted), **v) for k, v in sorted(logs[key].items(), key=lambda kv: (kv[1]['row'], kv[1]['col']))]
        e['excluded_no_observation'] = [list(k) for k in logs[key] if k not in accepted]
        e['sealed_roi_metrics_A_linked_not_rescored'] = dict(
            native_runtime=S2['native'][key]['runtime'], native_STAR=S2['native'][key]['STAR'],
            offline_legacy_R_rt=S2['offline'][f'{key}/legacy/R_rt']['angstrom'], offline_B2_R_rt=S2['offline'][f'{key}/B2/R_rt']['angstrom'])
        res['cases'][key] = e

# ON - OFF arm changes (patches present in both arms only; non-shared patches listed)
res['arm_changes'] = {}
for c in CASES:
    o, n = res['cases'][f'{c}/OFF'], res['cases'][f'{c}/ON']
    po = {tuple(p): i for i, p in enumerate(o['patches'])}; pn = {tuple(p): i for i, p in enumerate(n['patches'])}
    common = [p for p in po if p in pn]
    ch = dict(common_patches=[list(p) for p in common], only_OFF=[list(p) for p in po if p not in pn], only_ON=[list(p) for p in pn if p not in po], G_equal=o['G'] == n['G'])
    for q in ('e_tr', 'eta') + tuple('fit:' + s for s in FIT_SETS):
        if q.startswith('fit:'):
            a_ = np.array(o['fitted'][q[4:]]['err'])[[po[p] for p in common]]; b_ = np.array(n['fitted'][q[4:]]['err'])[[pn[p] for p in common]]
        else:
            a_ = np.array(o[q])[[po[p] for p in common]]; b_ = np.array(n[q])[[pn[p] for p in common]]
        d = b_ - a_
        frames = range(1, 5) if q != 'e_tr' else range(5)
        pl = [list(p) for p in common]
        ch[q] = dict(delta_vec=d.tolist(), delta_norm_of_norms=(R.norm(b_) - R.norm(a_)).tolist(),
                     per_frame={str(g): dict(delta=R.summarise(d[:, g, :]), rms_OFF=R.summarise(a_[:, g, :])['rms'], rms_ON=R.summarise(b_[:, g, :])['rms']) for g in range(NF)},
                     per_patch=[dict(patch=pl[i], rms_OFF_g1_4=R.summarise(a_[i, 1:5])['rms'], rms_ON_g1_4=R.summarise(b_[i, 1:5])['rms'], delta_g1_4=R.summarise(d[i, 1:5])) for i in range(len(common))],
                     overall={k: dict(rms_OFF=R.summarise(a_[:, list(fr), :])['rms'], rms_ON=R.summarise(b_[:, list(fr), :])['rms'], delta=R.summarise(d[:, list(fr), :]))
                              for k, fr in (('g1_4', range(1, 5)), ('g1_3', range(1, 4)), ('g4', [4]))},
                     rank_change_of_norm=sorted([dict(patch=pl[i], g=int(g), change=float((R.norm(b_) - R.norm(a_))[i, g]), norm_OFF=float(R.norm(a_)[i, g]), norm_ON=float(R.norm(b_)[i, g]))
                                                 for i in range(len(common)) for g in frames], key=lambda r: -abs(r['change'])))
    res['arm_changes'][c] = ch

res['sealed_status_unchanged'] = S2['status']
res['environment'] = dict(python=sys.version.split()[0], numpy=np.__version__, threads={k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')},
                          wall_s=time.time() - t0, peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, platform=sys.platform,
                          star_rounding_note='STAR observations carry 5-decimal rounding (5e-6 px/axis half-unit); s and eta differences are precision-limited accordingly; the 40-frame compatibility ceiling is not an accuracy test here.')
(OUT / 'observation_residual.json').write_text(json.dumps(res, indent=1, allow_nan=False) + '\n')
print('done', len(res['cases']), 'case/arm sets; wall %.2f s' % (time.time() - t0))
