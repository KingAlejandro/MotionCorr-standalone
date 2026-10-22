#!/usr/bin/env python3
"""Issue 61 Stage B2: emit the post-processing job list (identical settings per arm)."""
import os, glob
ROOT = "/home/alex/mc-issue61"
BIN = "/home/alex/relion-container-tests/bin/relion-container-bin-r2"
jobs = []
for h1 in sorted(glob.glob(f"{ROOT}/rec/*/*_half1_class001_unfil.mrc")):
    arm = h1.split("/rec/")[1].split("/")[0]
    name = os.path.basename(h1).replace("_half1_class001_unfil.mrc", "")
    h2 = h1.replace("half1", "half2")
    if not os.path.exists(h2):
        print("MISSING half2 for", h1)
        continue
    out = f"{ROOT}/pp/{arm}/{name}"
    jobs.append(
        f"cd {ROOT}/proj/{arm} && {BIN}/relion_postprocess --i {h1} --o {out} "
        f"--mask MaskCreate/job020/mask.mrc --angpix 1.244531 "
        f"--mtf mtf_k2_200kV.star --mtf_angpix 0.885 --auto_bfac --autob_lowres 10 "
        f"> {ROOT}/logs/pp_{arm}_{name}.log 2>&1")
open(f"{ROOT}/jobs_postprocess.txt", "w").write("\n".join(jobs) + "\n")
print("postprocess jobs:", len(jobs))
