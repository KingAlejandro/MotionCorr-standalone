#!/usr/bin/env python3
"""Generate the input-format matrix from real tutorial movies.

One decode per source movie; every variant is written from the same in-memory
sample array, so all variants of a movie hold identical sample values.  uint8
variants are refused unless every sample already fits in a byte.
"""
import os, sys, time, json
import numpy as np, tifffile

SRC_DIR = "/home/alex/MotionCorr-standalone/relion30_tutorial/Movies"
OUT = sys.argv[1]
MOVIES = sys.argv[2].split(",")
VARIANTS = sys.argv[3].split(",")   # name:dtype:comp:rps[:pred][:repeat]

COMP = {"deflate": "zlib", "lzw": "lzw", "raw": None, "packbits": "packbits"}

def parse(v):
    p = v.split(":")
    return dict(name=p[0], dtype=p[1], comp=p[2], rps=int(p[3]),
                pred=bool(int(p[4])) if len(p) > 4 else False,
                repeat=int(p[5]) if len(p) > 5 else 1)

specs = [parse(v) for v in VARIANTS]
for s in specs:
    os.makedirs(os.path.join(OUT, s["name"], "Movies"), exist_ok=True)

report = []
for m in MOVIES:
    src = os.path.join(SRC_DIR, m)
    t0 = time.time()
    with tifffile.TiffFile(src) as tf:
        movie = np.stack([p.asarray() for p in tf.pages])
    t_read = time.time() - t0
    smax = int(movie.max())
    for s in specs:
        dst = os.path.join(OUT, s["name"], "Movies", m)
        if os.path.exists(dst):
            report.append(dict(movie=m, variant=s["name"], bytes=os.path.getsize(dst), skipped=True))
            continue
        data = movie
        if s["repeat"] > 1:
            data = np.concatenate([data] * s["repeat"], axis=0)
        if s["dtype"] == "uint8":
            if smax > 255:
                raise SystemExit(f"{m}: max sample {smax} does not fit uint8")
            data = data.astype(np.uint8)
        else:
            data = data.astype(s["dtype"])
        t1 = time.time()
        with tifffile.TiffWriter(dst) as tw:
            for f in range(data.shape[0]):
                tw.write(data[f], photometric="minisblack", compression=COMP[s["comp"]],
                         predictor=s["pred"], rowsperstrip=s["rps"], contiguous=False)
        report.append(dict(movie=m, variant=s["name"], frames=int(data.shape[0]),
                           bytes=os.path.getsize(dst), write_s=round(time.time()-t1, 2),
                           sample_max=smax, skipped=False))
        print(report[-1], flush=True)
    print(f"# {m} decoded in {t_read:.1f}s max={smax}", flush=True)

with open(os.path.join(OUT, "generation_report.json"), "a") as fh:
    json.dump(report, fh, indent=1)
