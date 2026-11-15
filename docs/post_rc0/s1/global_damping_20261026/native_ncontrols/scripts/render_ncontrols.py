#!/usr/bin/env python3
"""Render the W5 phase-ramp controls as native input movies and prove they equal the W5 frames.

usage: render_ncontrols.py OUTDIR SRC_ROOT        (run on cpu64; W5 scratch is read-only and used in place)

W5 definition (w5_intervention_20261025/scripts/intervention.py, probes block): base image = pinned fixtures/integer_target.npy (128 x 96),
Ft = fft2(base)/(NX*NY), frame f spectrum = shiftF(Ft, -f*vel) with shiftF from the pinned independent review's indep.py,
vel0 = (-1, 2) and vel1 = (-0.8125, 0.53125) px/frame, N = 5, 9, 13, 20; truth = the constant field f*vel. Nothing else is added (no noise).
The W5 spectra are loaded with W5's own code (common.verify pins every input) and the real-space movie is their inverse transform.

Written per movie: NAME.mrcs (mode 2, float32, un-flipped, the repo's write_mrc_stack), NAME.star (the repo's STAR_TEMPLATE), NAME_truth.npy.
Checks (all in OUTDIR/render_report.json): sha256 of the W5 float64 frames; independent re-render by a separate formula (max abs diff);
imaginary part discarded by taking the real part (max); stored float32 vs float64 frames (max abs diff); spectrum of the stored frames vs the W5 spectrum;
the W5 replay (indep.py replay) on the stored frames vs on the W5 spectra and vs W5 factorial.json trajectories; MRC read-back equality and the row-order null control.
"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
out = Path(sys.argv[1]).resolve(); src = Path(sys.argv[2]).resolve()
W5 = Path('/tmp/motioncorr-w5-20261025-7b76b848')
sys.path[:0] = [str(W5/'scripts'), str(src/'test-data'), str(src/'tools')]
import common as C
C.verify()
from generate_known_motion_fixture import STAR_TEMPLATE, write_mrc_stack
from motion_field import read_mrc
sha = lambda b: hashlib.sha256(b).hexdigest()
indep = (C.IN/'retained/review/round1/indep.py').read_text().split('out = {}')[0]
argv0 = sys.argv; sys.argv = ['indep.py', str(C.IN)]; ns = {}
exec(compile(indep, 'pinned-indep.py[definitions]', 'exec'), ns); sys.argv = argv0
NX, NY = C.NX, C.NY
tgt = np.load(C.IN/'fixtures/integer_target.npy', allow_pickle=False).astype(float)
Ft = np.fft.fft2(tgt)/(NX*NY)
kx = np.fft.fftfreq(NX)*NX; ky = np.fft.fftfreq(NY)*NY
fact = json.loads((W5/'results/factorial.json').read_text())['probes']
out.mkdir(parents=True, exist_ok=False)
report = dict(base_image_sha256=sha((C.IN/'fixtures/integer_target.npy').read_bytes()), indep_py_sha256=sha((C.IN/'retained/review/round1/indep.py').read_bytes()),
              common_py_sha256=sha((W5/'scripts/common.py').read_bytes()), movies={})
for iv, vel in enumerate(((-1., 2.), (-.8125, .53125))):
    for N in (5, 9, 13, 20):
        name = f'vel{iv}_N{N}'
        tt = np.arange(N)[:, None]*np.array(vel)[None]
        F0 = np.stack([ns['shiftF'](Ft, -t) for t in tt])                 # W5 spectra
        full = np.fft.ifft2(F0*(NX*NY))                                    # W5 frames, complex
        frames = full.real
        # independent re-render: separate formula, no W5 code
        gx, gy = np.meshgrid(kx/NX, ky/NY)
        ind = np.stack([np.fft.ifft2(np.fft.fft2(tgt)*np.exp(-2j*np.pi*(gx*(-t[0])+gy*(-t[1])))).real for t in tt])
        stored32 = frames.astype('<f4')
        write_mrc_stack(out/f'{name}.mrcs', stored32, C.PIX)
        (out/f'{name}.star').write_text(STAR_TEMPLATE.format(pixel_size=C.PIX, voltage=300., movie=f'{name}.mrcs'))
        np.save(out/f'{name}_truth.npy', tt, allow_pickle=False)
        back = read_mrc(out/f'{name}.mrcs')[0]
        # spectrum of the stored frames vs the W5 spectrum
        F1 = np.fft.fft2(back.astype(float))/(NX*NY)
        # W5 replay (prod and iso weights, both stops) on W5 spectra vs on the stored frames vs W5 factorial.json
        rep = {}
        ns['NF'] = N
        for wn, W in (('prod', ns['W_prod']), ('iso', ns['W_iso'])):
            for it, tol in ((5, .5), (50, 1e-9)):
                a0, _, _ = ns['replay'](F0.copy(), W, iters=it, tol=tol)
                a1, _, _ = ns['replay'](F1.copy(), W, iters=it, tol=tol)
                w5 = np.array(fact[f'vel{iv}-N{N}-{wn}-{it}it']['global_trajectory'])
                rep[f'{wn}-{it}it'] = dict(w5_spectra_vs_factorial_json_max_px=float(np.abs(a0-w5).max()),
                                           stored_frames_vs_w5_spectra_max_px=float(np.abs(a1-a0).max()),
                                           stored_frames_vs_factorial_json_max_px=float(np.abs(a1-w5).max()))
        f0 = back[0]
        report['movies'][name] = dict(
            N=N, vel=list(vel), mrcs_sha256=sha((out/f'{name}.mrcs').read_bytes()), star_sha256=sha((out/f'{name}.star').read_bytes()),
            w5_frames_float64_sha256=sha(np.ascontiguousarray(frames).tobytes()), w5_frames_float32_sha256=sha(stored32.tobytes()),
            independent_rerender_max_abs_diff=float(np.abs(ind-frames).max()),
            discarded_imaginary_part_max_abs=float(np.abs(full.imag).max()),
            stored_float32_vs_w5_float64_max_abs_diff=float(np.abs(back.astype(float)-frames).max()),
            frame_value_range=[float(frames.min()), float(frames.max())],
            stored_spectrum_vs_w5_spectrum_max_abs=float(np.abs(F1-F0).max()), w5_spectrum_max_abs=float(np.abs(F0).max()),
            mrc_readback_equals_written=bool(np.array_equal(back, stored32)),
            row_order=dict(frame0_vs_base_max_abs=float(np.abs(f0-tgt).max()), frame0_vs_base_flipud_max_abs=float(np.abs(f0-tgt[::-1]).max()),
                           frame0_vs_base_fliplr_max_abs=float(np.abs(f0-tgt[:, ::-1]).max())),
            replay_checks=rep)
rp = out/'render_report.json'
rp.write_text(json.dumps(report, indent=1, allow_nan=False)+'\n')
worst = lambda k: max(m[k] for m in report['movies'].values())
print('movies', len(report['movies']), 'independent re-render max', worst('independent_rerender_max_abs_diff'),
      'float32 vs float64 max', worst('stored_float32_vs_w5_float64_max_abs_diff'), 'imag max', worst('discarded_imaginary_part_max_abs'))
print('replay: w5 spectra vs factorial.json max px', max(v['w5_spectra_vs_factorial_json_max_px'] for m in report['movies'].values() for v in m['replay_checks'].values()),
      '; stored frames vs w5 spectra max px', max(v['stored_frames_vs_w5_spectra_max_px'] for m in report['movies'].values() for v in m['replay_checks'].values()))
