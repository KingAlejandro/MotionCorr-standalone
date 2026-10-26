#!/usr/bin/env python3
"""Smoke test of stage 1 + stage 2 on two synthetic movies built from analytic truth (no census data).

Usage: test_w8_pipeline.py SRC CONTROLS_v2.json
dose1-s00: perfect inputs (global = declared drift, observations Tr[Tc - g]); R-rt must be ~0 (STAR
rounding only). pedestal32-s00: no local rows, local disabled; must come back NO_LOCAL_RETAINED.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np

SRC, CONTROLS = map(Path, sys.argv[1:3])
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path[:0] = [str(SRC/'tools'), str(SRC/'test-data')]
import w8_fit as W                                    # noqa: E402
import check_realistic_motion as ev                   # noqa: E402
import generate_realistic_motion as gen               # noqa: E402
from motion_field import read_motion_star             # noqa: E402

NF = 40
fmt = lambda v: f'{v:12.6f}'


def build(d, cond, local):
    r = gen.recipe(cond, 0); nx, ny = r['nx'], r['ny']
    t = np.arange(NF)/(NF-1)
    g = -np.stack([8*(-np.expm1(-t/.1))+4*t, -5*(-np.expm1(-t/.15))-2*t], axis=-1)
    xs = [408., 1227., 2046., 2865., 3684.]
    pc = np.array([(x, y) for y in xs for x in xs])
    lines = ['', 'data_general', '', f'_rlnImageSizeX {nx}', f'_rlnImageSizeY {ny}', f'_rlnImageSizeZ {NF}',
             '_rlnMicrographStartFrame 1', f"_rlnMicrographOriginalPixelSize {r['pixel_size']}", '_rlnMicrographBinning 1.0',
             f"_rlnMotionModelVersion {1 if local else 0}", '', 'data_global_shift', '', 'loop_',
             '_rlnMicrographFrameNumber #1', '_rlnMicrographShiftX #2', '_rlnMicrographShiftY #3']
    lines += [f'{f+1:12d} {fmt(g[f, 0])} {fmt(g[f, 1])}' for f in range(NF)]
    coeff = np.zeros((2, 18))
    if local:
        Tc = np.stack([-gen.displacement(r, f, pc[:, 0], pc[:, 1]) for f in range(NF)], 1)
        h = Tc - g[None]; obs = h - h[:, :1] + 0.5*(h[:, 1:2] - h[:, :1])
        coeff = W.fit(obs, pc[:, 0]/nx-.5, pc[:, 1]/ny-.5, 'native')['coeff']
        lines += ['', 'data_local_motion_model', '', 'loop_', '_rlnMotionModelCoeffsIdx #1', '_rlnMotionModelCoeff #2']
        lines += [f'{i:12d} {coeff.ravel()[i]:.10e}' for i in range(36)]
        lines += ['', 'data_local_shift', '', 'loop_', '_rlnMicrographFrameNumber #1', '_rlnCoordinateX #2', '_rlnCoordinateY #3',
                  '_rlnMicrographShiftX #4', '_rlnMicrographShiftY #5']
        lines += [f'{f+1:12d} {fmt(pc[p, 0])} {fmt(pc[p, 1])} {fmt(obs[p, f, 0])} {fmt(obs[p, f, 1])}' for p in range(25) for f in range(NF)]
    (d/'output').mkdir(parents=True)
    (d/'output/movie.star').write_text('\n'.join(lines)+'\n')
    rt = {'global': g.tolist(), 'coeff_x': coeff[0].tolist(), 'coeff_y': coeff[1].tolist(), 'local_enabled': local}
    (d/'runtime.json').write_text(json.dumps(rt))
    (d/'metrics.json').write_text(json.dumps(ev.evaluate(r, rt, read_motion_star(d/'output/movie.star'))))


with tempfile.TemporaryDirectory() as td:
    td = Path(td); runs = td/'runs'
    build(runs/'dose1-s00/F', 'dose1', True); build(runs/'pedestal32-s00/F', 'pedestal32', False)
    py = [sys.executable, '-I']
    r1 = subprocess.run(py + [str(HERE/'w8_refit.py'), str(CONTROLS), str(runs), str(td/'refit.json')], capture_output=True, text=True)
    r2 = subprocess.run(py + [str(HERE/'w8_score.py'), str(SRC), str(runs), str(td/'refit.json'), str(td/'score.json'), str(td/'t.md')], capture_output=True, text=True)
    sc = json.loads((td/'score.json').read_text()) if r2.returncode == 0 else None
    m = {x['movie']: x for x in sc['movies']} if sc else {}
    res = dict(stage1_exit=r1.returncode, stage2_exit=r2.returncode, stderr=(r1.stderr+r2.stderr)[-800:],
               R_rt_A=m.get('dose1-s00', {}).get('R_rt'), R_hyb_A=m.get('dose1-s00', {}).get('R_hyb'),
               native_rt_A=m.get('dose1-s00', {}).get('native_rt'), ped32_status=m.get('pedestal32-s00', {}).get('status'))
    res['pass'] = (r1.returncode == 0 and r2.returncode == 0 and res['R_rt_A']['max'] < 1e-4 and res['R_hyb_A']['max'] < 1e-4
                   and res['ped32_status'] == 'NO_LOCAL_RETAINED')
    print(json.dumps(res, indent=1))
    sys.exit(0 if res['pass'] else 1)
