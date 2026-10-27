# Host-only: score the 16 retained arm-a production-stop N STAR/runtime files (ed1a0e3f) with the new
# 37e n_score + generator truth, and compare against the retained reference metrics (37e evidence json).
import json, sys
from pathlib import Path
S = Path(sys.argv[1])
src = S/'src37e'
sys.path[:0] = [str(src/'tools'), str(src/'test-data')]
import numpy as np
import ccf_dc_native_rows as rows
import generate_ccf_dc_n_controls as ngen
from motion_field import read_motion_star
ref = json.loads((src/'docs/post_rc0/ccf_dc_native_compat_20261026/evidence/retained_cpu_reference.json').read_text())['rows']
runs = S/'retained/docs/post_rc0/s1/global_damping_20261026/native_ncontrols/results/nc/runs'
worst = {}
out = []
for r in ref:
    name, wt = r['movie'], r['weight']
    v, n = name.split('_N'); vel = ngen.VELOCITY[v]; n = int(n)
    truth = ngen.truth(vel, n)
    d = runs/f'a-prod-{wt}'
    st = read_motion_star(d/name/f'{name}.star'); gS = np.stack((st.global_shift_x, st.global_shift_y), -1)
    gR = np.array(json.loads((d/f'{name}.runtime.json').read_text())['global'])
    for lab, g in (('runtime', gR), ('STAR', gS)):
        s = rows.n_score(g, truth)
        for m in ('rms', 'p95', 'max'):
            dd = abs(s[m] - r[lab][m]); worst[lab+'.'+m] = max(worst.get(lab+'.'+m, 0), dd)
        if s['verdict'] != r[lab]['verdict']: out.append(('VERDICT MISMATCH', name, wt, lab))
        tr = float(np.sqrt(np.mean((g - truth)**2)*2)); key = 'traj_rms_px_'+lab
        if key in r: worst[key] = max(worst.get(key, 0), abs(tr - r[key]))
    # negative controls: opposite truth sign and a one-frame time offset must not reproduce
    for tag, t in (('neg_sign', -truth), ('time_offset', np.vstack([truth[1:], truth[-1:] + vel]))):
        s = rows.n_score(gS, t); worst[tag+'_min_rms_diff'] = min(worst.get(tag+'_min_rms_diff', 1e9), abs(s['rms'] - r['STAR']['rms']))
    if name == 'vel1_N20' and wt == 'iso': out.append(('harmful', r['runtime'], rows.n_score(gR, truth)))
print(json.dumps(dict(n=len(ref), worst_abs_diff=worst, notes=out), indent=1, default=str))
