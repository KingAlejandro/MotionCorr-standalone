#!/usr/bin/env python3
"""Small additive known-motion family. See docs/motion_diagnostics_v2.md.

Only the historical MRC/STAR serializers are reused; no production warp is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from generate_known_motion_fixture import STAR_TEMPLATE, write_mrc_stack

SCHEMA = "motion-diagnostics/2"
PIXEL_SIZE = 0.885
FRAMES = 5
# No estimator result was used to choose these recipes or accuracy limits.
CASES = {
    "zero": dict(motion="zero"),
    "integer": dict(motion="integer"),
    "fractional": dict(motion="fractional"),
    "affine": dict(motion="affine"),
    "pedestal": dict(motion="affine", pedestal=4096.0, contrast=0.25),
    "noisy": dict(motion="affine", noise=4.0, role="characterization"),
    "flat": dict(motion="fractional", signal="flat", role="characterization"),
    "repeated": dict(motion="fractional", signal="repeated", role="characterization"),
}


def recipe(name):
    return dict(schema=SCHEMA, name=name, nx=128, ny=96, frames=FRAMES,
                pixel_size=PIXEL_SIZE, seed=238262, pedestal=100.0, contrast=1.0,
                noise=0.0, signal="multiband", role="gate", **{
                    k: v for k, v in CASES[name].items() if k not in
                    ("pedestal", "contrast", "noise", "signal", "role")}) | CASES[name]


def grid(r):
    y, x = np.mgrid[:r["ny"], :r["nx"]]
    return np.stack((x, y), axis=-1).astype(float)


def transform(r, f):
    """p = q + g + A(q-c); A and g are zero in reference frame 0."""
    t = f / (r["frames"] - 1)
    kind = r["motion"]
    g = np.array([0., 0.]) if kind == "zero" else np.array([3.25, -2.125]) * t
    if kind == "integer":
        g = np.array([f, -2*f], dtype=float)
    a = t * np.array([[0.012, -0.008], [0.006, -0.010]]) if kind == "affine" else np.zeros((2, 2))
    return g, a


def forward(r, f, q):
    g, a = transform(r, f)
    c = np.array([r["nx"], r["ny"]]) / 2
    return q + g + (q-c) @ a.T


def inverse(r, f, p):
    # Analytic affine inverse, not a negated displacement or image interpolation.
    g, a = transform(r, f)
    c = np.array([r["nx"], r["ny"]]) / 2
    return (p - g + c @ a.T) @ np.linalg.inv(np.eye(2) + a).T


def signal(r, q):
    x, y = q[..., 0], q[..., 1]
    s = np.zeros(x.shape)
    if r["signal"] == "repeated":
        s = np.cos(2*np.pi*x/16)  # y is unidentifiable; x only modulo 16.
    elif r["signal"] == "multiband":
        # Continuous frequencies in cycles/pixel, safely below Nyquist.
        for kx, ky, amp, phase in [(3, 2, 1., .2), (7, -3, .7, 1.1),
                                    (11, 5, .5, -.4), (19, -13, .25, .7)]:
            s += amp * np.cos(2*np.pi*(kx*x/r["nx"] + ky*y/r["ny"]) + phase)
        # Analytic asymmetric localized landmarks break periodic ambiguities.
        for cx, cy, amp, width in [(31, 23, 3., 3.), (82, 57, -2., 5.), (103, 34, 2., 4.)]:
            s += amp*np.exp(-((x-cx)**2+(y-cy)**2)/(2*width**2))
    return r["pedestal"] + r["contrast"]*s


def render(r):
    q = grid(r)
    target = signal(r, q)
    movie = np.stack([signal(r, inverse(r, f, q)) for f in range(r["frames"])])
    if r["noise"]:
        movie += np.random.Generator(np.random.PCG64(r["seed"])).normal(
            0, r["noise"]*r["contrast"], movie.shape)
    truth = np.stack([q-forward(r, f, q) for f in range(r["frames"])])
    return movie.astype("<f4"), target.astype("<f4"), truth


def validate_mapping(r):
    q = grid(r)
    closure = roundtrip = pixel_closure = 0.
    for f in range(r["frames"]):
        p = forward(r, f, q)
        closure = max(closure, float(np.max(np.linalg.norm(inverse(r, f, p)-q, axis=-1))))
        roundtrip = max(roundtrip, float(np.max(np.linalg.norm(forward(r, f, inverse(r, f, q))-q, axis=-1))))
        pixel_closure = max(pixel_closure, float(np.max(np.abs(signal(r, inverse(r, f, p))-signal(r, q)))))
    if max(closure, roundtrip) > 1e-10 or pixel_closure > 1e-9:
        raise ValueError("mapping closure failed")
    return dict(forward_inverse_max_px=closure, inverse_forward_max_px=roundtrip,
                continuous_signal_max_abs=pixel_closure)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(out):
    # Never silently replace an existing fixture or baseline.
    out.mkdir(parents=True, exist_ok=False)
    manifest = dict(schema=SCHEMA, numpy=np.__version__, cases={})
    for name in CASES:
        r = recipe(name)
        movie, target, truth = render(r)
        write_mrc_stack(out / f"{name}.mrcs", movie, PIXEL_SIZE)
        np.save(out / f"{name}_target.npy", target, allow_pickle=False)
        np.save(out / f"{name}_field.npy", truth, allow_pickle=False)
        (out / f"{name}.star").write_text(STAR_TEMPLATE.format(
            pixel_size=PIXEL_SIZE, voltage=300., movie=f"{name}.mrcs"))
        files = [f"{name}.mrcs", f"{name}_target.npy", f"{name}_field.npy", f"{name}.star"]
        manifest["cases"][name] = dict(recipe=r, closure=validate_mapping(r),
            files={f: digest(out/f) for f in files}, roi=[12, 84, 12, 116])
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, allow_nan=False)+"\n")
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", required=True, type=Path)
    args = ap.parse_args()
    generate(args.outdir)
