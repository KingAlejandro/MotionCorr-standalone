#!/usr/bin/env python3
"""Split a movies STAR into N chunks, preserving the optics/header prefix verbatim.

Deliberately mirrors tools/run_all_24_tutorial_benchmark.py:prepare_chunks so the
optics block, and therefore per-movie pixel size / voltage / pre-exposure, is
identical in every chunk. Round-robin, not contiguous: movie cost varies, and a
contiguous split would put any systematic ordering effect in one worker.
"""
import argparse, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--star", required=True); ap.add_argument("--n", type=int, required=True)
ap.add_argument("--outdir", required=True); ap.add_argument("--prefix", default="chunk")
a = ap.parse_args()

text = Path(a.star).read_text()
lines = text.splitlines(keepends=True)
movie_idx = [i for i, l in enumerate(lines) if "Movies/" in l and l.strip()]
if not movie_idx:
    sys.exit("no movie rows found (expected lines containing 'Movies/')")
first = movie_idx[0]
header = "".join(lines[:first])
rows = [lines[i] for i in movie_idx]
trailer = "".join(l for i, l in enumerate(lines[first:], start=first)
                  if i not in set(movie_idx) and l.strip())

out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
buckets = [[] for _ in range(a.n)]
for k, r in enumerate(rows):
    buckets[k % a.n].append(r)          # round-robin

written = []
for k, b in enumerate(buckets):
    if not b:
        sys.exit(f"chunk {k} empty: N={a.n} exceeds movie count {len(rows)}")
    p = out / f"{a.prefix}_{a.n}way_{k}.star"
    p.write_text(header + "".join(b) + trailer)
    written.append((str(p), len(b)))

total = sum(n for _, n in written)
if total != len(rows):
    sys.exit(f"partition lost rows: {total} != {len(rows)}")
for p, n in written:
    print(f"{p}\t{n}")
print(f"TOTAL\t{total}", file=sys.stderr)
