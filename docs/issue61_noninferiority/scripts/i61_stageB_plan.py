#!/usr/bin/env python3
"""Issue 61 Stage B: build matched particle subsets and emit the job list.

Subsets are defined purely by movie id, so the particle membership of every
subset is byte-identical across arms.
"""
import os, sys, json

ROOT = "/home/alex/mc-issue61"
BIN = "/home/alex/relion-container-tests/bin/relion-container-bin-r2"
REAL = ["cpu", "default", "allfftw"]
CTRL = ["ctrl_noise_f005", "ctrl_noise_f020", "ctrl_envelope_b20"]
ALL = REAL + CTRL
DEV = ["00021", "00046"]


def read_star(path):
    """Return (preamble_lines, header_lines, colnames, rows) for data_particles."""
    lines = open(path).read().splitlines()
    i = lines.index("data_particles")
    pre = lines[:i]
    j = i
    while not lines[j].startswith("loop_"):
        j += 1
    k = j + 1
    cols = []
    while lines[k].strip().startswith("_rln"):
        cols.append(lines[k].strip().split()[0])
        k += 1
    rows = [l for l in lines[k:] if l.strip()]
    return pre, lines[i:k], cols, rows


def mid_of(row, mic_idx):
    return row.split()[mic_idx].split("_")[-2]


plan = []
subsets = {}
for arm in ALL:
    p = f"{ROOT}/proj/{arm}/Extract61/particles.star"
    pre, hdr, cols, rows = read_star(p)
    mic = cols.index("_rlnMicrographName")
    mids = sorted({mid_of(r, mic) for r in rows})
    held = [m for m in mids if m not in DEV]
    assert len(mids) == 24 and len(held) == 22, (len(mids), len(held))
    sets = {"all24": mids, "held22": held}
    if arm in REAL:
        for m in held:
            sets[f"jk_{m}"] = [x for x in held if x != m]
    outdir = f"{ROOT}/stars/{arm}"
    os.makedirs(outdir, exist_ok=True)
    for name, keep in sets.items():
        ks = set(keep)
        sel = [r for r in rows if mid_of(r, mic) in ks]
        with open(f"{outdir}/{name}.star", "w") as fh:
            fh.write("\n".join(pre + hdr + sel) + "\n")
        subsets.setdefault(arm, {})[name] = len(sel)
    os.makedirs(f"{ROOT}/rec/{arm}", exist_ok=True)
    os.makedirs(f"{ROOT}/pp/{arm}", exist_ok=True)
    for name in sets:
        for h in (1, 2):
            out = f"{ROOT}/rec/{arm}/{name}_half{h}_class001_unfil.mrc"
            plan.append(
                f"{BIN}/relion_reconstruct --i {outdir}/{name}.star "
                f"--o {out} --ctf --sym D2 --subset {h} --pad 2 "
                f"> {ROOT}/logs/rec_{arm}_{name}_h{h}.log 2>&1")

with open(f"{ROOT}/jobs_reconstruct.txt", "w") as fh:
    fh.write("\n".join(plan) + "\n")
json.dump(subsets, open(f"{ROOT}/results/subset_sizes.json", "w"), indent=1, sort_keys=True)
print("reconstruct jobs:", len(plan))
print("cpu subset sizes:", {k: v for k, v in list(subsets["cpu"].items())[:3]})
sz = {a: subsets[a]["held22"] for a in ALL}
print("held22 particle counts identical across arms:", len(set(sz.values())) == 1, sz["cpu"])
print("all24:", subsets["cpu"]["all24"])
