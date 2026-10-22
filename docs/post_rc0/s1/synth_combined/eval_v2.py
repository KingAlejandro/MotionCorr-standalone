#!/usr/bin/env python3
"""Evaluate one run_v2_cases.py output directory against the #267 fixtures.

usage: eval_v2.py FIXTURES RUNDIR OUT.json
The #267 checker is run per case (exit code, sampling status and message kept).
An independent field-only distance (same ROI, truth and STAR field) is retained
even when an optional summed image is invalid; no ROI or tolerance is relaxed.
"""
import json, pathlib, subprocess, sys, tempfile
import numpy as np
# Works both at the committed path and for helpers copied under the source root.
REPO = next((p for p in pathlib.Path(__file__).resolve().parents
             if (p/'tools/check_motion_diagnostics.py').is_file()
             and (p/'test-data/generate_motion_diagnostics.py').is_file()), None)
if REPO is None:
    sys.exit('cannot locate MotionCorr sources above evaluator path')
sys.path[:0] = [str(REPO/'tools'), str(REPO/'test-data')]
import check_motion_diagnostics as chk
from motion_field import read_motion_star
fix, run, out = (pathlib.Path(a).resolve() for a in sys.argv[1:4])
runs = {r['case']: r for r in json.loads((run/'runs.json').read_text())}
rows = []
for case in ['zero', 'integer', 'fractional', 'affine', 'pedestal', 'noisy', 'flat', 'repeated']:
    row = dict(case=case, native_exit=runs[case]['exit'], dc=runs[case]['dc'])
    star = run/case/f'{case}.star'; summed = run/case/f'{case}.mrc'; js = run/f'{case}.checker.json'
    # Never treat a cached report as output from this invocation. Retain it on
    # input error, but only consume a report produced at a fresh private path.
    m = None
    with tempfile.TemporaryDirectory(prefix='motioncorr-v2-') as tmp:
        fresh = pathlib.Path(tmp)/'checker.json'
        p = subprocess.run([sys.executable, str(REPO/'tools/check_motion_diagnostics.py'), '--fixtures', str(fix), '--case', case,
                            '--candidate', str(star), '--summed-image', str(summed), '--json', str(fresh)], capture_output=True, text=True)
        if p.returncode in (0, 1) and fresh.exists():
            report = fresh.read_bytes()
            m = json.loads(report)
            js.write_bytes(report)
    row['checker_exit'] = p.returncode; row['checker_message'] = (p.stdout+p.stderr).strip().splitlines()[-1] if (p.stdout+p.stderr).strip() else ''
    c = json.loads((fix/'MANIFEST.json').read_text())['cases'][case]; r = c['recipe']; y0, y1, x0, x1 = c['roi']
    s = read_motion_star(star); q = chk.gen.grid(r)
    field = s.field(s.frames, q[..., 0].ravel(), q[..., 1].ravel()).reshape((r['frames'], r['ny'], r['nx'], 2))
    truth = np.load(fix/f'{case}_field.npy')
    e = (field-truth)[:, y0:y1, x0:x1]
    row['field_px'] = chk.vector_metrics(e); row['field_angstrom'] = chk.vector_metrics(e*r['pixel_size'])
    aa = row['field_angstrom']; row['field_gate'] = 'PASS' if aa['rms'] <= .2 and aa['p95'] <= .4 and aa['max'] <= .8 else 'FAIL'
    if m is not None:
        row['checker_status'] = m['accuracy_status']
        row['sampling_status'] = m['sampling_status']
        row['image'] = {k: v for k, v in m['signal'].items()}
    else: row['checker_status'] = 'ABORT_NO_RESULT'
    rows.append(row)
out.write_text(json.dumps(rows, indent=1, allow_nan=False)+'\n')
