#!/usr/bin/env python3
"""Check that reusing a cached gain reference across movies changes nothing.

The gain reference is read once per run rather than once per movie. Nothing in
the rest of the suite passes --gainref, so without this the whole gain path --
including the cache -- is unobserved.

Three cases, the third being the control that proves the other two can fail:
  identity  a gain of all 1.0 must reproduce the no-gain output exactly, since
            multiplying a float by 1.0f is exact
  reuse     two identical movies in one run must produce identical output, so a
            stale or empty cache entry on the second movie is caught
  control   a gain of 2.0 must NOT reproduce the no-gain output
"""
import argparse
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

NX, NY, NFRAMES = 48, 40, 6


def write_mrc(path: Path, frames, nx=NX, ny=NY):
    flat = [v for f in frames for v in f]
    nz = len(frames)
    h = bytearray(1024)
    struct.pack_into("<3i", h, 0, nx, ny, nz)
    struct.pack_into("<i", h, 12, 2)                       # mode 2 = float32
    struct.pack_into("<3i", h, 28, nx, ny, nz)
    struct.pack_into("<3f", h, 40, float(nx), float(ny), float(nz))
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


def synthetic_frames(seed=11):
    """A drifting blob on a textured background, deterministic without numpy."""
    state = seed
    def rnd():
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF
    base = [rnd() * 50.0 + 100.0 for _ in range(NX * NY)]
    frames = []
    for n in range(NFRAMES):
        f = list(base)
        cx, cy = NX // 2 + n, NY // 2 + (n % 2)
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < NX and 0 <= y < NY:
                    f[y * NX + x] += 400.0 / (1.0 + dx * dx + dy * dy)
        frames.append(f)
    return frames


def run(binary, star, out_dir, gain=None, extra=()):
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(binary), "--i", str(star), "--o", str(out_dir), "--use_own", "--j", "1",
           "--skip_defect", "--seed", "1", "--angpix", "1.0", "--voltage", "300",
           "--patch_x", "1", "--patch_y", "1", "--bfactor", "150", *extra]
    if gain is not None:
        cmd += ["--gainref", str(gain)]
    # Run from the star's directory so its relative movie names resolve.
    res = subprocess.run(cmd, cwd=str(star.parent), capture_output=True, text=True)
    if res.returncode != 0:
        print("STDOUT:\n", res.stdout[-3000:])
        print("STDERR:\n", res.stderr[-3000:])
        raise RuntimeError(f"motioncorr failed ({res.returncode})")
    return sorted(out_dir.glob("**/*.mrc"))


def corrected(paths):
    """Drop the gain copy the runner writes into its own output directory."""
    return [p for p in paths if p.name != "gain.mrc"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        frames = synthetic_frames()
        write_mrc(tmp / "movA.mrcs", frames)
        write_mrc(tmp / "movB.mrcs", frames)                     # byte-identical twin
        write_mrc(tmp / "gain_one.mrc", [[1.0] * (NX * NY)])
        write_mrc(tmp / "gain_two.mrc", [[2.0] * (NX * NY)])
        write_star(tmp / "one.star", ["movA.mrcs"])
        write_star(tmp / "two.star", ["movA.mrcs", "movB.mrcs"])

        nogain = corrected(run(args.binary, tmp / "one.star", tmp / "o_nogain"))
        assert len(nogain) == 1, f"expected 1 corrected image, got {len(nogain)}"
        ref = read_mrc_pixels(nogain[0])

        ones = corrected(run(args.binary, tmp / "one.star", tmp / "o_ones", tmp / "gain_one.mrc"))
        assert len(ones) == 1, f"expected 1 corrected image, got {len(ones)}"
        got = read_mrc_pixels(ones[0])
        assert got == ref, "identity gain changed the output; the applied gain is not all-ones"
        print("  identity: gain of 1.0 reproduces the no-gain output exactly")

        twos = corrected(run(args.binary, tmp / "one.star", tmp / "o_twos", tmp / "gain_two.mrc"))
        assert len(twos) == 1
        assert read_mrc_pixels(twos[0]) != ref, \
            "CONTROL FAILED: a gain of 2.0 produced the no-gain output, so this test cannot see the gain at all"
        print("  control:  gain of 2.0 does change the output (the checks above can fail)")

        pair = corrected(run(args.binary, tmp / "two.star", tmp / "o_pair", tmp / "gain_two.mrc"))
        assert len(pair) == 2, f"expected 2 corrected images, got {len(pair)}"
        a, b = read_mrc_pixels(pair[0]), read_mrc_pixels(pair[1])
        assert a == b, "identical movies gave different output; the gain differed between movie 1 and movie 2"
        first_only = corrected(run(args.binary, tmp / "one.star", tmp / "o_first", tmp / "gain_two.mrc"))
        assert a == read_mrc_pixels(first_only[0]), \
            "a movie's output depends on whether it ran first; cached gain state leaks between movies"
        print("  reuse:    second movie in a run matches the first, and matches a solo run")

    print("gain cache: all cases exact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
