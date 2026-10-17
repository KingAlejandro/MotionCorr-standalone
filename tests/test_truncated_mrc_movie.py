#!/usr/bin/env python3
"""A truncated raw MRC movie must fail its movie, not publish products (RC0 F3).

Image<T>::read signals a short raw MRC only through a negative return (-2, a
short fread). The runner's per-frame read loop used to drop that value, so a
movie shorter than its header implies ran to completion over unread frame
memory and published corrected products and a completion STAR.

For MRC modes 0, 1, 2, 6, 12 and 101 a synthetic 8-frame movie is written in
full and as four truncated copies: cut mid-frame, cut on a frame boundary, cut
inside the last frame, and header only. Checked for each mode (and, with
--gpu, for each requested --ingest route):

  * the valid movie exits 0 and publishes products; with --baseline-binary
    (an unmodified build) its output tree is byte-identical to the baseline's;
  * each truncated copy exits non-zero without a signal, names the movie and
    the lowest unreadable frame in one route-invariant message, and leaves no
    MRC, STAR or EPS product;
  * a batch of one valid and one truncated movie completes the valid movie
    with products identical to its single-movie run, exits non-zero, and
    withholds the joint STAR.

The truncation checks must fail on a build without the fix: run this script
with --binary pointing at the unmodified build.
"""
import argparse
import math
import random
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "profiling"))
from lib import identity  # noqa: E402

NX = NY = 128
NFRAMES = 8
HEADER = 1024
MODES = (0, 1, 2, 6, 12, 101)
# Modes the compact CUDA staging admits; --ingest compact refuses the others.
COMPACT_MODES = (0, 1, 6)
MESSAGE = "Failed to read frame %d (0-based) of %s: the movie is truncated or unreadable."

STAR_HEAD = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 1.000 300.0 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
"""


def make_frames():
    """Integer-valued frames in 0..~110 with periodic content and known drift."""
    rng = random.Random(20261016)
    blobs = [(rng.uniform(0, NX), rng.uniform(0, NY), rng.uniform(2.0, 6.0), rng.uniform(10.0, 50.0))
             for _ in range(20)]
    base = [[40.0] * NX for _ in range(NY)]
    for cx, cy, width, amp in blobs:
        for y in range(NY):
            dy = (y - cy + NY / 2) % NY - NY / 2
            for x in range(NX):
                dx = (x - cx + NX / 2) % NX - NX / 2
                base[y][x] += amp * math.exp(-(dx * dx + dy * dy) / (2.0 * width * width))
    frames = []
    for i in range(NFRAMES):
        sx, sy = round(0.4 * i), round(-0.3 * i)
        frames.append([int(round(base[(y - sy) % NY][(x - sx) % NX] + rng.uniform(-3, 3)))
                       for y in range(NY) for x in range(NX)])
    return frames


def encode_frame(values, mode):
    n = len(values)
    if mode == 0:
        return struct.pack("<%db" % n, *[v - 50 for v in values])
    if mode == 1:
        return struct.pack("<%dh" % n, *[(v - 50) * 100 for v in values])
    if mode == 2:
        return struct.pack("<%df" % n, *[float(v) for v in values])
    if mode == 6:
        return struct.pack("<%dH" % n, *[v * 500 for v in values])
    if mode == 12:
        return struct.pack("<%de" % n, *[float(v) for v in values])
    # Mode 101: two 4-bit samples per byte, first sample in the low nibble.
    q = [min(15, v * 15 // 110) for v in values]
    return bytes(q[i] | (q[i + 1] << 4) for i in range(0, n, 2))


def mrc_header(mode):
    h = bytearray(HEADER)
    struct.pack_into("<4i", h, 0, NX, NY, NFRAMES, mode)
    struct.pack_into("<3i", h, 28, NX, NY, NFRAMES)
    struct.pack_into("<3f", h, 40, float(NX), float(NY), float(NFRAMES))
    struct.pack_into("<3f", h, 52, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", h, 64, 1, 2, 3)
    struct.pack_into("<3f", h, 76, 0.0, 255.0, 100.0)
    h[208:212] = b"MAP "
    h[212:216] = bytes((0x44, 0x41, 0, 0))
    return bytes(h)


def variants(mode, frames):
    """name -> (file bytes, lowest frame index that cannot be read, or None when valid)."""
    pages = [encode_frame(f, mode) for f in frames]
    fb = len(pages[0])
    full = mrc_header(mode) + b"".join(pages)
    return {
        "valid": (full, None),
        "mid-frame": (full[:HEADER + 4 * fb + fb // 2], 4),
        "frame-boundary": (full[:HEADER + 5 * fb], 5),
        "last-frame": (full[:HEADER + 7 * fb + fb // 2], 7),
        "header-only": (full[:HEADER], 0),
    }


def run(binary, work, label, movies, gpu, ingest, extra_files=None, extra_args=()):
    """movies: ordered {name: bytes}. Returns (rc, text, out dir, witness lines).

    extra_files {name: bytes} are written beside the movies and extra_args appended to the command.
    """
    data = work / label / "data"
    out = work / label / "out"
    data.mkdir(parents=True)
    out.mkdir()
    for name, payload in {**movies, **(extra_files or {})}.items():
        (data / name).write_bytes(payload)
    (data / "movies.star").write_text(STAR_HEAD + "".join("%s 1\n" % n for n in movies))
    witness = work / label / "witness.txt"
    cmd = [str(Path(binary).resolve()), "--i", "movies.star", "--o", str(out) + "/", "--use_own",
           "--j", "2", "--dose_weighting", "--dose_per_frame", "1.0", "--voltage", "300",
           "--angpix", "1.0", "--patch_x", "3", "--patch_y", "3", "--bfactor", "150", "--seed", "1",
           *extra_args]
    if gpu is not None:
        cmd += ["--gpu", str(gpu), "--ingest", ingest, "--ingest_witness", str(witness)]
    res = subprocess.run(cmd, cwd=data, capture_output=True, text=True, timeout=600)
    lines = witness.read_text().split("\n") if witness.exists() else []
    return res.returncode, res.stdout + res.stderr, out, [l for l in lines if l]


def products(out):
    return sorted(str(p.relative_to(out)) for p in Path(out).rglob("*")
                  if p.is_file() and p.suffix.lower() in (".mrc", ".mrcs", ".star", ".eps"))


def movie_inventory(tree, stem):
    """Relative paths of one movie's products (everything the comparator compares)."""
    return sorted(r for r in identity.inventory(str(tree)) if Path(r).name.startswith(stem)
                  and Path(r).suffix.lower() not in identity.EXCLUDED)


def per_movie_identical(single, batch, stem):
    """One movie's files in a batch tree against its single-movie tree; None when identical.

    The per-movie inventories of BOTH trees must match before any bytes are compared, so a
    healthy movie's STAR or EPS missing from either tree is a difference even when its MRC survives.
    """
    inv_single, inv_batch = movie_inventory(single, stem), movie_inventory(batch, stem)
    if inv_single != inv_batch:
        return "per-movie inventories differ: only single %s, only batch %s" % (
            sorted(set(inv_single) - set(inv_batch)), sorted(set(inv_batch) - set(inv_single)))
    if not any(Path(r).suffix.lower() in identity.MRC_EXT for r in inv_batch):
        return "no %s MRC product in the batch" % stem
    for rel in inv_batch:
        a, b = Path(single) / rel, Path(batch) / rel
        if Path(rel).suffix.lower() in identity.MRC_EXT:
            diff = identity.compare_mrc(str(a), str(b))
        else:
            diff = None if identity.normalise(a.read_bytes(), str(single)) == \
                identity.normalise(b.read_bytes(), str(batch)) else "differs after root normalisation"
        if diff:
            return "%s: %s" % (rel, diff)
    return None


def selfcheck_per_movie_identical(work, failures):
    """The helper must see a missing STAR, a missing EPS and a changed STAR, not only a bad MRC."""
    def tree(name, files):
        root = work / name
        root.mkdir(parents=True)
        for rel, payload in files.items():
            (root / rel).write_bytes(payload)
        return root

    mrc = mrc_header(2) + bytes(range(16))
    full = {"good.mrc": mrc, "good.star": b"data_\n1\n", "good_shifts.eps": b"%!PS\n"}
    single = tree("self-single", full)
    check(per_movie_identical(single, tree("self-same", dict(full)), "good") is None,
          "self-check: identical per-movie trees compare identical", failures)
    for label, files in (("STAR missing from the batch", {k: v for k, v in full.items() if k != "good.star"}),
                         ("EPS missing from the batch", {k: v for k, v in full.items() if k != "good_shifts.eps"}),
                         ("STAR changed", {**full, "good.star": b"data_\n2\n"}),
                         ("extra product in the batch", {**full, "good_extra.star": b"x"})):
        diff = per_movie_identical(single, tree("self-" + label.replace(" ", "-"), files), "good")
        check(diff is not None, "self-check: %s is caught (%s)" % (label, diff), failures)
    diff = per_movie_identical(tree("self-missing-ref", {k: v for k, v in full.items() if k != "good.star"}),
                               tree("self-full-batch", dict(full)), "good")
    check(diff is not None, "self-check: STAR missing from the single-movie tree is caught (%s)" % diff, failures)


def check(cond, msg, failures):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--baseline-binary", type=Path, default=None,
                    help="unmodified build; valid products must be byte-identical to its")
    ap.add_argument("--gpu", type=int, default=None, help="CUDA build: run each route on this device")
    ap.add_argument("--ingest", default="auto,compact,float",
                    help="comma list of --ingest routes (only with --gpu)")
    ap.add_argument("--modes", default=",".join(map(str, MODES)))
    args = ap.parse_args()
    routes = args.ingest.split(",") if args.gpu is not None else [None]
    failures = []
    frames = make_frames()

    with tempfile.TemporaryDirectory(prefix="mc-trunc-mrc-") as tmp:
        work = Path(tmp)
        selfcheck_per_movie_identical(work, failures)
        for mode in [int(m) for m in args.modes.split(",")]:
            vs = variants(mode, frames)
            for route in routes:
                if route == "compact" and mode not in COMPACT_MODES:
                    continue
                tag = "mode %d%s" % (mode, " ingest=" + route if route else "")
                slug = "m%d-%s" % (mode, route or "cpu")
                expect_route = None
                if route == "float" or (route == "auto" and mode not in COMPACT_MODES):
                    expect_route = "float"
                elif route in ("compact", "auto"):
                    expect_route = "compact"

                rc, text, out_ok, wit = run(args.binary, work, slug + "-valid", {"movie.mrcs": vs["valid"][0]},
                                            args.gpu, route)
                check(rc == 0 and any(p.endswith(".mrc") for p in products(out_ok)),
                      "%s: valid movie exits 0 and publishes (rc=%d)" % (tag, rc), failures)
                if rc:
                    print(text[-1500:])
                    continue
                if expect_route:
                    check([l.split()[-1] for l in wit] == [expect_route],
                          "%s: valid movie took the %s route" % (tag, expect_route), failures)
                if args.baseline_binary:
                    rcb, textb, out_b, _ = run(args.baseline_binary, work, slug + "-valid-base",
                                               {"movie.mrcs": vs["valid"][0]}, args.gpu, route)
                    ident = identity.compare_trees(str(out_b), str(out_ok)) if rcb == 0 else None
                    check(ident is not None and ident["identical"],
                          "%s: valid products identical to the baseline build: %s"
                          % (tag, "baseline rc=%d" % rcb if ident is None else ident["problems"] or "no differences"),
                          failures)

                for name, (payload, bad_frame) in vs.items():
                    if bad_frame is None:
                        continue
                    rc, text, out, wit = run(args.binary, work, "%s-%s" % (slug, name),
                                             {"movie.mrcs": payload}, args.gpu, route)
                    want = MESSAGE % (bad_frame, "movie.mrcs")
                    check(rc > 0, "%s, %s: truncated movie fails the job (rc=%d)" % (tag, name, rc), failures)
                    check(want in text, "%s, %s: reports %r" % (tag, name, want), failures)
                    check(products(out) == [], "%s, %s: no MRC/STAR/EPS product published: %s"
                          % (tag, name, products(out) or "none"), failures)
                    if expect_route:
                        check([l.split()[-1] for l in wit] == [expect_route],
                              "%s, %s: failed on the %s route" % (tag, name, expect_route), failures)

                # One valid and one truncated movie, truncated listed first.
                batch_movies = {"bad.mrcs": vs["last-frame"][0], "good.mrcs": vs["valid"][0]}
                rc, text, out_b, wit = run(args.binary, work, slug + "-batch", batch_movies, args.gpu, route)
                got = products(out_b)
                check(rc > 0, "%s batch: job exits non-zero (rc=%d)" % (tag, rc), failures)
                check(any(p.endswith("good.mrc") for p in got) and not any("bad" in p for p in got),
                      "%s batch: good movie published, bad movie not: %s" % (tag, got), failures)
                check(not any(Path(p).name == "corrected_micrographs.star" for p in got),
                      "%s batch: joint STAR withheld" % tag, failures)
                # The valid movie's own run, named good.mrcs, is the reference.
                rc1, _, out_1, _ = run(args.binary, work, slug + "-good", {"good.mrcs": vs["valid"][0]},
                                       args.gpu, route)
                diff = per_movie_identical(out_1, out_b, "good") if rc1 == 0 else "reference run failed"
                check(diff is None, "%s batch: good movie products identical to its single run: %s"
                      % (tag, diff or "no differences"), failures)

    if failures:
        print("\n%d check(s) failed" % len(failures))
        return 1
    print("\nAll truncated MRC movie checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
