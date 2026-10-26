#!/usr/bin/env python3
"""W7 error budget of the H7a flags-off (F) census. See ../ANALYSIS-PLAN.md.

Usage: analyze_w7.py SRC RUNS FIXTURES OUT.json CENSUS.json
  SRC       git archive of 4fa272f6 (unchanged evaluator + generator)
  RUNS      H7a results/runs (reads <movie>/F/...)
  FIXTURES  cpu64 census fixtures (reads <movie>/RECEIPT.json only)
  CENSUS    H7a results/census.json (movie sha256 per movie)
Reads no pixels and runs no MotionCorr.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
from pathlib import Path
import numpy as np

SRC, RUNS, FIX, OUT, CENSUS = map(Path, sys.argv[1:6])
MOVIE_SHA = {row['movie']: row for row in json.loads(CENSUS.read_text())['rows']}
sys.path[:0] = [str(SRC/'tools'), str(SRC/'test-data')]
import check_realistic_motion as ev            # noqa: E402  (unchanged evaluator)
import generate_realistic_motion as gen        # noqa: E402  (unchanged generator)
from check_motion_diagnostics import vector_metrics   # noqa: E402
from motion_field import read_motion_star      # noqa: E402

CONDITIONS = list(gen.CONDITIONS)
BINS = {'0': [0], '1': [1], '2-10': range(2, 11), '11-20': range(11, 21), '21-30': range(21, 31), '31-39': range(31, 40)}
REGIONS = ['interior', 'edge', 'corner']


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def close(a, b, path=''):
    """Recursive comparison at 1e-12 relative; returns list of mismatching paths."""
    if isinstance(a, dict):
        return [m for k in b for m in close(a.get(k), b[k], f'{path}/{k}')] if isinstance(b, dict) else [path]
    if isinstance(a, list):
        if not isinstance(b, list) or len(a) != len(b): return [path]
        return [m for i, (x, y) in enumerate(zip(a, b)) for m in close(x, y, f'{path}[{i}]')]
    if isinstance(a, float) or isinstance(b, float):
        return [] if abs(a-b) <= 1e-12*max(abs(a), abs(b), 1e-300) else [path]
    return [] if a == b else [path]


def lattice(r):
    # The evaluator's lattice, verbatim.
    x, y = np.meshgrid(np.linspace(32, r['nx']-33, 129), np.linspace(32, r['ny']-33, 129))
    return x.ravel(), y.ravel()


def declared_drift(r):
    # The evaluator's g, verbatim (non-control branch).
    t = np.arange(r['frames'])/(r['frames']-1)
    return -np.stack([8*(-np.expm1(-t/.1))+4*t, -5*(-np.expm1(-t/.15))-2*t], axis=-1)


def truth(r, x, y):
    return -np.stack([gen.displacement(r, f, x, y) for f in range(r['frames'])])


def design(u, v, z):
    s = np.stack([np.ones_like(u), u, u*u, v, v*v, u*v])
    t = np.stack([z, z*z, z*z*z])
    return (s[:, None, :]*t[None, :, :]).reshape(18, -1).T    # column 3*s + t, as matA


def tr(h):
    """MotionCorr's stored observation for group_frames 1: local[g]-interp(0), local pinned at frame 0."""
    return h - h[..., :1, :] + 0.5*(h[..., 1:2, :] - h[..., :1, :])


class Fitter:
    def __init__(self, r, pu, pv, x, y):
        nf = r['frames']
        self.r, self.np_ = r, len(pu)
        z = np.tile(np.arange(nf)+0.5, self.np_)
        self.A = design(np.repeat(pu, nf), np.repeat(pv, nf), z)
        self.x, self.y = x, y

    def coeff(self, obs):          # obs (patch, frame, 2)
        b = obs.reshape(-1, 2)
        c, *_ = np.linalg.lstsq(self.A, b, rcond=None)
        return c.T                 # (2, 18)

    def field(self, obs):
        if self.np_ == 0: return np.zeros((self.r['frames'], len(self.x), 2))
        c = self.coeff(obs)
        m = {'coeff_x': list(c[0]), 'coeff_y': list(c[1]), 'global': np.zeros((self.r['frames'], 2))}
        return ev.runtime_field(m, self.r, self.x, self.y)


def metrics_A(e, ps):
    return {k: v for k, v in vector_metrics(e*ps).items()}


def parse_log(path):
    text = Path(path).read_text()
    patches = []
    for m in re.finditer(r'Patch \((\d+), (\d+)\): \d+ / \d+, X range = \[(\d+), (\d+)\), Y range = \[(\d+), (\d+)\), Center = \((\d+), (\d+)\)', text):
        patches.append(dict(iy=int(m[1]), ix=int(m[2]), x0=int(m[3]), x1=int(m[4]), y0=int(m[5]), y1=int(m[6]), xc=int(m[7]), yc=int(m[8])))
    blocks = re.split(r'Patch \(\d+, \d+\):', text)[1:]
    for p, b in zip(patches, blocks):
        p['iterations'] = len(re.findall(r'Iteration \d+: RMSD', b.split('Polynomial fit')[0]))
    return patches


def star_obs(path, nf):
    rows, on = [], False
    for line in Path(path).read_text().splitlines():
        if line.startswith('data_'): on = line.strip() == 'data_local_shift'; continue
        w = line.split()
        if on and len(w) == 5 and not line.startswith('_'):
            rows.append([float(a) for a in w])
    rows = np.array(rows).reshape(-1, 5)
    keys = sorted({(a[1], a[2]) for a in rows}, key=lambda k: (k[1], k[0]))
    obs = np.zeros((len(keys), nf, 2))
    for a in rows:
        obs[keys.index((a[1], a[2])), int(a[0])-1] = a[3:5]
    return np.array(keys).reshape(-1, 2), obs


def regions(x, y, cx, cy):
    ox = (x < cx.min()) | (x > cx.max()); oy = (y < cy.min()) | (y > cy.max())
    return dict(interior=~ox & ~oy, edge=ox ^ oy, corner=ox & oy)


def rms(a, axis=None):
    return float(np.sqrt(np.mean(np.sum(a*a, axis=-1), axis=axis))) if axis is None else np.sqrt(np.mean(np.sum(a*a, axis=-1), axis=axis))


def representability_lattice(r, T, x, y):
    """Best least-squares fit on the lattice: free global[f] (global[0]=0) + 18 coefficients."""
    nf = r['frames']; u, v = x/r['nx']-.5, y/r['ny']-.5
    S = np.stack([u, u*u, v, v*v, u*v])                          # non-constant spatial terms
    Sd = S - S.mean(axis=1, keepdims=True)                       # global absorbs per-frame means
    z = np.arange(1, nf, dtype=float); Z = np.stack([z, z*z, z**3])
    A = (Sd[:, None, None, :]*Z[None, :, :, None]).reshape(15, -1).T   # rows (frame, point)
    Td = T[1:] - T[1:].mean(axis=1, keepdims=True)
    c, *_ = np.linalg.lstsq(A, Td.reshape(-1, 2), rcond=None)    # (15, 2)
    coeff = np.zeros((2, 6, 3)); coeff[:, 1:, :] = c.T.reshape(2, 5, 3)
    P = np.einsum('agt,tf,gp->fpa', coeff, np.stack([np.arange(nf), np.arange(nf)**2, np.arange(nf)**3.]),
                  np.stack([np.ones_like(u), u, u*u, v, v*v, u*v]))
    glob = (T - P).mean(axis=1); glob[0] = 0.
    return {'global': glob.tolist(), 'coeff_x': coeff[0].ravel().tolist(), 'coeff_y': coeff[1].ravel().tolist(), 'local_enabled': True}


def ms_budget(e, comps):
    tot = float(np.mean(np.sum(e*e, -1)))
    names = list(comps)
    share = {n: float(np.mean(np.sum(comps[n]**2, -1)))/tot for n in names}
    cross = {f'{a}*{b}': 2*float(np.mean(np.sum(comps[a]*comps[b], -1)))/tot
             for i, a in enumerate(names) for b in names[i+1:]}
    return dict(ms_total_px2=tot, share=share, cross=cross, sum_check=sum(share.values())+sum(cross.values()))


def movie(name):
    cond, seed = name.rsplit('-s', 1); seed = int(seed)
    d = RUNS/name/'F'
    met = json.loads((d/'metrics.json').read_text())
    rec_path = FIX/name/'RECEIPT.json'; receipt = json.loads(rec_path.read_text()); r = receipt['recipe']
    # Amended G1: H7a regenerated 82 movies, so its RECEIPT copies differ in timing fields; the
    # movie bytes are the identity (H7a census movie sha256 == this receipt's movie.mrcs hash).
    row = MOVIE_SHA[name]
    g1 = dict(movie_sha_matches=(row['movie_sha256'] == receipt['files']['movie.mrcs'] and row['movie_sha256_equals_receipt'] is True),
              recipe_matches=(r == gen.recipe(cond, seed)))
    model = json.loads((d/'runtime.json').read_text())
    ps, nf = r['pixel_size'], r['frames']
    re_eval = ev.evaluate(r, model, read_motion_star(d/'output/movie.star'))
    g2 = close(re_eval, {k: met[k] for k in re_eval})

    x, y = lattice(r); T = truth(r, x, y); g = declared_drift(r)
    glob = np.asarray(model['global'])
    # The evaluator always adds the polynomial; local_enabled=False runs must carry zero coefficients.
    if not model['local_enabled']: assert not np.any(model['coeff_x']) and not np.any(model['coeff_y'])
    field = ev.runtime_field(model, r, x, y)
    e = field - T

    patches = parse_log(d/'output/movie.log')
    keys, obs = star_obs(d/'output/movie.star', nf)
    use_local = model['local_enabled'] and len(keys) > 0
    if not use_local: keys, obs = keys[:0], obs[:0]
    pu, pv = keys[:, 0]/r['nx']-.5, keys[:, 1]/r['ny']-.5
    fit = Fitter(r, pu, pv, x, y)
    g3 = float(np.max(np.abs(obs[:, 1]-3*obs[:, 0]))) if use_local else None
    g4 = float(np.max(np.abs(fit.field(obs) - (field - glob[:, None, :])))) if use_local else 0.0

    # Patch-centre truth and the exact linear split.
    Tc = np.stack([-gen.displacement(r, f, keys[:, 0], keys[:, 1]) for f in range(nf)], 1) if use_local else np.zeros((0, nf, 2))
    eps = glob - g
    R = Tc - glob[None]; obs_star = tr(R); delta = obs - obs_star
    if use_local:
        e_repr = g[:, None, :] + fit.field(tr(Tc - g[None])) - T
    else:
        e_repr = g[:, None, :] - T
    eps_c = np.zeros_like(eps); eps_c[1:] = eps[1:].mean(0)
    def glob_part(h):
        return h[:, None, :] - fit.field(tr(np.broadcast_to(h[None], (len(keys), nf, 2))))
    e_glob_c, e_glob_r = glob_part(eps_c), glob_part(eps - eps_c)
    d_c = np.broadcast_to(delta.mean(1, keepdims=True), delta.shape)
    e_obs_c, e_obs_r = fit.field(d_c), fit.field(delta - d_c)
    comps = dict(repr=e_repr, glob_const=e_glob_c, glob_var=e_glob_r, obs_const=e_obs_c, obs_var=e_obs_r)
    g5 = float(np.max(np.abs(sum(comps.values()) - e)))

    out = dict(movie=name, condition=cond, seed=seed, nx=r['nx'], ny=r['ny'], local_enabled=bool(model['local_enabled']),
               n_patches=len(keys), gates=dict(G1=g1, G2_mismatches=g2, G3_max_px=g3, G4_max_px=g4, G5_max_px=g5))
    out['field_A'] = metrics_A(e, ps); assert abs(out['field_A']['rms'] - met['field']['angstrom']['rms']) < 1e-9
    lim = dict(rms=.20, p95=.40, max=.80)
    out['fails'] = [k for k in lim if out['field_A'][k] > lim[k]]
    out['pass'] = not out['fails']

    # T2 rigid vs local.
    ebar = np.broadcast_to(e.mean(1, keepdims=True), e.shape); et = e - ebar
    out['T2'] = dict(ms_share_rigid=float(np.mean(np.sum(ebar**2, -1))/np.mean(np.sum(e*e, -1))),
                     rigid_A=metrics_A(ebar, ps), local_A=metrics_A(et, ps))
    # T3 temporal.
    pf = lambda a: rms(a, axis=1)
    out['T3'] = dict(bins_rms_A={b: dict(e=float(np.sqrt(np.mean(pf(e)[list(f)]**2)))*ps, rigid=float(np.sqrt(np.mean(pf(ebar)[list(f)]**2)))*ps,
                                         local=float(np.sqrt(np.mean(pf(et)[list(f)]**2)))*ps,
                                         **{n: float(np.sqrt(np.mean(pf(c)[list(f)]**2)))*ps for n, c in comps.items()}) for b, f in BINS.items()},
                     per_frame_rms_A=(pf(e)*ps).tolist(), per_frame_rigid_A=(pf(ebar)*ps).tolist(),
                     max_frame=int(np.unravel_index(np.argmax(np.linalg.norm(e, axis=-1)), e.shape[:2])[0]))
    z = np.arange(nf, dtype=float); Zc = np.stack([z, z*z, z**3], 1)
    rest = eps - eps_c; cub = Zc @ np.linalg.lstsq(Zc, rest, rcond=None)[0]; jit = rest - cub
    r1 = lambda a: float(np.sqrt(np.mean(np.sum(a[1:]**2, -1))))*ps
    out['T3']['eps_g_A'] = dict(total=r1(eps), const=r1(eps_c), cubic=r1(cub), jitter=r1(jit),
                                const_vec_px=eps[1:].mean(0).tolist())
    # T4 spatial (hull of the log's patch centres, also for runs whose patches were dropped).
    cx = np.array([p['xc'] for p in patches]); cy = np.array([p['yc'] for p in patches])
    reg = regions(x, y, cx, cy); mag = np.linalg.norm(e, axis=-1); p95 = np.percentile(mag, 95)
    imax = np.unravel_index(np.argmax(mag), mag.shape)
    out['T4'] = dict(fraction={k: float(m.mean()) for k, m in reg.items()},
                     rms_A={k: dict(e=rms(e[:, m])*ps, local=rms(et[:, m])*ps, **{n: rms(c[:, m])*ps for n, c in comps.items()}) for k, m in reg.items()},
                     above_p95_share={k: float((mag[:, m] > p95).sum()/(mag > p95).sum()) for k, m in reg.items()},
                     max_region=[k for k, m in reg.items() if m[imax[1]]][0], max_frame=int(imax[0]))
    # T5 representability: never subtracted from any error.
    rl = representability_lattice(r, T, x, y)
    out['T5'] = dict(R_lat_A=ev.evaluate(r, rl)['field']['angstrom'])
    allp = [(p['xc'], p['yc']) for p in patches]
    apu = np.array([a[0] for a in allp])/r['nx']-.5; apv = np.array([a[1] for a in allp])/r['ny']-.5
    fa = Fitter(r, apu, apv, x, y)
    Tca = np.stack([-gen.displacement(r, f, np.array([a[0] for a in allp], float), np.array([a[1] for a in allp], float)) for f in range(nf)], 1)
    ca = fa.coeff(tr(Tca - g[None]))
    rp = {'global': g.tolist(), 'coeff_x': ca[0].tolist(), 'coeff_y': ca[1].tolist(), 'local_enabled': True}
    out['T5']['R_pipe_A'] = ev.evaluate(r, rp)['field']['angstrom']
    # Sensitivity: patch-area mean truth instead of the centre value (33x33 sample grid over the patch box).
    Tm = []
    for p in patches:
        gx, gy = np.meshgrid(np.linspace(p['x0'], p['x1']-1, 33), np.linspace(p['y0'], p['y1']-1, 33))
        Tm.append([-gen.displacement(r, f, gx.ravel(), gy.ravel()).mean(0) for f in range(nf)])
    cm = fa.coeff(tr(np.array(Tm) - g[None]))
    out['T5']['R_pipe_patchmean_A'] = ev.evaluate(r, dict(rp, coeff_x=cm[0].tolist(), coeff_y=cm[1].tolist()))['field']['angstrom']
    out['T5']['centre_vs_patchmean_px'] = dict(rms=rms(np.array(Tm)-Tca), max=float(np.max(np.linalg.norm(np.array(Tm)-Tca, axis=-1))))
    gap = []
    for f in range(nf):
        qx, qy = gen.inverse(r, f, x, y)
        gap.append(gen.displacement(r, f, x, y) - gen.displacement(r, f, qx, qy))
    gap = np.array(gap); out['T5']['fwd_inv_gap_px'] = dict(rms=rms(gap), max=float(np.linalg.norm(gap, axis=-1).max()))
    # T6 observation vs fit.
    out['T6'] = dict(components_A={n: metrics_A(c, ps) for n, c in comps.items()},
                     groups_A=dict(repr=metrics_A(e_repr, ps), glob=metrics_A(e_glob_c+e_glob_r, ps), obs=metrics_A(e_obs_c+e_obs_r, ps)),
                     budget=ms_budget(e, comps),
                     budget_groups=ms_budget(e, dict(repr=e_repr, glob=e_glob_c+e_glob_r, obs=e_obs_c+e_obs_r)),
                     ablation_A={n: metrics_A(e-c, ps) for n, c in comps.items()} |
                                {'glob': metrics_A(e-e_glob_c-e_glob_r, ps), 'obs': metrics_A(e-e_obs_c-e_obs_r, ps),
                                 'glob+obs': metrics_A(e_repr, ps)})
    if use_local:
        it = {(p['xc'], p['yc']): p['iterations'] for p in patches}
        its = np.array([it[(int(k[0]), int(k[1]))] for k in keys])
        slope = [float(np.dot(delta[..., a].ravel(), obs_star[..., a].ravel())/np.dot(obs_star[..., a].ravel(), obs_star[..., a].ravel())) for a in (0, 1)]
        out['T6']['obs'] = dict(delta_rms_px=rms(delta), obs_star_rms_px=rms(obs_star), obs_rms_px=rms(obs),
                                delta_const_rms_px=rms(delta.mean(1)), delta_var_rms_px=rms(delta-d_c),
                                gain_slope_xy=slope,
                                delta_rms_px_by_iterations={str(k): rms(delta[its == k]) for k in sorted(set(its.tolist()))},
                                n_by_iterations={str(k): int((its == k).sum()) for k in sorted(set(its.tolist()))})
    return out


def main():
    names = sorted(p.name for p in RUNS.iterdir() if (p/'F').is_dir())
    res = [movie(n) for n in names]
    gates = dict(n=len(res),
                 G1=all(m['gates']['G1']['movie_sha_matches'] and m['gates']['G1']['recipe_matches'] for m in res),
                 G2=all(not m['gates']['G2_mismatches'] for m in res),
                 G3_max_px=max(m['gates']['G3_max_px'] for m in res if m['gates']['G3_max_px'] is not None),
                 G4_max_px=max(m['gates']['G4_max_px'] for m in res),
                 G5_max_px=max(m['gates']['G5_max_px'] for m in res))
    gates['pass'] = gates['G1'] and gates['G2'] and gates['G3_max_px'] <= 2e-5 and gates['G4_max_px'] <= .005 and gates['G5_max_px'] <= .005
    OUT.write_text(json.dumps(dict(schema='w7-error-budget/1', numpy=np.__version__, gates=gates, movies=res), indent=1, allow_nan=False)+'\n')
    print(json.dumps(gates))


if __name__ == '__main__':
    main()
