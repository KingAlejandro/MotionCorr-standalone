#!/usr/bin/env python3
"""Generate a small (~2 MB) synthetic multi-frame TIFF movie with a realistic
cryo-EM beam-induced motion trajectory, synthetic particles, and detector defects.
"""

import os
from pathlib import Path
import numpy as np
from PIL import Image


def generate_synthetic_movie(output_path: Path):
    nx, ny, n_frames = 512, 512, 8

    # Fixed seed for complete determinism
    rng = np.random.RandomState(42)

    # Base background
    base = np.zeros((ny, nx), dtype=np.float32) + 30.0

    # 60 synthetic Gaussian particles
    for _ in range(60):
        cx = rng.uniform(30, nx - 30)
        cy = rng.uniform(30, ny - 30)
        sigma = rng.uniform(4.0, 12.0)
        amp = rng.uniform(15.0, 45.0)

        y, x = np.ogrid[:ny, :nx]
        dist_sq = (x - cx) ** 2 + (y - cy) ** 2
        base += amp * np.exp(-dist_sq / (2.0 * sigma**2))

    # Realistic trajectory: early rapid doming relaxation + steady drift
    t = np.arange(n_frames, dtype=np.float32)
    dx = 3.5 * (1.0 - np.exp(-t / 1.8)) + 0.3 * t
    dy = -2.8 * (1.0 - np.exp(-t / 1.5)) + 0.25 * t

    frames = []
    for i in range(n_frames):
        shift_x = dx[i]
        shift_y = dy[i]

        # Fourier subpixel translation
        fft_base = np.fft.rfft2(base)
        ky = np.fft.fftfreq(ny)[:, None]
        kx = np.fft.rfftfreq(nx)[None, :]
        phase = np.exp(-2j * np.pi * (kx * shift_x + ky * shift_y))
        shifted = np.fft.irfft2(fft_base * phase, s=(ny, nx))

        # Add Gaussian noise
        noise = rng.normal(0.0, 2.5, (ny, nx))
        frame_val = np.clip(shifted + noise, 0, 255).astype(np.uint8)

        # Hot pixels (detector defects)
        frame_val[120, 180] = 250
        frame_val[350, 410] = 255
        frame_val[200, 310] = 248
        frame_val[450, 100] = 252
        frame_val[80, 420] = 254

        frames.append(Image.fromarray(frame_val))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(str(output_path), save_all=True, append_images=frames[1:], compression=None)
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Generated synthetic movie: {output_path} ({size_mb:.2f} MB, {n_frames} frames, {nx}x{ny})")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "synthetic_movie.tiff"
    generate_synthetic_movie(out)

