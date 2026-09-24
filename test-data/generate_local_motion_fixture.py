#!/usr/bin/env python3
"""Generate deterministic synthetic MRC movie fixtures for MotionCorr local patch testing.

Produces:
1. local_motion.mrc: Movie ($128 \times 128 \times 8$ frames) with spatial differential
   motion across patches (affine/polynomial deformation) so 3x3 or 5x5 patches observe
   different non-zero trajectories.
2. fallback.mrc: Movie with extreme irregular noise / discontinuity that triggers
   polynomial fit fallback to global trajectory.
"""

import json
import struct
from pathlib import Path
from typing import Dict, Any
import numpy as np


def write_mrc(path: Path, stack: np.ndarray, pixel_size: float = 1.0) -> None:
    nframes, ny, nx = stack.shape
    header = bytearray(1024)
    struct.pack_into("<4i", header, 0, nx, ny, nframes, 2)
    struct.pack_into("<3i", header, 16, 0, 0, 0)
    struct.pack_into("<3i", header, 28, nx, ny, nframes)
    struct.pack_into("<3f", header, 40, float(nx * pixel_size), float(ny * pixel_size), float(nframes * pixel_size))
    struct.pack_into("<3f", header, 52, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", header, 64, 1, 2, 3)
    struct.pack_into("<3f", header, 76, float(stack.min()), float(stack.max()), float(stack.mean()))
    struct.pack_into("<2i", header, 88, 0, 0)
    header[208:212] = b"MAP "
    header[212:216] = bytes((0x44, 0x41, 0, 0))
    struct.pack_into("<f", header, 216, float(stack.std()))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(header)
        stack.astype("<f4").tofile(f)


def write_star(path: Path, movie_name: str, pixel_size: float = 1.0, voltage: float = 300.0) -> None:
    content = f"""# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 {pixel_size:.3f} {voltage:.1f} 2.7 0.1

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
{movie_name} 1
"""
    with path.open("w") as f:
        f.write(content)


def generate_local_motion_fixture(output_dir: Path) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    nx, ny, nframes = 128, 128, 8
    rng = np.random.default_rng(20260924)
    y, x = np.mgrid[:ny, :nx].astype(np.float32)

    # Base image with Gaussian particles
    base_image = np.full((ny, nx), 100.0, dtype=np.float32)
    for _ in range(40):
        cx = rng.uniform(10, nx - 10)
        cy = rng.uniform(10, ny - 10)
        width = rng.uniform(3.0, 6.0)
        amp = rng.uniform(20.0, 60.0)
        base_image += amp * np.exp(-((x - cx)**2 + (y - cy)**2) / (2.0 * width**2))

    # Apply spatially differential motion (global translation + spatial shear/stretch)
    frames = []
    ground_truth = []
    for iframe in range(nframes):
        t = iframe / float(nframes - 1)
        # Global component
        gx = 1.5 * t
        gy = -1.2 * t
        # Spatially varying component across the 128x128 field
        # Center is (64, 64)
        dx_field = gx + 0.8 * t * (x - 64.0) / 64.0 + 0.4 * t * (y - 64.0) / 64.0
        dy_field = gy - 0.5 * t * (x - 64.0) / 64.0 + 0.7 * t * (y - 64.0) / 64.0

        src_x = np.clip(x - dx_field, 0, nx - 1)
        src_y = np.clip(y - dy_field, 0, ny - 1)

        x0 = np.floor(src_x).astype(int)
        x1 = np.minimum(x0 + 1, nx - 1)
        y0 = np.floor(src_y).astype(int)
        y1 = np.minimum(y0 + 1, ny - 1)

        wx = src_x - x0
        wy = src_y - y0

        warped = (
            (1.0 - wx) * (1.0 - wy) * base_image[y0, x0] +
            wx * (1.0 - wy) * base_image[y0, x1] +
            (1.0 - wx) * wy * base_image[y1, x0] +
            wx * wy * base_image[y1, x1]
        )
        noise = rng.normal(0, 0.5, (ny, nx)).astype(np.float32)
        frame = (warped + noise).astype(np.float32)
        frames.append(frame)
        ground_truth.append({"frame": iframe, "mean_dx": float(np.mean(dx_field)), "mean_dy": float(np.mean(dy_field))})

    stack_local = np.stack(frames, axis=0)
    mrc_local = output_dir / "synthetic_local_motion.mrc"
    write_mrc(mrc_local, stack_local)
    write_star(output_dir / "synthetic_local_motion.star", str(mrc_local.resolve()))

    # 2. Fallback fixture: pure noise movie with no discernible feature correlation
    noise_frames = [rng.normal(100.0, 15.0, (ny, nx)).astype(np.float32) for _ in range(nframes)]
    stack_fallback = np.stack(noise_frames, axis=0)
    mrc_fallback = output_dir / "synthetic_fallback.mrc"
    write_mrc(mrc_fallback, stack_fallback)
    write_star(output_dir / "synthetic_fallback.star", str(mrc_fallback.resolve()))

    metadata = {
        "dimensions": [nx, ny, nframes],
        "local_motion_file": str(mrc_local.name),
        "fallback_file": str(mrc_fallback.name),
        "ground_truth": ground_truth
    }
    with (output_dir / "synthetic_local_meta.json").open("w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Generated {mrc_local} and {mrc_fallback}")
    return metadata


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "synthetic"
    generate_local_motion_fixture(out)
