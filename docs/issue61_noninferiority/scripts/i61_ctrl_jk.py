#!/usr/bin/env python3
"""Add delete-one-movie jackknife subsets for the two controls that the
protocol's validity precondition refers to, so each control gets an interval
rather than a bare point estimate."""
import os, sys
sys.path.insert(0, "/home/alex/mc-issue61/scripts")
ROOT = "/home/alex/mc-issue61"
BIN = "/home/alex/relion-container-tests/bin/relion-container-bin-r2"
ARMS = ["ctrl_noise_f005", "ctrl_envelope_b20"]
DEV = ["00021", "00046"]


def read_star(path):
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
    return pre, lines[i:k], cols, [l for l in lines[k:] if l.strip()]


jobs = []
for arm in ARMS:
    pre, hdr, cols, rows = read_star(f"{ROOT}/proj/{arm}/Extract61/particles.star")
    mic = cols.index("_rlnMicrographName")
    mids = sorted({r.split()[mic].split("_")[-2] for r in rows})
    held = [m for m in mids if m not in DEV]
    for m in held:
        ks = set(held) - {m}
        sel = [r for r in rows if r.split()[mic].split("_")[-2] in ks]
        sp = f"{ROOT}/stars/{arm}/jk_{m}.star"
        open(sp, "w").write("\n".join(pre + hdr + sel) + "\n")
        for h in (1, 2):
            out = f"{ROOT}/rec/{arm}/jk_{m}_half{h}_class001_unfil.mrc"
            jobs.append(f"cd {ROOT}/proj/{arm} && {BIN}/relion_reconstruct "
                        f"--i {sp} --o {out} --ctf --sym D2 --subset {h} --pad 2 "
                        f"> {ROOT}/logs/rec_{arm}_jk_{m}_h{h}.log 2>&1")
open(f"{ROOT}/jobs_reconstruct_ctrl.txt", "w").write("\n".join(jobs) + "\n")
print("control jackknife jobs:", len(jobs))
