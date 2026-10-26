#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native local[g] (= obs[g] - obs[0] from retained STAR) versus known residual L*[g]."""
import json, sys
from pathlib import Path
import numpy as np
R275, SRC, OUT = (Path(a) for a in sys.argv[1:4])
sys.dont_write_bytecode = True
sys.path[:0] = [str(SRC / "tools")]
from motion_field import read_motion_star
NX, NY, NF = 128, 96, 5
A1 = np.array([[0.012, -0.008], [0.006, -0.010]]); G1 = np.array([3.25, -2.125]); C = np.array([NX, NY]) / 2
truth = lambda f, p: -(G1 * f / 4 + (np.asarray(p, float) - C) @ (A1 * f / 4).T)
res = {}
for b in ("cpu", "cuda"):
    base = R275 / f"runs/{b}-affine-on"
    g = np.array([[float(t) for t in l.split()[1:]] for l in (base / "state/global.txt").read_text().splitlines()])
    rows = read_motion_star(base / "out/affine.star").local_shifts
    by = {}
    for s in rows:
        by.setdefault((s["rlnCoordinateX"], s["rlnCoordinateY"]), {})[int(s["rlnMicrographFrameNumber"]) - 1] = (s["rlnMicrographShiftX"], s["rlnMicrographShiftY"])
    nat, ide, per = [], [], {}
    for c, d in sorted(by.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        o = np.array([d[f] for f in range(NF)])
        local = o - o[0]                               # obs[g] - obs[0] = local[g] - local[0]
        Ls = np.array([truth(f, c) - g[f] for f in range(NF)])
        nat.append(local[1:]); ide.append(Ls[1:])
        e = np.linalg.norm(local[1:] - Ls[1:], axis=1)
        per[f"({int(c[1]) // 32 + 1},{int(c[0]) // 42 + 1})"] = dict(
            local_err_norm_px_frames1to4=[round(float(x), 3) for x in e],
            native_local=[[round(float(v), 4) for v in r] for r in local[1:]],
            known_local=[[round(float(v), 4) for v in r] for r in Ls[1:]])
    nat = np.concatenate(nat); ide = np.concatenate(ide)
    k = [float(np.dot(nat[:, a], ide[:, a]) / np.dot(ide[:, a], ide[:, a])) for a in (0, 1)]
    r = [float(np.corrcoef(nat[:, a], ide[:, a])[0, 1]) for a in (0, 1)]
    res[b] = dict(slope_native_on_known_xy=[round(x, 4) for x in k], corr_xy=[round(x, 4) for x in r],
                  rms_known_px=round(float(np.sqrt((ide ** 2).sum(1).mean())), 4),
                  rms_native_px=round(float(np.sqrt((nat ** 2).sum(1).mean())), 4),
                  rms_err_px=round(float(np.sqrt(((nat - ide) ** 2).sum(1).mean())), 4), patches=per)
OUT.write_text(json.dumps(res, indent=1) + "\n")
for b, v in res.items():
    print(b, {k: v[k] for k in v if k != "patches"})
    for p, d in v["patches"].items():
        print("  ", p, d["local_err_norm_px_frames1to4"])
