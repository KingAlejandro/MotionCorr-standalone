#!/usr/bin/env python3
"""Scrape both arms' per-movie logs for conditions that would invalidate the comparison.

Two specific hazards this exists to catch:
  * MotionCorr's CUDA path has CPU fallback branches that only emit a WARNING to the
    per-movie .log. A partial fallback means the timing and the "CUDA path" claim are
    both wrong, and nothing else in the output reveals it.
  * RELION discards its 5x5 local motion model entirely (correcting with the global
    trajectory only) if too few patches converge, if the fit is too steep, or if the
    fit RMSD is too large. A movie that fell back is being compared as
    "local correction vs no local correction".
"""
import json, os, re, sys, glob

mc_dir, mc3_logdir, out = sys.argv[1], sys.argv[2], sys.argv[3]
rows = []
for p in sorted(glob.glob(os.path.join(mc_dir, "Movies", "*.log"))):
    base = os.path.basename(p)[:-4]
    txt = open(p, errors="replace").read()
    hot = re.search(r"Detected (\d+) hot pixels", txt)
    iters = re.findall(r"Iteration (\d+): RMSD = ([0-9.eE+-]+) px", txt)
    rows.append({
        "movie": base,
        "cuda_warnings": re.findall(r"^.*(?:WARNING|falling back|fall back).*$", txt, re.M)[:6],
        "n_cuda_warnings": len(re.findall(r"WARNING|falling back|fall back", txt)),
        "local_model_rejected": bool(re.search(
            r"could not fit|Local correction is disabled|not fit a reasonable", txt, re.I)),
        "hot_pixels": int(hot.group(1)) if hot else None,
        "global_iters": len([i for i in iters]) ,
        "used_cuda_profile_block": "[CUDA Global Alignment Profile]" in txt,
    })

mc3 = []
for p in sorted(glob.glob(os.path.join(mc3_logdir, "*-Patch-Patch.log"))):
    base = os.path.basename(p)[:-len("-Patch-Patch.log")]
    bad = tot = 0
    for line in open(p, errors="replace"):
        s = line.split()
        if len(s) == 6 and not line.startswith("#"):
            tot += 1
            if s[5] != "0":
                bad += 1
    mc3.append({"movie": base, "patch_shift_entries": tot, "flagged_bad": bad,
                "frac_bad": round(bad / tot, 5) if tot else None})

summary = {
    "motioncorr_movies": len(rows),
    "motioncorr_with_cuda_warnings": sum(1 for r in rows if r["n_cuda_warnings"]),
    "motioncorr_with_cuda_profile": sum(1 for r in rows if r["used_cuda_profile_block"]),
    "motioncorr_local_model_rejected": sum(1 for r in rows if r["local_model_rejected"]),
    "motioncor3_movies": len(mc3),
    "motioncor3_total_bad_patch_entries": sum(m["flagged_bad"] for m in mc3),
    "motioncor3_total_patch_entries": sum(m["patch_shift_entries"] for m in mc3),
}
json.dump({"summary": summary, "motioncorr": rows, "motioncor3": mc3},
          open(out, "w"), indent=1)
print(json.dumps(summary, indent=1))
