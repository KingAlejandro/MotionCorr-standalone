#!/usr/bin/env python3
"""S1.3c part 2: CUDA patch inputs with the global C2R projection and CPU's
global trajectory injected, against CPU's own (iteration 1, CCF window).

  part2.py <fam> <out.json>        (scratch root)
Compares <fam>-p5-d2-cpu-own (S1.3b) with <fam>-p5-d4-cuda-injcpu-herm, and, for
reference, with <fam>-p5-d2-cuda-injcpu (S1.3b, same trajectory, no projection).
"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import analyze as A, pairs as P


def main(fam, out):
    res = {}
    for name, lb in (("projection_on", f"{fam}-p5-d4-cuda-injcpu-herm"), ("projection_off_S1.3b", f"{fam}-p5-d2-cuda-injcpu")):
        rel, col0 = [], []
        for iy in range(1, 6):
            for ix in range(1, 6):
                a = P.inputs(f"{fam}-p5-d2-cpu-own", "cpu", iy, ix)
                b = P.inputs(lb, "cuda-batched", iy, ix)
                d = b - a
                for f in range(a.shape[0]):
                    rel.append(float(np.linalg.norm(d[f]) / np.linalg.norm(a[f])))
                    e = np.abs(d[f]) ** 2
                    col0.append(float(e[:, 0].sum() / e.sum()) if e.sum() > 0 else 0.0)
        res[name] = {"n_patch_frames": len(rel), "rel_median": float(np.median(rel)), "rel_max": float(max(rel)),
                     "kx0_share_median": float(np.median(col0))}
        print(fam, name, json.dumps(res[name]))
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
