#!/usr/bin/env python3
"""Layer 2: forward-model simulation with a known noiseless object.

This is the only layer that can measure ABSOLUTE harm, because only here is
the true, motion-free specimen signal known. It answers the question a
reference comparison cannot: when a diagnostic reads X, how much recoverable
signal was actually lost?

Construction, per trial:

  1. draw a noiseless object T with a cryo-EM-like falling power spectrum;
  2. build an N-frame movie: frame f is T translated by the true motion
     trajectory, plus INDEPENDENT noise per frame at a stated dose;
  3. the ideal sum realigns every frame by the exact true shift and averages;
  4. a perturbed sum realigns by faulted shifts, or applies a faulted field.

Two measurements are then made on each perturbed sum:

  * ``ref_*``  -- diagnostics against the IDEAL SUM. This is what a gate sees.
  * ``truth_*`` -- the spectral transfer against the NOISELESS OBJECT T. This
    is the absolute harm, and it is not available to any gate.

The bridge between the two is the deliverable of this layer. In particular it
measures the layer-1 noise-blurring bias: how much larger a layer-1 relative
RMSE is than the pipeline's, for the same delta-B.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.calibration import diagnostics as dg           # noqa: E402
from tools.calibration import perturbations as pt          # noqa: E402
from tools.calibration.prespecification import (           # noqa: E402
    N_FRAMES,
    PIXEL_SIZE_A,
    X4_CORRELATION_LENGTHS,
    delta_b_for_sigma_px,
    split_grid,
)


def make_object(ny: int, nx: int, rng: np.random.Generator, pixel_size_a: float) -> np.ndarray:
    """A noiseless object with an amplitude spectrum that falls like a micrograph.

    Structure is generated as filtered noise rather than as discrete particles
    so that the spectral transfer estimator has signal in every shell; a sparse
    particle field would leave shells empty and make the envelope fit unstable
    for reasons that have nothing to do with the fault under test.
    """
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.rfftfreq(nx)[None, :]
    k = np.sqrt(fy * fy + fx * fx) / pixel_size_a           # Angstrom^-1
    # Falling envelope, roughly B = 100 A^2, with a 1/k low-frequency rise.
    env = np.exp(-100.0 * k * k / 4.0) / (k + 0.01)
    obj = np.fft.irfft2(np.fft.rfft2(rng.standard_normal((ny, nx))) * env, s=(ny, nx))
    obj -= obj.mean()
    return obj / obj.std()


def true_trajectory(n_frames: int, rng: np.random.Generator) -> np.ndarray:
    """A plausible beam-induced motion trajectory: fast early drift, slow later.

    Magnitudes are chosen to resemble the tutorial data, where accumulated
    motion is of order 15 A over 24 frames at 0.885 A/px, i.e. ~17 px total.
    """
    t = np.arange(n_frames, dtype=np.float64)
    drift = 12.0 * (1.0 - np.exp(-t / 3.0)) + 0.25 * t
    ang = rng.uniform(0.0, 2.0 * math.pi)
    traj = np.stack([drift * math.cos(ang), drift * math.sin(ang)], axis=1)
    traj += rng.standard_normal((n_frames, 2)) * 0.15        # small stochastic component
    return traj - traj[0]


def build_sum(
    obj: np.ndarray,
    applied: np.ndarray,
    true_traj: np.ndarray,
    noise_sigma: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sum the movie after realigning frame f by ``-applied[f]``.

    The detector records frame f as ``T(r - traj_f) + n_f(r)``: the noise is
    laid down in detector coordinates, on top of the already-moved specimen.
    Realignment translates the WHOLE recorded frame by ``-applied_f``, so

        aligned_f = T(r - (traj_f - applied_f)) + n_f(r + applied_f)

    Both terms move. Getting this wrong -- adding the noise after realignment,
    so that two runs with different applied shifts share an identical noise sum
    -- was a real defect in the first version of this file: it made a pure
    translation look like a 53 A^2 envelope loss, because the stationary noise
    anchored the cross-correlation. The noise ramp below is what makes the
    layer honest, and it is also why a residual shift error costs more than the
    signal blur alone: the summed noise decorrelates as well.

    When ``applied == true_traj`` the signal stacks coherently and the noise
    averages down by sqrt(N): the ideal sum.
    """
    ny, nx = obj.shape
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.rfftfreq(nx)[None, :]
    fobj = np.fft.rfft2(obj)
    acc = np.zeros((ny, nx // 2 + 1), dtype=np.complex128)
    for f in range(len(true_traj)):
        resid = true_traj[f] - applied[f]
        sig_ramp = np.exp(-2j * np.pi * (fx * resid[0] + fy * resid[1]))
        noise_ramp = np.exp(2j * np.pi * (fx * applied[f][0] + fy * applied[f][1]))
        frame_noise = np.fft.rfft2(rng.standard_normal((ny, nx)) * noise_sigma)
        acc += fobj * sig_ramp + frame_noise * noise_ramp
    return np.fft.irfft2(acc / len(true_traj), s=(ny, nx))


def truth_transfer(obj: np.ndarray, summed: np.ndarray, pixel_size_a: float) -> Dict[str, float]:
    """Spectral transfer of a summed micrograph against the noiseless object.

    Because the noise is independent of ``obj``, the shell-wise least-squares
    transfer converges to the true blur kernel, and the fitted delta-B is the
    absolute envelope loss -- not a comparison against another output.
    """
    std = dg.spectral_transfer_decomposition(obj, summed, pixel_size_a)
    return {f"truth_{k}": v for k, v in std.items()}


def run_trial(
    trial: int,
    ny: int,
    nx: int,
    n_frames: int,
    noise_sigma: float,
    pixel_size_a: float,
    border_px: int,
) -> List[Dict[str, Any]]:
    rng = np.random.default_rng(20260925 + 7919 * trial)
    obj = make_object(ny, nx, rng, pixel_size_a)
    traj = true_trajectory(n_frames, rng)

    noise_rng = np.random.default_rng(555_000 + trial)
    ideal = build_sum(obj, traj, traj, noise_sigma, noise_rng)
    ideal_truth = truth_transfer(obj, ideal, pixel_size_a)

    recs: List[Dict[str, Any]] = []

    def score(fault: str, severity: float, split: str, applied: np.ndarray | None,
              post=None, extra: Dict[str, Any] | None = None) -> None:
        nrng = np.random.default_rng(555_000 + trial)   # same noise realisation as ideal
        test = build_sum(obj, traj if applied is None else applied, traj, noise_sigma, nrng)
        if post is not None:
            test = post(test)
        rec: Dict[str, Any] = {
            "layer": "L2", "trial": trial, "fault": fault, "severity": severity,
            "split": split, "ny": ny, "nx": nx, "n_frames": n_frames,
            "noise_sigma": noise_sigma, **(extra or {}),
        }
        rec.update(dg.all_image_diagnostics(ideal, test, pixel_size_a, border_px))
        rec.update(truth_transfer(obj, test, pixel_size_a))
        rec["ideal_truth_delta_b_a2"] = ideal_truth["truth_delta_b_a2"]
        # Absolute harm: envelope loss of the perturbed sum relative to the
        # envelope loss the ideal sum already has.
        rec["harm_delta_b_a2"] = rec["truth_delta_b_a2"] - ideal_truth["truth_delta_b_a2"]
        recs.append(rec)
        print(f"  t{trial} {fault}={severity:g} {extra or ''} "
              f"relRMSE={rec['image_relative_rmse']:.4e} "
              f"gate_dB={rec['std_delta_b_a2']:+.3f} harm_dB={rec['harm_delta_b_a2']:+.3f} "
              f"eps={rec['std_eps_incoherent']:.3e}", flush=True)

    score("H4_null", 0.0, "control", None)

    for split, values in split_grid("X1_translation_px").items():
        for s in values:
            # Every frame realigned to the same wrong origin: a pure translation.
            off = np.full((n_frames, 2), s / math.sqrt(2.0))
            score("X1_translation_px", s, split, traj - off)

    for split, values in split_grid("X2_jitter_sigma_px").items():
        for s in values:
            jrng = np.random.default_rng(99_000 + trial * 31 + int(s * 1000))
            score("X2_jitter_sigma_px", s, split,
                  traj - pt.x2_jitter_kernel_transfer(s, n_frames, jrng))

    for split, values in split_grid("X3_drift_total_px").items():
        for s in values:
            score("X3_drift_total_px", s, split, traj - pt.x3_drift_shifts(s, n_frames))

    for split, values in split_grid("X4_localfield_rms_px").items():
        for s in values:
            for cl in X4_CORRELATION_LENGTHS:
                frng = np.random.default_rng(77_000 + trial * 37 + int(s * 1000) + int(cl * 100))
                field = pt.smooth_random_field((ny, nx), s, cl, frng)
                score("X4_localfield_rms_px", s, split, None,
                      post=lambda im, fl=field: pt.warp(im, fl),
                      extra={"correlation_fraction": cl})

    for split, values in split_grid("X5_applied_delta_b_a2").items():
        for s in values:
            score("X5_applied_delta_b_a2", s, split, None,
                  post=lambda im, b=s: pt.x5_attenuation(im, b, pixel_size_a))

    for split, values in split_grid("X7_hot_pixel_count").items():
        for s in values:
            hrng = np.random.default_rng(33_000 + trial * 41 + int(s))
            score("X7_hot_pixel_count", s, split, None,
                  post=lambda im, n=int(s), r=hrng: pt.x7_hot_pixels(im, n, r))

    return recs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--size", type=int, nargs=2, default=(1024, 1024), metavar=("NY", "NX"))
    ap.add_argument("--frames", type=int, default=N_FRAMES)
    ap.add_argument("--noise-sigma", type=float, default=3.0,
                    help="per-frame noise standard deviation, in units of object std")
    ap.add_argument("--pixel-size", type=float, default=PIXEL_SIZE_A)
    ap.add_argument("--border-px", type=int, default=100)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    records: List[Dict[str, Any]] = []
    for t in range(args.trials):
        print(f"[layer2] trial {t}", flush=True)
        records.extend(run_trial(t, args.size[0], args.size[1], args.frames,
                                 args.noise_sigma, args.pixel_size, args.border_px))
    args.out.write_text(json.dumps({"records": records,
                                    "config": vars(args) | {"out": str(args.out)}},
                                   indent=2, default=str))
    print(f"wrote {args.out} with {len(records)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
