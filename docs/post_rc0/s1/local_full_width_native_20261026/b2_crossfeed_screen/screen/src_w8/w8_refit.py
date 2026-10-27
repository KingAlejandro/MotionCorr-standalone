#!/usr/bin/env python3
"""W8 census stage 1: refit from observations only (../PLAN.md, amendment 1).

Usage: w8_refit.py CONTROLS_v2.json RUNS OUT_refit.json
Refuses (exit 4) before reading any movie unless the versioned controls allow the census
(B1, B2 and C all pass, including K8). Every census fit must be full rank. Reads, per movie, only <movie>/F/runtime.json and <movie>/F/output/movie.star. Never imports the
generator or the evaluator (asserted at exit), so truth cannot reach the fit.
"""
import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import w8_fit as W   # noqa: E402
import w8_gate      # noqa: E402

NF = 40


def read_star(path):
    """Image size, read-back global trajectory and local-shift observations from a MotionCorr movie STAR."""
    block, gen, glob, loc = None, {}, [], []
    for line in Path(path).read_text().splitlines():
        s = line.strip()
        if s.startswith('data_'): block = s; continue
        w = s.split()
        if block == 'data_general' and len(w) == 2 and w[0].startswith('_rln'): gen[w[0]] = w[1]
        elif not w or w[0].startswith('_') or w[0] in ('loop_', '#'): continue
        elif block == 'data_global_shift' and len(w) == 3: glob.append([float(a) for a in w])
        elif block == 'data_local_shift' and len(w) == 5: loc.append([float(a) for a in w])
    nx, ny = int(gen['_rlnImageSizeX']), int(gen['_rlnImageSizeY'])
    glob = np.array(glob); assert glob.shape == (NF, 3) and np.array_equal(glob[:, 0], np.arange(1, NF+1))
    loc = np.array(loc).reshape(-1, 5)
    keys = sorted({(a[1], a[2]) for a in loc}, key=lambda k: (k[1], k[0]))
    obs = np.full((len(keys), NF, 2), np.nan)
    for a in loc: obs[keys.index((a[1], a[2])), int(a[0])-1] = a[3:5]
    assert not np.isnan(obs).any()
    return nx, ny, glob[:, 1:], np.array(keys).reshape(-1, 2), obs


def lattice(nx, ny):
    x, y = np.meshgrid(np.linspace(32, nx-33, 129), np.linspace(32, ny-33, 129))
    return x.ravel()/nx-.5, y.ravel()/ny-.5


def movie(d):
    rt = json.loads((d/'runtime.json').read_text())
    nx, ny, g_star, keys, obs = read_star(d/'output/movie.star')
    out = dict(nx=nx, ny=ny, global_runtime=rt['global'], global_star=g_star.tolist(), n_patches=len(keys),
               local_enabled_native=bool(rt['local_enabled']))
    if not rt['local_enabled'] or len(keys) == 0:
        # F kept no patches (pedestal32): retain the native no-local field; never invent observations.
        assert len(keys) == 0 and not np.any(rt['coeff_x']) and not np.any(rt['coeff_y'])
        out['status'] = 'NO_LOCAL_RETAINED'
        return out
    pu, pv = keys[:, 0]/nx-.5, keys[:, 1]/ny-.5
    lu, lv = lattice(nx, ny)
    nat = w8_gate.require_full_rank(W.fit(obs, pu, pv, 'native'))
    out['G3_max_px'] = float(np.abs(obs[:, 1]-3*obs[:, 0]).max())
    out['G4_native_refit_vs_runtime_max_px'] = float(np.abs(W.field(nat['coeff'], lu, lv, NF)
                                                     - W.field(np.array([rt['coeff_x'], rt['coeff_y']]), lu, lv, NF)).max())
    b2 = w8_gate.require_full_rank(W.fit(obs, pu, pv, 'B2'))
    out.update(status='REFIT_B2', patch_centres=keys.tolist(), coeff_x=b2['coeff'][0].tolist(), coeff_y=b2['coeff'][1].tolist(),
               intercept_x=b2['intercept'][0].tolist(), intercept_y=b2['intercept'][1].tolist(), rank=b2['rank'], n_cols=b2['n_cols'],
               sv_min=float(b2['sv'].min()), sv_max=float(b2['sv'].max()))
    # Equivalence on census inputs (B1, C vs B2), as in K8.
    out['B1_C_vs_B2_max_px'] = max(float(np.abs(W.field(w8_gate.require_full_rank(W.fit(obs, pu, pv, a))['coeff'], lu, lv, NF) - W.field(b2['coeff'], lu, lv, NF)).max())
                                   for a in ('B1', 'C'))
    return out


def main():
    CONTROLS, RUNS, OUT = map(Path, sys.argv[1:4])
    if not w8_gate.census_allowed(json.loads(CONTROLS.read_text())):
        print('REFUSED: controls do not allow the census (B1/B2/C equivalence group)', file=sys.stderr)
        sys.exit(4)
    names = sorted(p.name for p in RUNS.iterdir() if (p/'F').is_dir())
    res = {n: movie(RUNS/n/'F') for n in names}
    forbidden = [m for m in ('generate_realistic_motion', 'check_realistic_motion', 'check_motion_diagnostics', 'motion_field') if m in sys.modules]
    assert not forbidden, forbidden
    fitted = [v for v in res.values() if v['status'] == 'REFIT_B2']
    gates = dict(n=len(res), n_refit=len(fitted), n_no_local=sum(v['status'] == 'NO_LOCAL_RETAINED' for v in res.values()),
                 G3_max_px=max(v['G3_max_px'] for v in fitted), G4_max_px=max(v['G4_native_refit_vs_runtime_max_px'] for v in fitted),
                 full_rank=all(v['rank'] == v['n_cols'] for v in fitted), equivalence_max_px=max(v['B1_C_vs_B2_max_px'] for v in fitted),
                 truth_modules_imported=forbidden)
    gates['pass'] = gates['G3_max_px'] <= 2e-5 and gates['G4_max_px'] <= .005 and gates['full_rank'] and gates['equivalence_max_px'] <= 1e-8
    OUT.write_text(json.dumps(dict(schema='w8-refit/1', numpy=np.__version__, gates=gates, movies=res), indent=1, allow_nan=False)+'\n')
    print(json.dumps(gates))
    sys.exit(0 if gates['pass'] else 3)


if __name__ == '__main__':
    main()
