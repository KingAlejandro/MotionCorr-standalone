"""A4: does the frozen 0.01313 px ceiling discriminate the arms it is used to compare? Field-vector distance legacy vs B2 on the same observations (sealed stage-1 coefficients), ROI grid, 5 frames."""
import json, sys
from pathlib import Path
import numpy as np
P = Path('/tmp/mc-lfw-b2-crossfeed-20261026-r1').resolve(); s1 = json.loads((P / 'out/stage1_fit.json').read_text())
x, y = np.meshgrid(np.arange(12, 116, dtype=float), np.arange(12, 84, dtype=float)); u, v = x.ravel() / 128 - .5, y.ravel() / 96 - .5
Sp = np.stack([np.ones_like(u), u, u * u, v, v * v, u * v]); z = np.arange(5.); Z = np.stack([z, z * z, z ** 3])
f = lambda c: np.einsum('agt,tf,gp->fpa', np.asarray(c).reshape(2, 6, 3), Z, Sp)
out = {k: float(np.linalg.norm(f(r['legacy_coeff']) - f(r['B2_coeff']), axis=-1).max()) for k, r in s1['native'].items() if r['status'] == 'LOCAL'}
out = {'legacy_vs_B2_vector_max_px': out, 'ceiling_px': 0.01313142874082845}
json.dump(out, sys.stdout, indent=1); print()
