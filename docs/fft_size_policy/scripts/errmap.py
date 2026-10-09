#!/usr/bin/env python3
"""Where does TEST differ from REF? Per movie and sum (DW, noDW): RMSE of the
difference in border bands and the interior, relative to the REF sum's
standard deviation, plus a block-averaged |difference| map of one movie as
PGM (docs/fft_size_policy.md).

  errmap.py REF_DIR TEST_DIR --json-out OUT [--map-movie NAME --map-out PGM]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
from compare_motioncorr import parse_mrc  # noqa: E402

BANDS = ((0, 8), (8, 32), (32, 128), (128, None))  # distance from the nearest edge, px


def load(path):
    h, p, _ = parse_mrc(path)
    return p.astype(np.float64).reshape(h["ny"], h["nx"])


def localise(a, b):
    d = b - a
    ny, nx = a.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    edge = np.minimum(np.minimum(xx, nx - 1 - xx), np.minimum(yy, ny - 1 - yy))
    sd = a.std()
    out = {"whole": float(np.sqrt((d ** 2).mean()) / sd)}
    for lo, hi in BANDS:
        m = (edge >= lo) if hi is None else (edge >= lo) & (edge < hi)
        key = f"edge_{lo}_{hi if hi is not None else 'inf'}"
        out[key] = float(np.sqrt((d[m] ** 2).mean()) / sd)
        out[key + "_sq_share"] = float((d[m] ** 2).sum() / (d ** 2).sum())
    return out


def write_pgm(d, path, block=8):
    ny, nx = (s // block * block for s in d.shape)
    m = np.abs(d[:ny, :nx]).reshape(ny // block, block, nx // block, block).mean((1, 3))
    m = np.clip(m / np.percentile(m, 99.5) * 255, 0, 255).astype(np.uint8)
    Path(path).write_bytes(b"P5 %d %d 255\n" % (m.shape[1], m.shape[0]) + m.tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref", type=Path)
    ap.add_argument("test", type=Path)
    ap.add_argument("--json-out", type=Path, required=True)
    ap.add_argument("--map-movie")
    ap.add_argument("--map-out", type=Path)
    args = ap.parse_args()
    rows = []
    for rm in sorted((args.ref / "Movies").glob("*.mrc")):
        tm = args.test / "Movies" / rm.name
        if not tm.exists():
            continue
        a, b = load(rm), load(tm)
        kind = "nodw" if rm.stem.endswith("_noDW") else "dw"
        rows.append({"movie": rm.stem.replace("_noDW", ""), "kind": kind, **localise(a, b)})
        if args.map_movie and kind == "dw" and rm.stem == args.map_movie:
            write_pgm(b - a, args.map_out)
    args.json_out.write_text(json.dumps(rows, indent=1))
    keys = [k for k in rows[0] if k.startswith("edge_") or k == "whole"]
    for kind in ("dw", "nodw"):
        rs = [r for r in rows if r["kind"] == kind]
        if rs:
            print(f"{kind} median over {len(rs)}: " +
                  " ".join(f"{k} {np.median([r[k] for r in rs]):.4g}" for k in keys))


if __name__ == "__main__":
    main()
