#!/usr/bin/env python3
"""Stand-in for the motioncorr binary in kit tests (no GPU, no MotionCorr build).

Accepts --i STAR --o OUT [--profile FILE] plus ignored options, and writes the
same product layout as MotionCorr: per-movie MRC (with a timestamp in the
label block), STAR and shifts EPS that embed the output path, a timing log,
a PDF with a creation date and a joint STAR. Behaviour from the environment:

  FAKE_SLEEP    seconds of work per run (spread over movies), default 0.05
  FAKE_EXTRA    extra seconds per movie inside the "fit polynomial" stage
  FAKE_VARIANT  changes the MRC payload (a product difference)
  FAKE_FAIL     exit 3 without products
"""
import hashlib
import json
import os
import struct
import sys
import time


def opt(args, name):
    return args[args.index(name) + 1] if name in args else None


def main():
    args = sys.argv[1:]
    if os.environ.get("FAKE_FAIL"):
        return 3
    star, out, prof = opt(args, "--i"), opt(args, "--o"), opt(args, "--profile")
    movies = [l.split()[0] for l in open(star) if l.strip().startswith("Movies/")]
    sleep = float(os.environ.get("FAKE_SLEEP", "0.05"))
    extra = float(os.environ.get("FAKE_EXTRA", "0"))
    variant = os.environ.get("FAKE_VARIANT", "")
    t_run = time.monotonic()
    records = []
    joint = []
    for i, m in enumerate(movies):
        t0 = time.monotonic()
        stem = os.path.splitext(m)[0]
        base = os.path.join(out, stem)
        os.makedirs(os.path.dirname(base), exist_ok=True)
        time.sleep(sleep / len(movies) / 2)
        t1 = time.monotonic()
        time.sleep(extra)
        t2 = time.monotonic()
        hdr = bytearray(1024)
        struct.pack_into("<3i", hdr, 0, 4, 4, 1)
        struct.pack_into("<i", hdr, 12, 2)
        hdr[208:212] = b"MAP "
        label = ("Relion    %s" % time.strftime("%d-%b-%y  %H:%M:%S")).encode()
        hdr[224:224 + len(label)] = label
        payload = hashlib.sha256((m + variant).encode()).digest() * 2
        with open(base + ".mrc", "wb") as f:
            f.write(bytes(hdr) + payload)
        with open(base + ".star", "w") as f:
            f.write("data_general\n_rlnImageSizeX 4\n_rlnMicrographMovieName %s\n# out %s\n" % (m, out))
        with open(base + "_shifts.eps", "w") as f:
            f.write("%%!PS-Adobe-2.0 EPSF\n%%%%Title: %s_shifts.eps\n" % base)
        time.sleep(sleep / len(movies) / 2)
        t3 = time.monotonic()
        with open(base + ".log", "w") as f:
            f.write("Full movie wall time: %.3f s\n" % (t3 - t0))
        joint.append(base + ".mrc")
        records.append({"type": "movie", "index": i, "name": m, "ok": True, "wall_ms": (t3 - t0) * 1e3,
                        "cpu_ms": 0.1, "minflt": 1, "majflt": 0, "vcsw": 0, "ivcsw": 0,
                        "stages": [{"name": "setup", "n": 1, "wall_ms": (t1 - t0) * 1e3, "cpu_ms": 0.0,
                                    "minflt": 1, "majflt": 0, "vcsw": 0, "ivcsw": 0},
                                   {"name": "fit polynomial", "n": 1, "wall_ms": (t2 - t1) * 1e3, "cpu_ms": 0.0,
                                    "minflt": 0, "majflt": 0, "vcsw": 0, "ivcsw": 0},
                                   {"name": "movie teardown", "n": 1, "wall_ms": (t3 - t2) * 1e3, "cpu_ms": 0.0,
                                    "minflt": 0, "majflt": 0, "vcsw": 0, "ivcsw": 0}],
                        "sub": []})
    with open(os.path.join(out, "corrected_micrographs.star"), "w") as f:
        f.write("data_micrographs\nloop_\n_rlnMicrographName #1\n" + "\n".join(joint) + "\n")
    with open(os.path.join(out, "logfile.pdf"), "w") as f:
        f.write("%%PDF-1.4 /CreationDate (D:%d)\n" % time.time_ns())
    if prof:
        with open(prof, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
            f.write(json.dumps({"type": "process", "movies": len(movies),
                                "run_wall_ms": (time.monotonic() - t_run) * 1e3, "main_cpu_ms": 1.0,
                                "process_cpu_ms": 1.0, "process_minflt": 1, "process_majflt": 0,
                                "peak_rss_kb": 1000, "threads": []}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
