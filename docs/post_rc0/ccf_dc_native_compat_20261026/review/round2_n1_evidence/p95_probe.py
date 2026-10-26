# Host-only: per-row p95 of the new n_score vs retained, and p95 recomputed over a dense ROI broadcast
# (ROI y[12:84] x[12:116] as the retained README/score_ncontrols state; W5 common.py itself is not in git).
import json, sys
from pathlib import Path
S = Path(sys.argv[1]); src = S/'src37e'
sys.path[:0] = [str(src/'tools'), str(src/'test-data')]
import numpy as np
import ccf_dc_native_rows as rows, generate_ccf_dc_n_controls as ngen
from motion_field import read_motion_star
ref = json.loads((src/'docs/post_rc0/ccf_dc_native_compat_20261026/evidence/retained_cpu_reference.json').read_text())['rows']
runs = S/'retained/docs/post_rc0/s1/global_damping_20261026/native_ncontrols/results/nc/runs'
worst_dense = 0.0; nbad = 0
for r in ref:
    name, wt = r['movie'], r['weight']; v, n = name.split('_N'); truth = ngen.truth(ngen.VELOCITY[v], int(n))
    st = read_motion_star(runs/f'a-prod-{wt}'/name/f'{name}.star'); g = np.stack((st.global_shift_x, st.global_shift_y), -1)
    e = np.linalg.norm((g - truth)*rows.PIXEL_SIZE, axis=-1)
    new = rows.n_score(g, truth)['p95']
    dense = float(np.percentile(np.repeat(e, 72*104), 95))
    d1, d2 = abs(new - r['STAR']['p95']), abs(dense - r['STAR']['p95'])
    worst_dense = max(worst_dense, d2); nbad += d1 > 1e-5
    print(f"{name:9s} {wt:4s} N={n:>2s} retained={r['STAR']['p95']:.6f} new={new:.6f} |d|={d1:.2e} dense_roi={dense:.6f} |d|={d2:.2e}")
print('rows with new-p95 |d|>1e-5:', nbad, 'of', len(ref), '; dense-ROI worst |d|:', worst_dense)
