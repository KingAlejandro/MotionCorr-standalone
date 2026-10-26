#!/usr/bin/env python3
"""Stage 1 (truth inaccessible): per-frame common-mean correction d[f] for the retained W8 B2 fits.

Usage: s1_common_mean.py W8_SCRIPTS RUNS REFIT_JSON OUT.json
Reads only movie.star observations (reviewed W8 read_star), runtime.json (native G) and the stored B2
coefficients/patch centres in refit.json. B2 is not re-fitted. Imports no generator/evaluator/truth module
(asserted at exit). d[f] = mean_p obs[p,f] - mean_p obs[p,0] - mean_p local_B2(p,f), per axis, in px.
"""
import json
import sys
from pathlib import Path
import numpy as np

W8, RUNS, REFIT, OUT = map(Path, sys.argv[1:5])
sys.path.insert(0, str(W8))
import w8_fit as W            # noqa: E402  (NumPy only)
from w8_refit import read_star  # noqa: E402  (reviewed parser; imports only NumPy + w8_fit/w8_gate)

NF = 40


def movie(name, rf):
    d = RUNS/name/'F'
    rt = json.loads((d/'runtime.json').read_text())
    if rf['status'] != 'REFIT_B2':
        assert rf['status'] == 'NO_LOCAL_RETAINED'
        return dict(status=rf['status'])        # unchanged: no observations, no d
    nx, ny, g_star, keys, obs = read_star(d/'output/movie.star')
    assert obs.shape == (25, NF, 2) and not np.isnan(obs).any()
    assert nx == rf['nx'] and ny == rf['ny']
    assert np.array_equal(keys, np.array(rf['patch_centres']))
    assert np.array_equal(np.asarray(rt['global']), np.asarray(rf['global_runtime']))
    G3 = float(np.abs(obs[:, 1]-3*obs[:, 0]).max())                  # time-convention check: obs(1)=3 obs(0)
    assert G3 <= 2e-5
    u, v = keys[:, 0]/nx-.5, keys[:, 1]/ny-.5
    coeff = np.array([rf['coeff_x'], rf['coeff_y']])
    local = W.field(coeff, u, v, NF)                                 # (frame, patch, axis), z = f, same centres
    assert np.array_equal(local[0], np.zeros_like(local[0]))         # B2 local at f0 is exactly 0
    m_B2 = local.mean(1)                                             # (frame, axis)
    m_obs = obs.mean(0)                                              # (frame, axis)
    dd = m_obs - m_obs[0] - m_B2
    assert np.array_equal(dd[0], np.zeros(2)) or float(np.abs(dd[0]).max()) == 0.0
    return dict(status='REFIT_B2', G3_max_px=G3, d=dd.tolist(), m_obs=m_obs.tolist(), m_B2=m_B2.tolist(),
                global_runtime=rt['global'], d_rms_px=float(np.sqrt(np.mean(np.sum(dd**2, -1)))),
                d_max_px=float(np.abs(dd).max()))


def main():
    refit = json.loads(REFIT.read_text())
    names = sorted(refit['movies'])
    assert len(names) == 100
    res = {n: movie(n, refit['movies'][n]) for n in names}
    forbidden = [m for m in ('generate_realistic_motion', 'check_realistic_motion', 'check_motion_diagnostics',
                             'motion_field', 'generate_known_motion_fixture') if m in sys.modules]
    assert not forbidden, forbidden
    fitted = [v for v in res.values() if v['status'] == 'REFIT_B2']
    summary = dict(n=len(res), n_refit=len(fitted), n_no_local=sum(v['status'] == 'NO_LOCAL_RETAINED' for v in res.values()),
                   G3_max_px=max(v['G3_max_px'] for v in fitted), truth_modules_imported=forbidden)
    OUT.write_text(json.dumps(dict(schema='w8-common-mean-s1/1', numpy=np.__version__, summary=summary, movies=res),
                              indent=1, allow_nan=False)+'\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
