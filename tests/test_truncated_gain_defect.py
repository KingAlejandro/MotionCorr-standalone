#!/usr/bin/env python3
"""A truncated raw MRC gain reference or defect map must fail, not be applied (RC0 F3b).

Image<T>::read reports a short raw MRC only through a negative return. The
gain and defect-map reads dropped it, and the size check that follows looks at
header dimensions only, so a truncated gain was multiplied into every movie
(and a truncated defect map masked from unread memory) with exit 0.

A valid synthetic movie (MRC mode 1, integer, and mode 2, float) is run with:
  * --gainref                 (gainReferenceFor),
  * --gainref + --gain_rot 1  (prepareGainReference, which reads before any movie),
  * --defect_file <image>     (fillDefectMask),
each valid and truncated three ways (mid-image, last four bytes missing,
header only). Checked per route (--gpu: every --ingest route that admits the movie):

  * the valid file exits 0 and publishes; with --baseline-binary (an unmodified
    build) its output tree is byte-identical to the baseline's;
  * each truncated file exits non-zero without a signal, names the file in one
    message, and leaves no MRC, STAR or EPS product;
  * two movies sharing one truncated gain both fail, and the job with them.

With --eer-movie and --eer-gain (a Falcon .gain TIFF; EMPIAR-12963 on the
validation host) the same is done through EERRenderer::loadEERGain, on a raw
MRC copy of the gain made here. Without them that section is reported as skipped.

The truncated cases must fail on a build without the fix.
"""
import argparse
import os
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_truncated_mrc_movie as base  # noqa: E402

identity = base.identity
NX = NY = base.NX
GAIN_MSG = "Failed to read the gain reference %s: the file is truncated or unreadable."
DEFECT_MSG = "Failed to read the defect map %s: the file is truncated or unreadable."


def image_mrc(values, nx, ny):
    """Single-image float32 MRC (mode 2)."""
    h = bytearray(base.HEADER)
    struct.pack_into("<4i", h, 0, nx, ny, 1, 2)
    struct.pack_into("<3i", h, 28, nx, ny, 1)
    struct.pack_into("<3f", h, 40, float(nx), float(ny), 1.0)
    struct.pack_into("<3f", h, 52, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", h, 64, 1, 2, 3)
    struct.pack_into("<3f", h, 76, min(values), max(values), sum(values) / len(values))
    h[208:212] = b"MAP "
    h[212:216] = bytes((0x44, 0x41, 0, 0))
    return bytes(h) + struct.pack("<%df" % len(values), *values)


def gain_values():
    return [1.0 + 0.05 * (((x * 7 + y * 13) % 11) - 5) / 5.0 for y in range(NY) for x in range(NX)]


def defect_values():
    return [1.0 if 40 <= y < 43 and 60 <= x < 63 else 0.0 for y in range(NY) for x in range(NX)]


def truncations(full):
    """name -> bytes; the valid file is not listed."""
    return {
        "mid-image": full[:base.HEADER + (len(full) - base.HEADER) // 2],
        "tail-short": full[:-4],
        "header-only": full[:base.HEADER],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--baseline-binary", type=Path, default=None)
    ap.add_argument("--gpu", type=int, default=None)
    ap.add_argument("--ingest", default="auto,compact,float", help="comma list (only with --gpu)")
    ap.add_argument("--movie-modes", default="1,2")
    ap.add_argument("--eer-movie", type=Path, default=None)
    ap.add_argument("--eer-gain", type=Path, default=None, help="Falcon .gain TIFF matching --eer-movie")
    ap.add_argument("--eer-work", type=Path, default=None, help="scratch dir for the EER section")
    args = ap.parse_args()
    failures = []
    check = base.check
    frames = base.make_frames()
    gain_full = image_mrc(gain_values(), NX, NY)
    defect_full = image_mrc(defect_values(), NX, NY)
    scenarios = [  # name, file written, valid bytes, extra args, message
        ("gain", "gain.mrc", gain_full, ["--gainref", "gain.mrc"], GAIN_MSG % "gain.mrc"),
        ("gain-rot1", "gain.mrc", gain_full, ["--gainref", "gain.mrc", "--gain_rot", "1"], GAIN_MSG % "gain.mrc"),
        ("defect", "defect.mrc", defect_full, ["--defect_file", "defect.mrc"], DEFECT_MSG % "defect.mrc"),
    ]

    with tempfile.TemporaryDirectory(prefix="mc-trunc-gain-") as tmp:
        work = Path(tmp)
        for mode in [int(m) for m in args.movie_modes.split(",")]:
            movie = base.variants(mode, frames)["valid"][0]
            routes = args.ingest.split(",") if args.gpu is not None else [None]
            for route in routes:
                if route == "compact" and mode not in base.COMPACT_MODES:
                    continue
                for sname, fname, valid, extra, want in scenarios:
                    tag = "mode %d%s, %s" % (mode, " ingest=" + route if route else "", sname)
                    slug = "m%d-%s-%s" % (mode, route or "cpu", sname)
                    rc, text, out_ok, _ = base.run(args.binary, work, slug + "-valid", {"movie.mrcs": movie},
                                                   args.gpu, route, {fname: valid}, extra)
                    check(rc == 0 and any(p.endswith(".mrc") for p in base.products(out_ok)),
                          "%s: valid file exits 0 and publishes (rc=%d)" % (tag, rc), failures)
                    if rc:
                        print(text[-1500:])
                        continue
                    if args.baseline_binary:
                        rcb, _, out_b, _ = base.run(args.baseline_binary, work, slug + "-valid-base",
                                                    {"movie.mrcs": movie}, args.gpu, route, {fname: valid}, extra)
                        ident = identity.compare_trees(str(out_b), str(out_ok)) if rcb == 0 else None
                        check(ident is not None and ident["identical"],
                              "%s: valid products identical to the baseline build: %s"
                              % (tag, "baseline rc=%d" % rcb if ident is None else ident["problems"] or "no differences"),
                              failures)
                    for tname, payload in truncations(valid).items():
                        rc, text, out, _ = base.run(args.binary, work, "%s-%s" % (slug, tname),
                                                    {"movie.mrcs": movie}, args.gpu, route, {fname: payload}, extra)
                        check(rc > 0, "%s, %s: job fails (rc=%d)" % (tag, tname, rc), failures)
                        check(want in text, "%s, %s: reports %r" % (tag, tname, want), failures)
                        check(base.products(out) == [], "%s, %s: no MRC/STAR/EPS product published: %s"
                              % (tag, tname, base.products(out) or "none"), failures)

                    if sname != "gain-rot1":
                        # A bad gain or defect map is read for every movie: both fail, and the job.
                        two = {"a.mrcs": movie, "b.mrcs": movie}
                        rc, text, out, _ = base.run(args.binary, work, slug + "-two", two, args.gpu, route,
                                                    {fname: truncations(valid)["mid-image"]}, extra)
                        check(rc > 0 and base.products(out) == [] and want in text,
                              "%s, two movies: job fails and publishes nothing (rc=%d, products %s)"
                              % (tag, rc, base.products(out) or "none"), failures)

        failures += eer_section(args, work)

    if failures:
        print("\n%d check(s) failed" % len(failures))
        return 1
    print("\nAll truncated gain/defect checks passed")
    return 0


def eer_section(args, work):
    failures = []
    if not (args.eer_movie and args.eer_gain):
        print("SKIP EER gain section: --eer-movie/--eer-gain not given")
        return failures
    try:
        from PIL import Image
    except ImportError:
        base.check(False, "EER gain section NOT RUN: Pillow is required for the supplied EER inputs", failures)
        return failures
    import numpy as np

    scratch = args.eer_work or work
    scratch.mkdir(parents=True, exist_ok=True)
    gain = np.array(Image.open(args.eer_gain), dtype="<f4")
    ny, nx = gain.shape
    full = image_mrc(gain.ravel().tolist(), nx, ny)
    base_extra = ["--eer_grouping", "49", "--eer_upsampling", "1", "--expected_frames", "39",
                  "--dose_per_frame", "1.282051"]
    star = base.STAR_HEAD.replace("1.000 300.0", "0.970 300.0") + "Movies/movie.eer 1\n"

    def run_eer(binary, label, gain_name, gain_payload=None, gain_link=None):
        d = scratch / label
        if d.exists():
            import shutil
            shutil.rmtree(d)
        (d / "Movies").mkdir(parents=True)
        out = d / "out"
        out.mkdir()
        os.symlink(Path(args.eer_movie).resolve(), d / "Movies" / "movie.eer")
        if gain_link:
            os.symlink(Path(gain_link).resolve(), d / gain_name)
        else:
            (d / gain_name).write_bytes(gain_payload)
        (d / "movies.star").write_text(star)
        import subprocess
        cmd = [str(Path(binary).resolve()), "--i", "movies.star", "--o", str(out) + "/", "--use_own",
               "--dose_weighting", "--bfactor", "150", "--seed", "1", "--j", "8", *base_extra,
               "--gainref", gain_name]
        if args.gpu is not None:
            cmd += ["--gpu", str(args.gpu), "--ingest", "auto"]
        res = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
        return res.returncode, res.stdout + res.stderr, out

    arms = [("tiff", "gain.gain", None, args.eer_gain), ("mrc", "gain.mrc", full, None)]
    for aname, gname, payload, link in arms:
        rc, text, out = run_eer(args.binary, "eer-%s-valid" % aname, gname, payload, link)
        base.check(rc == 0 and any(p.endswith(".mrc") for p in base.products(out)),
                   "EER %s gain: valid exits 0 and publishes (rc=%d)" % (aname, rc), failures)
        if rc:
            print(text[-1500:])
            continue
        if args.baseline_binary:
            rcb, _, out_b = run_eer(args.baseline_binary, "eer-%s-valid-base" % aname, gname, payload, link)
            ident = identity.compare_trees(str(out_b), str(out)) if rcb == 0 else None
            base.check(ident is not None and ident["identical"],
                       "EER %s gain: valid products identical to the baseline build: %s"
                       % (aname, "baseline rc=%d" % rcb if ident is None else ident["problems"] or "no differences"),
                       failures)
        for f in out.rglob("*.mrc"):  # bulk products are not needed after comparison
            f.unlink()
        if args.baseline_binary:
            for f in out_b.rglob("*.mrc"):
                f.unlink()
    for tname, payload in truncations(full).items():
        rc, text, out = run_eer(args.binary, "eer-mrc-%s" % tname, "gain.mrc", payload)
        want = GAIN_MSG % "gain.mrc"
        base.check(rc > 0, "EER mrc gain, %s: job fails (rc=%d)" % (tname, rc), failures)
        base.check(want in text, "EER mrc gain, %s: reports %r" % (tname, want), failures)
        base.check(base.products(out) == [], "EER mrc gain, %s: no MRC/STAR/EPS product published: %s"
                   % (tname, base.products(out) or "none"), failures)
    return failures


if __name__ == "__main__":
    sys.exit(main())
