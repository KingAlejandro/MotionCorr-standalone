#!/usr/bin/env python3
"""Image-level truth check for the #269 movies; no production warp is used.

Truth is the generator's own continuous scene s(q) (cubic B-spline of the oversampled
random field) sampled at detector pixel centres q of frame 0 (F_0 is the identity).
A published non-DW sum S of N frames estimates  N*(P + C*dose*s(q)), so we compare
  s_hat = (S/N - P)/(C*dose)   with   s.
Interior metrics (Hann-windowed Fourier rings, 0.01-0.16 cycles/px = the scene band)
exclude a 128 px margin; the outer 64 px is reported separately in real space.
Poisson noise is not removed: relRMSE is noise dominated, so the primary figure is the
signal transfer Re<S,T>/<T,T> per band (unbiased by independent noise), plus FRC.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'test-data'))
import generate_realistic_motion as gen

BANDS = [(.01, .04), (.04, .08), (.08, .12), (.12, .16)]   # cycles/pixel
INTERIOR_MARGIN = 128
BORDER_WIDTH = 64
PROFILE_EDGES = [0, 8, 16, 32, 64, 128, 10**9]
CONTROL_SIZE = 1536
CONTROL_PAD = 48


def truth_scene(r):
    """s(q) on the detector grid from the generator's continuous synthesis."""
    from scipy.ndimage import map_coordinates
    coeff, margin = gen.scene(r); s = r['oversample']
    out = np.empty((r['ny'], r['nx']), np.float32)
    for y0 in range(0, r['ny'], 256):
        y, x = np.mgrid[y0:min(y0+256, r['ny']), :r['nx']].astype(float)
        out[y0:y0+len(y)] = map_coordinates(coeff, [(y+margin)*s, (x+margin)*s], order=3, prefilter=False, mode='mirror')
    return out


def normalise(r, summed, frames=None):
    """Published sum (or mean if frames=1) -> unit-expectation scene units."""
    n = r['frames'] if frames is None else frames
    return (np.asarray(summed, np.float64)/n-r['pedestal'])/(r['scale']*r['dose'])


def interior(r):
    m = INTERIOR_MARGIN
    return np.s_[m:r['ny']-m, m:r['nx']-m]


def control_region(r):
    y0 = (r['ny']-CONTROL_SIZE)//2; x0 = (r['nx']-CONTROL_SIZE)//2
    return np.s_[y0:y0+CONTROL_SIZE, x0:x0+CONTROL_SIZE]


def _hann(n):
    return np.hanning(n+2)[1:-1]


def band_power(a, b, bands=BANDS):
    """Per-band sums <A,B*>, <A,A>, <B,B> over windowed, mean-removed rfft2 spectra."""
    h, w = a.shape; win = np.outer(_hann(h), _hann(w))
    fa = np.fft.rfft2(win*(a-a.mean())); fb = np.fft.rfft2(win*(b-b.mean()))
    f = np.hypot(np.fft.fftfreq(h)[:, None], np.fft.rfftfreq(w)[None, :])
    wt = np.full(fa.shape, 2.); wt[:, 0] = 1.
    if w % 2 == 0: wt[:, -1] = 1.
    rows = []
    for lo, hi in bands:
        m = (f >= lo) & (f < hi)
        rows.append(dict(band=[lo, hi], ab=float(np.sum(wt[m]*(fa[m]*fb[m].conj()).real)),
                         aa=float(np.sum(wt[m]*np.abs(fa[m])**2)), bb=float(np.sum(wt[m]*np.abs(fb[m])**2))))
    return rows


def spectral_metrics(est, tru):
    rows = band_power(est, tru)
    out = []
    for q in rows:
        out.append(dict(band=q['band'], transfer=q['ab']/q['bb'], frc=q['ab']/np.sqrt(q['aa']*q['bb'])))
    ab, aa, bb = (sum(q[k] for q in rows) for k in ('ab', 'aa', 'bb'))
    return dict(bands=out, transfer_inband=ab/bb, frc_inband=ab/np.sqrt(aa*bb),
                relrmse_inband=float(np.sqrt(max(aa-2*ab+bb, 0)/bb)))


def pixel_relrmse(est, tru):
    e = (est-est.mean())-(tru-tru.mean())
    return float(np.sqrt(np.mean(e*e))/np.std(tru))


def edge_distance(shape):
    y = np.arange(shape[0]); x = np.arange(shape[1])
    return np.minimum(np.minimum(y, shape[0]-1-y)[:, None], np.minimum(x, shape[1]-1-x)[None, :])


def border_profile(est, tru, ref_mean_slice):
    """RMS(est-tru)/std(tru) by distance to the nearest detector edge (real space, mean-matched on the interior)."""
    e = est-tru
    e = e-e[ref_mean_slice].mean()
    d = edge_distance(e.shape); sd = float(np.std(tru[ref_mean_slice]))
    prof = []
    for lo, hi in zip(PROFILE_EDGES[:-1], PROFILE_EDGES[1:]):
        m = (d >= lo) & (d < hi)
        if not m.any(): continue
        prof.append(dict(distance_px=[lo, min(hi, 10**6)], rel_rms=float(np.sqrt(np.mean(e[m]**2))/sd)))
    mb = d < BORDER_WIDTH
    return dict(profile=prof, border_rel_rms=float(np.sqrt(np.mean(e[mb]**2))/sd),
                interior_rel_rms=float(np.sqrt(np.mean(e[interior_slice_for(e.shape)]**2))/sd))


def interior_slice_for(shape):
    m = INTERIOR_MARGIN
    return np.s_[m:shape[0]-m, m:shape[1]-m]


def evaluate_sum(r, summed, truth):
    est = normalise(r, summed)
    sl = interior(r)
    res = dict(schema='motion-image-truth/1', interior=spectral_metrics(est[sl], truth[sl].astype(np.float64)),
               interior_pixel_relrmse=pixel_relrmse(est[sl], truth[sl].astype(np.float64)))
    res['border'] = border_profile(est, truth.astype(np.float64), sl)
    cs = control_region(r)
    res['control_region'] = spectral_metrics(est[cs], truth[cs].astype(np.float64))
    return res


def paired_effect(r, a, b, truth):
    """Effect of switching sum a -> b (same movie): profile of RMS(b-a) and change of squared error vs truth."""
    ea, eb, t = normalise(r, a), normalise(r, b), truth.astype(np.float64)
    sl = interior(r)
    off = (eb-ea)[sl].mean(); eb = eb-off          # mean-matched; DC is not an image effect
    d = edge_distance(ea.shape); sd = float(np.std(t[sl])); rows = []
    for lo, hi in zip(PROFILE_EDGES[:-1], PROFILE_EDGES[1:]):
        m = (d >= lo) & (d < hi)
        if not m.any(): continue
        diff = eb[m]-ea[m]
        rows.append(dict(distance_px=[lo, min(hi, 10**6)], pixels=int(m.sum()), rms_change=float(np.sqrt(np.mean(diff**2))/sd),
                         max_abs_change=float(np.abs(diff).max()/sd),
                         d_sq_error=float((np.sum((eb[m]-t[m])**2)-np.sum((ea[m]-t[m])**2))/(sd*sd))))
    return rows


# ---- negative / positive controls on an interior crop, from the movie itself -------------------

def control_sums(r, movie_path):
    """Oracle-aligned, zero-motion and wrong-sign sums of the raw movie on the control crop.

    Resampling is SciPy cubic (evaluator-side, independent of production). Frame f at
    detector p=F_f(q)=q+d_f(q) shows scene(q), so oracle samples p=q+d, wrong sign p=q-d.
    """
    from scipy.ndimage import map_coordinates
    cs = control_region(r); (y0, y1), (x0, x1) = [(s.start, s.stop) for s in cs]
    ys, xs = max(y0-CONTROL_PAD, 0), max(x0-CONTROL_PAD, 0)
    ye, xe = min(y1+CONTROL_PAD, r['ny']), min(x1+CONTROL_PAD, r['nx'])
    mm = np.memmap(movie_path, dtype='<f4', mode='r', offset=1024, shape=(r['frames'], r['ny'], r['nx']))
    y, x = np.mgrid[y0:y1, x0:x1].astype(float)
    acc = {k: np.zeros(y.shape) for k in ('oracle', 'zero', 'wrong_sign')}
    for f in range(r['frames']):
        cut = np.asarray(mm[f, ys:ye, xs:xe], np.float64)
        d = gen.displacement(r, f, x, y)
        for k, sgn in (('oracle', 1.), ('zero', 0.), ('wrong_sign', -1.)):
            acc[k] += map_coordinates(cut, [y+sgn*d[..., 1]-ys, x+sgn*d[..., 0]-xs], order=3, mode='nearest')
    return {k: normalise(r, v) for k, v in acc.items()}  # v is the sum over frames


def evaluate_controls(r, movie_path, truth):
    cs = control_region(r); t = truth[cs].astype(np.float64)
    out = dict(truth_vs_truth=spectral_metrics(t, t))
    for k, est in control_sums(r, movie_path).items():
        out[k] = spectral_metrics(est, t)
        out[k]['pixel_relrmse'] = pixel_relrmse(est, t)
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--receipt', type=Path, required=True); ap.add_argument('--sum', type=Path, required=True)
    ap.add_argument('--truth', type=Path, help='cached truth .npy (made if absent)'); ap.add_argument('--json', type=Path, required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from motion_field import read_mrc
    r = json.loads(a.receipt.read_text())['recipe']
    if a.truth and a.truth.exists(): truth = np.load(a.truth)
    else:
        truth = truth_scene(r)
        if a.truth: np.save(a.truth, truth)
    img, _ = read_mrc(a.sum)
    a.json.write_text(json.dumps(evaluate_sum(r, img[0], truth), indent=1, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
