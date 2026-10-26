#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Constant-velocity phase-ramp movies for the native CCF DC N controls (global alignment only).

Frame f is the base image shifted by f*vel through the Fourier shift theorem,
``frame_f(x) = base(x + f*vel)``, so the truth field of frame f is the constant ``f*vel`` px (the
convention of ``generate_motion_diagnostics``: its ``integer`` case is vel0 with N = 5). The base is
the K267 target image (``<case>_target.npy``, sha256 287e0a82...), regenerated here from the
versioned recipe; no source outside the repository is read. vel0 = (-1, 2), vel1 = (-0.8125, 0.53125)
px/frame, N in {5, 9, 13, 20}. Movies carry no noise. Truth is written to ``<name>_truth.npy`` for
the scoring stage only; the fitter and the tap bridge never read it.

    python3 generate_ccf_dc_n_controls.py --outdir <new dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

import generate_motion_diagnostics as gen
from generate_known_motion_fixture import STAR_TEMPLATE, write_mrc_stack

SCHEMA = "ccf-dc-n-controls/1"
VELOCITY = {"vel0": (-1.0, 2.0), "vel1": (-0.8125, 0.53125)}
FRAME_COUNTS = (5, 9, 13, 20)
BASE_SHA256 = "287e0a82ebb47a9230a6f3e2468ce417baebb1e23b8b94243f232a2cdb43da70"  # K267 *_target.npy


def base_image():
    r = gen.recipe("zero")
    return gen.signal(r, gen.grid(r)).astype("<f4")


def shifted_frames(base, vel, n, sign=1.0):
    """frame_f(x) = base(x + sign*f*vel) by the Fourier shift theorem, rounded once to float32."""
    ny, nx = base.shape
    spectrum = np.fft.fft2(base.astype(np.float64))
    ky = np.fft.fftfreq(ny)[:, None]
    kx = np.fft.fftfreq(nx)[None, :]
    frames = []
    for f in range(n):
        dx, dy = sign * f * vel[0], sign * f * vel[1]
        frames.append(np.fft.ifft2(spectrum * np.exp(2j * np.pi * (kx * dx + ky * dy))).real)
    return np.stack(frames).astype("<f4")


def truth(vel, n):
    return np.array([[f * vel[0], f * vel[1]] for f in range(n)], dtype=np.float64)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate(out):
    out.mkdir(parents=True, exist_ok=False)
    base = base_image()
    tmp = out / "base_target.npy"
    np.save(tmp, base, allow_pickle=False)
    if digest(tmp) != BASE_SHA256:
        raise ValueError("base image differs from the pinned K267 target")
    manifest = dict(schema=SCHEMA, base_sha256=BASE_SHA256, pixel_size=gen.PIXEL_SIZE, cases={})
    for vname, vel in VELOCITY.items():
        for n in FRAME_COUNTS:
            name = f"{vname}_N{n}"
            write_mrc_stack(out / f"{name}.mrcs", shifted_frames(base, vel, n), gen.PIXEL_SIZE)
            np.save(out / f"{name}_truth.npy", truth(vel, n), allow_pickle=False)
            (out / f"{name}.star").write_text(STAR_TEMPLATE.format(
                pixel_size=gen.PIXEL_SIZE, voltage=300., movie=f"{name}.mrcs"))
            files = [f"{name}.mrcs", f"{name}_truth.npy", f"{name}.star"]
            manifest["cases"][name] = dict(velocity=list(vel), frames=n, nx=base.shape[1], ny=base.shape[0],
                                           roi=[12, 84, 12, 116], files={f: digest(out / f) for f in files})
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", type=Path, required=True)
    generate(ap.parse_args().outdir)
