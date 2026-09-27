#!/usr/bin/env python3
"""Hot-pixel replacement must not depend on which movies were processed before it.

Hot-pixel correction (src/motioncorr_runner.cpp) re-seeds with
init_random_generator(random_seed) once per movie, then replaces each bad pixel:

    n_ok  = non-bad pixels in the clipped (2*D_MAX+1)^2 window, D_MAX = 2
    n_ok >  NUM_MIN_OK (6) -> pbuf[rand() % n_ok]
    n_ok <= NUM_MIN_OK (6) -> rnd_gaus(frame_mean, frame_std)

rnd_gaus() is a Marsaglia polar Box-Muller that produces two deviates per pass
and caches the second. If that cache survives the re-seed, a movie that made an
ODD number of Gaussian draws hands its leftover deviate to the NEXT movie, which
also consumes zero rand() calls where it should have consumed at least two --
desynchronising the whole uniform stream for the rest of that movie.

The test runs one probe movie alone and again preceded by a movie that makes an
odd number of Gaussian draws, and requires the probe's output to be identical.

Geometry note: for a solid 5x5 block of hot pixels, n_ok = 25 - f(r)*f(c) with
f = (3,4,5,4,3), so exactly the five plus-shaped centre cells get n_ok <= 6.
One block therefore contributes 5 Gaussian pixels; with 7 frames that is 35
Gaussian draws -- odd, which is what makes the leak observable.
"""

import argparse
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

NX = NY = 96
NFRAMES = 7          # odd, so (5 Gaussian pixels x NFRAMES) is odd
BLOCK = 5
HOT = 400.0
BACKGROUND = 30.0


def _noise(seed):
    """Deterministic LCG in [-1, 1); avoids a numpy dependency in the test."""
    state = seed & 0xFFFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield (state / 0x3FFFFFFF) - 1.0


def write_movie(path: Path, seed: int, block_origin, isolated):
    """Write a float32 MRC stack whose only above-threshold pixels are planted."""
    rng = _noise(seed)
    frames = []
    for _ in range(NFRAMES):
        f = [BACKGROUND + 2.5 * next(rng) for _ in range(NX * NY)]
        if block_origin is not None:
            r0, c0 = block_origin
            for r in range(r0, r0 + BLOCK):
                for c in range(c0, c0 + BLOCK):
                    f[r * NX + c] = HOT
        for (r, c) in isolated:
            f[r * NX + c] = HOT
        frames.append(f)

    flat = [v for f in frames for v in f]
    h = bytearray(1024)
    struct.pack_into("<3i", h, 0, NX, NY, NFRAMES)
    struct.pack_into("<i", h, 12, 2)                       # mode 2 = float32
    struct.pack_into("<3i", h, 28, NX, NY, NFRAMES)
    struct.pack_into("<3f", h, 40, float(NX), float(NY), float(NFRAMES))
    struct.pack_into("<3f", h, 52, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", h, 64, 1, 2, 3)
    struct.pack_into("<3f", h, 76, min(flat), max(flat), sum(flat) / len(flat))
    h[208:212] = b"MAP "
    struct.pack_into("<i", h, 212, 0x00004144)
    with open(path, "wb") as fh:
        fh.write(bytes(h))
        fh.write(struct.pack(f"<{len(flat)}f", *flat))


def write_star(path: Path, movies):
    path.write_text(
        "# version 30001\n\ndata_optics\n\nloop_\n"
        "_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
        "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n"
        "_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n"
        "opticsGroup1 1 1.000 300.0 2.7 0.1\n\n"
        "# version 30001\n\ndata_movies\n\nloop_\n"
        "_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n"
        + "\n".join(f"{m} 1" for m in movies) + "\n"
    )


def read_mrc_pixels(path: Path) -> bytes:
    """Pixel bytes only: the MRC label area carries a wall-clock timestamp."""
    data = path.read_bytes()
    nx, ny, nz, mode = struct.unpack("<4i", data[:16])
    if mode != 2:
        raise ValueError(f"Unsupported MRC mode: {mode}")
    return data[1024:1024 + nx * ny * nz * 4]


def read_hotpixels(star: Path):
    """Ordered hot-pixel coordinates from a per-movie STAR file."""
    coords, in_block = [], False
    for line in star.read_text().splitlines():
        t = line.strip()
        if t.startswith("data_"):
            in_block = t == "data_hot_pixels"
            continue
        if not in_block or not t or t == "loop_" or t.startswith("_") or t.startswith("#"):
            continue
        f = t.split()
        if len(f) >= 2:
            coords.append((int(float(f[0])), int(float(f[1]))))
    return coords


def run(binary: Path, star: Path, out_dir: Path, work: Path):
    cmd = [
        str(binary.resolve()), "--i", str(star.resolve()), "--o", str(out_dir.resolve()),
        "--use_own", "--j", "1", "--angpix", "1.0",
        "--patch_x", "1", "--patch_y", "1", "--seed", "1",
    ]
    res = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True)
    if res.returncode != 0:
        print("STDOUT:\n", res.stdout)
        print("STDERR:\n", res.stderr)
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(cmd)}")


def test_hotpixel_rng_determinism(binary: Path = None):
    repo_root = Path(__file__).resolve().parent.parent
    if binary is None:
        binary = repo_root / "build" / "motioncorr"
    if not binary.is_file():
        raise FileNotFoundError(f"motioncorr binary not found at {binary}. Build with cmake first.")

    block = (40, 40)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        write_movie(work / "probe.mrcs", 11, block, [(10, 15), (80, 25)])
        write_movie(work / "lead.mrcs", 22, block, [(20, 70)])
        write_star(work / "probe_alone.star", ["probe.mrcs"])
        write_star(work / "lead_then_probe.star", ["lead.mrcs", "probe.mrcs"])

        run(binary, work / "probe_alone.star", work / "out_alone", work)
        run(binary, work / "lead_then_probe.star", work / "out_after", work)

        alone = work / "out_alone" / "probe.mrc"
        after = work / "out_after" / "probe.mrc"

        # Precondition, actually observed rather than assumed: the whole 5x5 block
        # must have been flagged hot. That is exactly the geometry that drives
        # n_ok to 0 at the block centre and so forces the Gaussian branch. Without
        # this check the test could pass simply by never reaching that branch.
        hot = set(read_hotpixels(work / "out_alone" / "probe.star"))
        expected_block = {(c, r)
                          for r in range(block[0], block[0] + BLOCK)
                          for c in range(block[1], block[1] + BLOCK)}
        missing = expected_block - hot
        assert not missing, (
            f"Gaussian branch not exercised: {len(missing)} of {BLOCK * BLOCK} block "
            f"pixels were not detected as hot (e.g. {sorted(missing)[:4]}). "
            f"Detected {len(hot)} hot pixels total."
        )
        print(f"Precondition: full {BLOCK}x{BLOCK} hot block detected "
              f"({len(hot)} hot pixels total) -> Gaussian branch reached.")

        pix_alone, pix_after = read_mrc_pixels(alone), read_mrc_pixels(after)
        n_diff = sum(1 for a, b in zip(pix_alone, pix_after) if a != b)
        print(f"probe.mrc pixel bytes: {len(pix_alone)}; differing: {n_diff}")

        assert pix_alone == pix_after, (
            "Hot-pixel replacement leaked across a movie boundary: probe.mrc differs "
            "depending on whether another movie was processed first in the same "
            f"process ({n_diff} of {len(pix_alone)} pixel bytes differ). A Gaussian "
            "deviate cached by rnd_gaus() survived init_random_generator()."
        )

    print("\nSUCCESS: hot-pixel replacement is independent of movie order and count.")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=None, help="Path to motioncorr binary")
    args = parser.parse_args()
    sys.exit(0 if test_hotpixel_rng_determinism(binary=args.binary) else 1)


if __name__ == "__main__":
    main()
