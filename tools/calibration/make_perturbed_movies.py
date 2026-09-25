#!/usr/bin/env python3
"""Write movie-space perturbations of a tutorial movie for the layer-3 pilot.

Three variants per movie, plus the control that makes them interpretable:

  ``null``   the movie re-encoded from TIFF into an MRC stack, unchanged.
             Without this, any TIFF-versus-MRC decoding difference would be
             charged to the perturbation.
  ``shiftN`` every frame rolled by N pixels in x and y, WITH THE GAIN
             REFERENCE ROLLED BY THE SAME AMOUNT. Rolling the movie alone
             would misalign the gain pattern against the detector and turn an
             accounted-for translation into a gain fault.
  ``hotN``   N pixels forced to a large count in every frame, at fixed
             positions -- a stuck-hot detector defect rather than a transient.

Output is MRC mode 6 (uint16), matching the source dtype exactly, so no
quantisation is introduced by the rewrite itself.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np
import tifffile


def write_mrc_stack_uint16(path: Path, stack: np.ndarray, pixel_size_a: float) -> None:
    nz, ny, nx = stack.shape
    header = bytearray(1024)
    struct.pack_into("<4i", header, 0, nx, ny, nz, 6)          # mode 6 = uint16
    struct.pack_into("<3i", header, 16, nx, ny, nz)
    struct.pack_into("<3f", header, 28, nx * pixel_size_a, ny * pixel_size_a, nz * pixel_size_a)
    struct.pack_into("<3f", header, 40, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", header, 52, 1, 2, 3)
    struct.pack_into("<3f", header, 76, float(stack.min()), float(stack.max()), float(stack.mean()))
    header[208:212] = b"MAP "
    struct.pack_into("<i", header, 212, 0x00004144)
    struct.pack_into("<f", header, 216, float(stack.std()))
    with open(path, "wb") as fh:
        fh.write(bytes(header))
        fh.write(np.ascontiguousarray(stack, dtype="<u2").tobytes())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tiff", type=Path, required=True)
    ap.add_argument("--gain", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--tag", required=True, help="short movie id, e.g. 00021")
    ap.add_argument("--shift-px", type=int, default=2)
    ap.add_argument("--hot-counts", type=int, nargs="*", default=[100, 10000])
    ap.add_argument("--hot-value", type=int, default=10000)
    ap.add_argument("--pixel-size", type=float, default=0.885)
    ap.add_argument("--seed", type=int, default=20260925)
    ap.add_argument("--flip-y", action="store_true",
                    help="write rows bottom-up. The TIFF and MRC movie readers "
                         "disagree on row order: re-encoding a tutorial TIFF into "
                         "an MRC stack unchanged gave a relative RMSE of 1.435 "
                         "against the TIFF run, falling to 0.700 when the output "
                         "was flipped, because the gain reference is then also "
                         "applied upside down. The null control in this script "
                         "exists to catch exactly that, and this flag is how the "
                         "movie-space arm is made comparable to the TIFF baseline.")
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    with tifffile.TiffFile(args.tiff) as t:
        stack = np.stack([p.asarray() for p in t.pages]).astype(np.uint16)
    print(f"read {args.tiff.name}: {stack.shape} {stack.dtype} "
          f"min={stack.min()} max={stack.max()} mean={stack.mean():.4f}", flush=True)
    if args.flip_y:
        stack = stack[:, ::-1, :].copy()
        print("flipped rows bottom-up to match the TIFF reader convention", flush=True)

    write_mrc_stack_uint16(args.outdir / f"{args.tag}_null.mrcs", stack, args.pixel_size)
    print("wrote null", flush=True)

    n = args.shift_px
    rolled = np.roll(np.roll(stack, n, axis=2), n, axis=1)
    write_mrc_stack_uint16(args.outdir / f"{args.tag}_shift{n}.mrcs", rolled, args.pixel_size)
    print(f"wrote shift{n}", flush=True)

    # Roll the gain by the same amount so the perturbation stays a pure
    # translation of the recorded field rather than a gain mismatch.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.calibration import mrcio
    gain, ghdr = mrcio.read_mrc_2d(args.gain)
    g_rolled = np.roll(np.roll(gain, n, axis=1), n, axis=0)
    if args.flip_y:
        # The movie rows were flipped, so the translation the detector sees is
        # downward rather than upward; roll the gain the matching way.
        g_rolled = np.roll(np.roll(gain, n, axis=1), -n, axis=0)
    mrcio.write_mrc_2d(args.outdir / f"gain_shift{n}.mrc", g_rolled, ghdr)
    print(f"wrote gain_shift{n}", flush=True)

    rng = np.random.default_rng(args.seed)
    ny, nx = stack.shape[1], stack.shape[2]
    for count in args.hot_counts:
        hot = stack.copy()
        flat = rng.choice(ny * nx, size=int(count), replace=False)
        ys, xs = np.unravel_index(flat, (ny, nx))
        hot[:, ys, xs] = np.uint16(args.hot_value)
        write_mrc_stack_uint16(args.outdir / f"{args.tag}_hot{count}.mrcs", hot, args.pixel_size)
        print(f"wrote hot{count}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
