#!/usr/bin/env python3
"""Merge N worker output dirs into one tree for Gate C comparison.

Fails closed on any duplicate relative path: two workers producing the same
output file would mean the partition was not disjoint, which is exactly the
scheduling bug this gate exists to catch. Copies rather than links so the
comparison reads real bytes.
"""
import argparse, re, shutil, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--workers", nargs="+", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--expect", type=int, default=24)
a = ap.parse_args()

out = Path(a.out)
if out.exists():
    sys.exit(f"refusing to overwrite existing merge dir: {out}")
out.mkdir(parents=True)

seen, conflicts = {}, []
for w in a.workers:
    wp = Path(w)
    for f in wp.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(wp)
        # per-run aggregate artifacts are expected in every worker dir; skip them
        if rel.name in ("corrected_micrographs.star", "logfile.pdf", "header.pdf",
                        "batch.pdf", "all_batches.pdf", "run.log", "time.txt") \
           or rel.name.endswith(".lst") or rel.name.startswith("corrected_micrographs_") \
           or re.fullmatch(r"run\d*\.log", rel.name) or rel.name == "foreign.txt":
            continue
        if rel in seen:
            conflicts.append((str(rel), seen[rel], w))
            continue
        seen[rel] = w
        d = out / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, d)

if conflicts:
    print(f"FAIL: {len(conflicts)} duplicate output paths across workers (partition not disjoint)")
    for r, a_, b_ in conflicts[:10]:
        print(f"  {r}: {a_} and {b_}")
    sys.exit(2)

mrcs = [p for p in out.rglob("*.mrc")
        if not p.name.endswith(("_PS.mrc", "_EVN.mrc", "_ODD.mrc", "_noDW.mrc"))
        and p.name != "gain.mrc"]
print(f"merged {len(seen)} files into {out}; corrected MRCs = {len(mrcs)}")
if len(mrcs) != a.expect:
    print(f"FAIL: expected {a.expect} corrected MRCs, found {len(mrcs)}")
    sys.exit(3)
print("merge OK")
