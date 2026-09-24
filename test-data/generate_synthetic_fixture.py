#!/usr/bin/env python3
"""Generate deterministic synthetic MRC movie fixtures for MotionCorr testing and validation.

Creates synthetic movies with known ground truth frame shifts and Gaussian particle features.
Used to establish reference outputs and numerical acceptance gates without committing multi-gigabyte files.
"""

import argparse
import json
import struct
from pathlib import Path
from typing import List, Tuple

import numpy as np


def shift_image(img: np.ndarray, dx: float, dy: float, subpixel: bool = False) -> np.ndarray:
    """Shift an image by (dx, dy). Uses integer roll if not subpixel, else Fourier phase ramp."""
    if not subpixel:
        return np.roll(img, (int(round(dy)), int(round(dx))), axis=(0, 1))
    ny, nx = img.shape
    ky = np.fft.fftfreq(ny)[:, None]
    kx = np.fft.fftfreq(nx)[None, :]
    phase_ramp = np.exp(-2j * np.pi * (kx * dx + ky * dy))
    shifted = np.real(np.fft.ifft2(np.fft.fft2(img) * phase_ramp))
    return shifted.astype(np.float32)


def generate_movie(
    output_path: Path,
    nx: int = 128,
    ny: int = 128,
    nframes: int = 8,
    seed: int = 20260923,
    num_particles: int = 20,
    pixel_size: float = 1.0,
    voltage: float = 300.0,
    shift_scale_x: float = 0.4,
    shift_scale_y: float = -0.3,
    noise_sigma: float = 1.0,
    subpixel: bool = False,
) -> Tuple[Path, List[Tuple[float, float]], Path]:
    """Generate a synthetic MRC movie stack with known integer or subpixel shifts."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[:ny, :nx]
    image = np.full((ny, nx), 100.0, dtype=np.float32)

    # Place pseudo-particles
    for _ in range(num_particles):
        cx = rng.uniform(0, nx)
        cy = rng.uniform(0, ny)
        width = rng.uniform(2.0, max(3.0, min(nx, ny) / 20.0))
        amplitude = rng.uniform(10.0, 50.0)
        dx = (x - cx + nx / 2) % nx - nx / 2
        dy = (y - cy + ny / 2) % ny - ny / 2
        image += amplitude * np.exp(-(dx * dx + dy * dy) / (2.0 * width * width))

    # Ground truth shifts applied to frames
    if subpixel:
        known_shifts = [
            (float(shift_scale_x * i), float(shift_scale_y * i))
            for i in range(nframes)
        ]
    else:
        known_shifts = [
            (int(round(shift_scale_x * i)), int(round(shift_scale_y * i)))
            for i in range(nframes)
        ]

    stack = np.stack([
        shift_image(image, dx, dy, subpixel=subpixel) + rng.normal(0, noise_sigma, image.shape)
        for dx, dy in known_shifts
    ]).astype("<f4")

    # Construct standard 1024-byte MRC 2014 header
    header = bytearray(1024)
    # nx, ny, nz, mode (2 = 32-bit float)
    struct.pack_into("<4i", header, 0, nx, ny, nframes, 2)
    # nxstart, nystart, nzstart
    struct.pack_into("<3i", header, 16, 0, 0, 0)
    # mx, my, mz
    struct.pack_into("<3i", header, 28, nx, ny, nframes)
    # cell dimensions: length in angstroms
    struct.pack_into("<3f", header, 40, float(nx * pixel_size), float(ny * pixel_size), float(nframes * pixel_size))
    # cell angles (degrees)
    struct.pack_into("<3f", header, 52, 90.0, 90.0, 90.0)
    # axes map
    struct.pack_into("<3i", header, 64, 1, 2, 3)
    # dmin, dmax, dmean
    struct.pack_into("<3f", header, 76, float(stack.min()), float(stack.max()), float(stack.mean()))
    # ispg, nsymbt
    struct.pack_into("<2i", header, 88, 0, 0)
    # MAP 'MAP ' and machine stamp
    header[208:212] = b"MAP "
    header[212:216] = bytes((0x44, 0x41, 0, 0))  # Little-endian IEEE float
    # rms / std
    struct.pack_into("<f", header, 216, float(stack.std()))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        f.write(header)
        stack.tofile(f)

    # Write companion STAR file for RELION / MotionCorr input
    star_path = output_path.with_suffix(".star")
    rel_movie = output_path.name
    star_content = f"""# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 {pixel_size:.3f} {voltage:.1f} 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
{rel_movie} 1
"""
    star_path.write_text(star_content)

    # Write companion ground-truth shifts JSON
    gt_path = output_path.with_name(f"{output_path.stem}_ground_truth.json")
    expected_alignment_shifts = [(-dx, -dy) for dx, dy in known_shifts]
    gt_data = {
        "movie_file": output_path.name,
        "nx": nx,
        "ny": ny,
        "nframes": nframes,
        "pixel_size": pixel_size,
        "voltage": voltage,
        "applied_frame_rolls_xy": known_shifts,
        "expected_alignment_shifts_xy": expected_alignment_shifts,
        "seed": seed,
    }
    gt_path.write_text(json.dumps(gt_data, indent=2))

    return output_path, known_shifts, star_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=["small", "standard", "large"],
        default="small",
        help="Preset profile: small (128x128, 8 frames), standard (512x512, 16 frames), large (1536x1536, 32 frames)",
    )
    parser.add_argument("--outdir", type=Path, default=Path("test-data/fixtures"), help="Directory for generated files")
    parser.add_argument("--prefix", type=str, default="", help="Optional filename prefix")
    parser.add_argument("--seed", type=int, default=20260923, help="Random seed for reproducibility")
    parser.add_argument(
        "--subpixel",
        action="store_true",
        help="Generate subpixel (non-integer) shifts via Fourier phase shift interpolation",
    )
    args = parser.parse_args()

    subpixel_suffix = "_subpixel" if args.subpixel else ""
    if args.profile == "small":
        nx, ny, nframes, num_particles = 128, 128, 8, 20
        fname = f"{args.prefix}synthetic_128x128_8frames{subpixel_suffix}.mrcs"
        sx, sy = 0.4, -0.3
    elif args.profile == "standard":
        nx, ny, nframes, num_particles = 512, 512, 16, 150
        fname = f"{args.prefix}synthetic_512x512_16frames{subpixel_suffix}.mrcs"
        sx, sy = 0.6, -0.4
    else:
        nx, ny, nframes, num_particles = 1536, 1536, 32, 450
        fname = f"{args.prefix}synthetic_1536x1536_32frames{subpixel_suffix}.mrcs"
        sx, sy = 0.5, -0.35

    out_file = args.outdir / fname
    mrcs_path, shifts, star_path = generate_movie(
        out_file,
        nx=nx,
        ny=ny,
        nframes=nframes,
        seed=args.seed,
        num_particles=num_particles,
        shift_scale_x=sx,
        shift_scale_y=sy,
        subpixel=args.subpixel,
    )
    print(f"Successfully generated {mrcs_path} ({mrcs_path.stat().st_size} bytes)")
    print(f"STAR file: {star_path}")
    print(f"Known shifts ({len(shifts)} frames): {shifts}")


if __name__ == "__main__":
    main()
