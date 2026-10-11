#!/usr/bin/env python3
"""Host buffer reuse must not change products (docs/host_buffer_reuse.md).

Reusing a full-frame buffer means it no longer starts as fresh, kernel-zeroed
pages. If any code read a buffer before writing it, products would then
depend on what the previous movie left behind.

Arms, all on a multi-movie batch so buffers really are reused across movies:
  nopool     MOTIONCORR_FRAME_POOL=0 (no pooling, glibc defaults)
  pool       the default build behaviour (bounded full-frame buffer pool)
  perturbed  pool plus MALLOC_PERTURB_ (fills fresh allocations with a pattern)
             and MOTIONCORR_FRAME_POOL_POISON=1 (fills every reused pool buffer
             with NaNs), so no read-before-write can hide
  thresholds the opt-in MOTIONCORR_MALLOC_REUSE=1 (glibc mmap/trim thresholds)
Plus a mixed-geometry batch in one process (512x512, 128x128, 512x512), so
reused buffers change shape between movies.

Products must be byte-identical across arms (MRC payload, header except the
label timestamp, and path-normalised STAR). On non-glibc platforms the arms
coincide; the test still runs, so it is a plain identity check there.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOVIE = ROOT / "test-data" / "synthetic" / "synthetic_movie.tiff"
OPTS = ["--use_own", "--j", "2", "--hotpixel_sigma", "2", "--angpix", "1", "--voltage", "300",
        "--patch_x", "3", "--patch_y", "3", "--bfactor", "150", "--dose_weighting",
        "--dose_per_frame", "1", "--save_noDW", "--skip_logfile"]
failures = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)


def write_star(path, movies):
    path.write_text(
        "# version 30001\n\ndata_optics\n\nloop_\n"
        "_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
        "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n"
        "_rlnSphericalAberration #5\n_rlnAmplitudeContrast #6\n"
        "opticsGroup1 1 1.000 300.0 2.7 0.1\n\n"
        "# version 30001\n\ndata_movies\n\nloop_\n"
        "_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n"
        + "".join(f"{m} 1\n" for m in movies))


def run(binary, star, out, env_extra, cwd):
    env = dict(os.environ)
    for k in ("MOTIONCORR_FRAME_POOL", "MOTIONCORR_FRAME_POOL_POISON", "MOTIONCORR_MALLOC_REUSE", "MALLOC_PERTURB_", "MALLOC_MMAP_THRESHOLD_",
              "MALLOC_TRIM_THRESHOLD_", "GLIBC_TUNABLES"):
        env.pop(k, None)
    env.update(env_extra)
    r = subprocess.run([binary, "--i", str(star), "--o", str(out) + "/"] + OPTS,
                       cwd=cwd, env=env, capture_output=True, text=True)
    return r


def compare(a, b, label):
    pa = sorted(p.relative_to(a) for p in a.rglob("*") if p.suffix in (".mrc", ".star"))
    pb = sorted(p.relative_to(b) for p in b.rglob("*") if p.suffix in (".mrc", ".star"))
    check(pa == pb and pa, f"{label}: same product inventory ({len(pa)} files)")
    diff = []
    for rel in pa:
        x, y = (a / rel).read_bytes(), (b / rel).read_bytes()
        if rel.suffix == ".mrc":
            same = x[1024:] == y[1024:] and x[:224] == y[:224]
        else:
            same = x.replace(str(a).encode(), b"X") == y.replace(str(b).encode(), b"X")
        if not same:
            diff.append(str(rel))
    check(not diff, f"{label}: byte-identical products" + (f" (differ: {diff[:4]})" if diff else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        movies = tmp / "movies"
        movies.mkdir()
        # Three same-geometry movies: distinct files, so each is processed.
        names = []
        for i in range(3):
            dst = movies / f"m{i}.tiff"
            shutil.copyfile(MOVIE, dst)
            names.append(f"movies/m{i}.tiff")
        same = tmp / "same.star"
        write_star(same, names)

        arms = {
            "nopool": {"MOTIONCORR_FRAME_POOL": "0"},
            "pool": {},
            "perturbed": {"MALLOC_PERTURB_": "165", "MOTIONCORR_FRAME_POOL_POISON": "1"},
            "thresholds": {"MOTIONCORR_MALLOC_REUSE": "1", "MALLOC_PERTURB_": "90"},
        }
        outs = {}
        for arm, env in arms.items():
            r = run(a.binary, same, tmp / f"out-{arm}", env, tmp)
            check(r.returncode == 0, f"{arm} run exits 0")
            if r.returncode:
                print(r.stderr[-1500:])
                return 1
            outs[arm] = tmp / f"out-{arm}"
            if arm == "nopool":
                check("frame pool disabled" in r.stdout and "buffers pooled" not in r.stdout,
                      "disabled pool reported accurately")
            if arm == "pool":
                check("Host allocator:" in r.stdout and "pooled" in r.stdout,
                      "default allocator mode reported (glibc defaults, pooled buffers)")
        compare(outs["nopool"], outs["pool"], "no pool vs pool")
        compare(outs["nopool"], outs["perturbed"], "no pool vs pool+MALLOC_PERTURB_")
        compare(outs["nopool"], outs["thresholds"], "no pool vs opt-in thresholds+MALLOC_PERTURB_")

        # Mixed geometry within one process: two different-size movies alternate
        # (512x512 TIFF, 128x128 MRC, 512x512 TIFF), so reused buffers change shape
        # between movies. Compared defaults vs reuse+perturb.
        shutil.copyfile(ROOT / "test-data" / "synthetic" / "synthetic_fallback.mrc", movies / "small.mrc")
        mixed = tmp / "mixed.star"
        write_star(mixed, [names[0], "movies/small.mrc", names[1]])
        mixed_out = {}
        for arm, env in (("defaults", {"MOTIONCORR_FRAME_POOL": "0"}),
                         ("perturbed", {"MALLOC_PERTURB_": "90", "MOTIONCORR_FRAME_POOL_POISON": "1"})):
            r = run(a.binary, mixed, tmp / f"mixed-{arm}", env, tmp)
            check(r.returncode == 0, f"mixed-geometry {arm} run exits 0")
            if r.returncode:
                print(r.stderr[-1500:])
            mixed_out[arm] = tmp / f"mixed-{arm}"
        compare(mixed_out["defaults"], mixed_out["perturbed"], "mixed geometry defaults vs reuse+perturbed")

        # User malloc settings must be left alone.
        r = run(a.binary, same, tmp / "user", {"MALLOC_MMAP_THRESHOLD_": "1048576",
                                                "MOTIONCORR_MALLOC_REUSE": "1"}, tmp)
        check(r.returncode == 0 and ("user malloc settings kept" in r.stdout
                                     or "platform allocator defaults" in r.stdout),
              "user-provided malloc settings are not overridden by the opt-in")
    print("PASS" if not failures else f"{len(failures)} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
