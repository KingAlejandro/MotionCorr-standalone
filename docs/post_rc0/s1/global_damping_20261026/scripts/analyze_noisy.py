#!/usr/bin/env python3
"""Per-iteration global updates, per-frame / per-patch errors and the location of the maximum, #267 `noisy`.
usage: analyze_noisy.py V2DIR FIXTURES SRC_ROOT OUT_PREFIX
Arms (runtime field where captured, STAR otherwise): a, dcg-prod, dcgh2g-prod, h2glob-prod, dcgh2g-long, diag-dcgh2g-g5.
Truth, ROI and field arithmetic are eval_v2's. Nothing here feeds back into any estimator setting.
"""
import json, pathlib, re, sys
import numpy as np
v2, fix, src, outp = (pathlib.Path(a).resolve() for a in sys.argv[1:5])
sys.path[:0] = [str(src/'tools'), str(src/'test-data')]
import check_motion_diagnostics as chk
from motion_field import read_motion_star
case = 'noisy'
man = json.loads((fix/'MANIFEST.json').read_text())['cases'][case]; r = man['recipe']; y0, y1, x0, x1 = man['roi']
truth = np.load(fix/f'{case}_field.npy'); px = r['pixel_size']
q = chk.gen.grid(r)
ARMS = {  # name -> (rundir, runtime file or None, log dir)
    'a':            ('a-rt', True), 'dcg-prod': ('dcg-prod-rt', True), 'dcgh2g-prod': ('dcgh2g-prod-rt', True),
    'h2glob-prod':  ('h2glob-prod', False), 'dcgh2g-long': ('dcgh2g-long-rt', True), 'diag-dcgh2g-g5': ('diag-dcgh2g-g5', True)}
def load(name):
    d, rt = ARMS[name]; s = read_motion_star(v2/d/case/f'{case}.star'); source = 'STAR'
    if rt and (v2/d/f'{case}.runtime.json').exists():
        j = json.loads((v2/d/f'{case}.runtime.json').read_text()); source = 'runtime'
        s.global_shift_x = np.array([g[0] for g in j['global']]); s.global_shift_y = np.array([g[1] for g in j['global']])
        if j['local_enabled'] and s.coeff_x is not None: s.coeff_x = np.array(j['coeff_x']); s.coeff_y = np.array(j['coeff_y'])
    return s, source
def iteration_norms(name):
    d = ARMS[name][0]; log = (v2/d/case/f'{case}.log').read_text().splitlines()
    glob = []
    for ln in log:
        if ln.startswith('Patches:'): break
        m = re.match(r'\s*Iteration (\d+): RMSD = (\S+) px', ln)
        if m: glob.append(float(m.group(2)))
    pat, label = {}, None
    after = False
    for ln in log:
        if ln.startswith('Patches:'): after = True; continue
        if not after: continue
        m = re.match(r'Patch \((\d+), (\d+)\): (\d+) / \d+, X range = \[(\d+), (\d+)\), Y range = \[(\d+), (\d+)\), Center = \((\d+), (\d+)\)', ln)
        if m:   # the header is printed BEFORE that patch's iteration lines
            label = (int(m.group(1)), int(m.group(2))); pat[label] = dict(iterations=[], center=(int(m.group(8)), int(m.group(9)))); continue
        m = re.match(r'\s*Iteration (\d+): RMSD = (\S+) px', ln)
        if m and label is not None: pat[label]['iterations'].append(float(m.group(2)))
    return glob, pat
rep = {}
for name in ARMS:
    if not (v2/ARMS[name][0]/case/f'{case}.star').exists(): rep[name] = dict(status='UNRUN'); continue
    s, source = load(name)
    field = s.field(s.frames, q[..., 0].ravel(), q[..., 1].ravel()).reshape((r['frames'], r['ny'], r['nx'], 2))
    e = ((field - truth) * px)[:, y0:y1, x0:x1]           # Angstrom
    mag = np.linalg.norm(e, axis=-1)
    f, yy, xx = np.unravel_index(np.argmax(mag), mag.shape)
    gx, gy = float(s.global_shift_x[f]) * px, float(s.global_shift_y[f]) * px
    loc = s.local_field([f + 1], np.array([x0 + xx]), np.array([y0 + yy]))[0, 0] * px
    mean_err = e.mean(axis=(1, 2))                         # per-frame spatial-mean error vector (A)
    per_frame = [dict(frame=i + 1, rms=float(np.sqrt((mag[i] ** 2).mean())), max=float(mag[i].max()),
                      spatial_mean_err=float(np.linalg.norm(mean_err[i])),
                      spatial_std=float(np.sqrt(((e[i] - mean_err[i]) ** 2).sum(-1).mean()))) for i in range(e.shape[0])]
    glob, pat = iteration_norms(name)
    # accepted patch observations vs truth: obs_local - (truth(center) - est_global)
    obs = []
    for row in s.local_shifts:
        fr = int(row['rlnMicrographFrameNumber']); cx, cy = row['rlnCoordinateX'], row['rlnCoordinateY']
        t = truth[fr - 1, int(cy), int(cx)]
        want = np.array([t[0] - s.global_shift_x[fr - 1], t[1] - s.global_shift_y[fr - 1]])
        got = np.array([row['rlnMicrographShiftX'], row['rlnMicrographShiftY']])
        obs.append(dict(frame=fr, center=(cx, cy), err_A=float(np.linalg.norm(got - want) * px)))
    byp = {}
    for o in obs: byp.setdefault(tuple(o['center']), []).append(o['err_A'])
    rep[name] = dict(status='RUN', field_source=source, rms=float(np.sqrt((mag ** 2).mean())), p95=float(np.percentile(mag, 95)), max=float(mag.max()),
        max_at=dict(frame=int(f) + 1, y=int(y0 + yy), x=int(x0 + xx), roi=[int(y0), int(y1), int(x0), int(x1)]),
        at_max=dict(error_vec_A=[float(c) for c in e[f, yy, xx]], est_global_A=[gx, gy], est_local_poly_A=[float(c) for c in loc],
                    frame_spatial_mean_err_A=float(np.linalg.norm(mean_err[f]))),
        top5=[dict(frame=int(i[0]) + 1, y=int(y0 + i[1]), x=int(x0 + i[2]), err_A=float(mag[i])) for i in
              [np.unravel_index(k, mag.shape) for k in np.argsort(mag.ravel())[::-1][:5]]],
        per_frame=per_frame, global_iteration_norms_px=glob,
        accepted_patch_count=len(byp), accepted_patch_obs_err_A={f'{k[0]:g},{k[1]:g}': dict(max=max(vv), per_frame=vv) for k, vv in sorted(byp.items())},
        patches={f'{k[0]},{k[1]}': dict(center=list(vv['center']), iterations=len(vv['iterations']), last_rmsd_px=vv['iterations'][-1] if vv['iterations'] else None, converged=bool(vv['iterations'] and vv['iterations'][-1] < 0.5),
                                         accepted=tuple(vv['center']) in {tuple(map(float, c)) for c in byp}) for k, vv in pat.items()})
outp.with_suffix('.json').write_text(json.dumps(rep, indent=1, allow_nan=False) + '\n')
L = ['| Arm (field source) | RMS / p95 / max A | max at (frame, y, x) | est global A at that frame | est local-poly A at that pixel | spatial-mean err of that frame A | accepted patches (max obs err A) | global iteration norms px |', '|---|---|---|---|---|---|---|---|']
for n, d in rep.items():
    if d['status'] != 'RUN': L.append(f'| {n} | UNRUN | | | | | | |'); continue
    a = d['at_max']; ma = d['max_at']
    L.append(f"| {n} ({d['field_source']}) | {d['rms']:.3f} / {d['p95']:.3f} / {d['max']:.3f} | ({ma['frame']}, {ma['y']}, {ma['x']}) | ({a['est_global_A'][0]:.2f}, {a['est_global_A'][1]:.2f}) | ({a['est_local_poly_A'][0]:.2f}, {a['est_local_poly_A'][1]:.2f}) | {a['frame_spatial_mean_err_A']:.3f} | {d['accepted_patch_count']} ({max(v['max'] for v in d['accepted_patch_obs_err_A'].values()):.2f}) | {', '.join(f'{x:.3f}' for x in d['global_iteration_norms_px'])} |")
L += ['', 'Per-frame spatial-mean error (A) and frame RMS (A):', '', '| Arm | ' + ' | '.join(f'f{i}' for i in range(1, 6)) + ' |', '|---|' + '---|' * 5]
for n, d in rep.items():
    if d['status'] == 'RUN': L.append(f'| {n} | ' + ' | '.join(f"{p['spatial_mean_err']:.2f} (rms {p['rms']:.2f}, max {p['max']:.2f})" for p in d['per_frame']) + ' |')
outp.with_suffix('.md').write_text('\n'.join(L) + '\n'); print('\n'.join(L))
