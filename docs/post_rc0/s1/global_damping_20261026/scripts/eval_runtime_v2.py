#!/usr/bin/env python3
"""Score the full-precision RUNTIME field of #267 runs (the #269 capture, MC_DIAG_MODEL_OUT) with the same truth, ROI,
field arithmetic and limits as eval_v2.py. usage: eval_runtime_v2.py FIXTURES RUNDIR STAR_EVAL.json OUT.json [CASE ...]
The runtime model replaces only the numbers inside the STAR-parsed model: the global shifts and the 18+18 local coefficients
come from RUNDIR/CASE.runtime.json (%.17g); geometry, frame indexing and basis are the STAR's. Status for unidentifiable cases is
taken from the STAR evaluation (identifiability is a property of the data). The gate is eval_v2's field gate (rms<=.2, p95<=.4, max<=.8 A).
Also reports the max |runtime - STAR| over global shifts and coefficients (serialization rounding).
"""
import json, os, pathlib, sys
import numpy as np
REPO = pathlib.Path(os.environ['MOTIONCORR_SRC']) if os.environ.get('MOTIONCORR_SRC') else next((p for p in pathlib.Path(__file__).resolve().parents
             if (p/'tools/check_motion_diagnostics.py').is_file() and (p/'test-data/generate_motion_diagnostics.py').is_file()), None)
if REPO is None: sys.exit('cannot locate MotionCorr sources above evaluator path')
sys.path[:0] = [str(REPO/'tools'), str(REPO/'test-data')]
import check_motion_diagnostics as chk
from motion_field import read_motion_star
fix, run, star_eval, out = (pathlib.Path(a).resolve() for a in sys.argv[1:5])
only = sys.argv[5:] or ['zero','integer','fractional','affine','pedestal','noisy','flat','repeated']
star_rows = {r['case']: r for r in json.loads(star_eval.read_text())} if star_eval.exists() else {}
rows = []
for case in only:
    star = run/case/f'{case}.star'; rt = json.loads((run/f'{case}.runtime.json').read_text())
    c = json.loads((fix/'MANIFEST.json').read_text())['cases'][case]; r = c['recipe']; y0, y1, x0, x1 = c['roi']
    s = read_motion_star(star)
    s_star = s.copy()
    gx = np.array([g[0] for g in rt['global']]); gy = np.array([g[1] for g in rt['global']])
    s.global_shift_x = gx; s.global_shift_y = gy
    if rt['local_enabled'] and s.coeff_x is not None:
        s.coeff_x = np.array(rt['coeff_x']); s.coeff_y = np.array(rt['coeff_y'])
    q = chk.gen.grid(r)
    field = s.field(s.frames, q[..., 0].ravel(), q[..., 1].ravel()).reshape((r['frames'], r['ny'], r['nx'], 2))
    truth = np.load(fix/f'{case}_field.npy')
    e = (field-truth)[:, y0:y1, x0:x1]
    row = dict(case=case, field_px=chk.vector_metrics(e), field_angstrom=chk.vector_metrics(e*r['pixel_size']))
    aa = row['field_angstrom']; row['runtime_gate'] = 'PASS' if aa['rms'] <= .2 and aa['p95'] <= .4 and aa['max'] <= .8 else 'FAIL'
    row['star_checker_status'] = star_rows.get(case, {}).get('checker_status')
    dglob = max(float(np.max(np.abs(gx - s_star.global_shift_x))), float(np.max(np.abs(gy - s_star.global_shift_y))))
    dcoef = 0.0
    if rt['local_enabled'] and s_star.coeff_x is not None:
        dcoef = max(float(np.max(np.abs(np.array(rt['coeff_x']) - s_star.coeff_x))), float(np.max(np.abs(np.array(rt['coeff_y']) - s_star.coeff_y))))
    row['max_abs_runtime_minus_star'] = dict(global_px=dglob, coeff=dcoef, local_enabled=rt['local_enabled'])
    rows.append(row)
out.write_text(json.dumps(rows, indent=1, allow_nan=False)+'\n')
