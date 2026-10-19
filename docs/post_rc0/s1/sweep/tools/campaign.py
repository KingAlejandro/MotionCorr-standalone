#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run frozen QF CPU/CUDA binaries on the same 4GPUs host, one arm at a time.

Pass --extras after the complete rank<2 first pass. The rank is manifest order,
with the original #186 movies before other locally staged movies.
"""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--root", required=True)
p.add_argument("--extras", action="store_true")
p.add_argument("--all", action="store_true", help="all manifest rows, S1-positive families first")
p.add_argument("--wait-lock", action="store_true")
p.add_argument("--manifest", help="fixed input selection, e.g. original staged pass")
a = p.parse_args()
root = Path(a.root).resolve()
tool = root / "tools/sweep.py"
source = "/mnt/clathrin/alex-motioncorr-rc0/W-QF/src"
qf = "/mnt/clathrin/alex-motioncorr-rc0/W-QF"
lock = open(root / "campaign.lock", "a")
fcntl.flock(lock, fcntl.LOCK_EX | (0 if a.wait_lock else fcntl.LOCK_NB))
rows = json.loads((Path(a.manifest) if a.manifest else root / "manifest.json").read_text())["movies"]
if a.all:
    order = ["e10216", "e10474f3", "e10641", "e12963", "e10028", "e10361", "e10441", "e10474f4", "e10164", "tutorial"]
    rows = sorted(rows, key=lambda r: (order.index(r["family"]), r["rank"]))
else:
    rows = sorted((r for r in rows if (r["rank"] >= 2) == a.extras), key=lambda r: (r["rank"], r["family"]))
for row in rows:
    for patches in (5, 3):
        tag = row["id"] + "-p" + str(patches)
        labels = [tag + "-F-" + backend for backend in ("cpu", "cuda")]
        if (root / "analysis" / (labels[1] + ".json")).is_file():
            print("retained " + tag, flush=True)
            continue
        for backend, label in zip(("cpu", "cuda"), labels):
            rec = root / "runs" / label / "run.json"
            if rec.is_file() and json.loads(rec.read_text()).get("exit_status") == 0:
                continue
            cmd = [sys.executable, str(tool), "arm", "--root", str(root), "--movie", row["id"],
                   "--label", label, "--binary", qf + "/build-" + ("cpu" if backend == "cpu" else "nvcomp") + "/motioncorr",
                   "--sha", "6d68e2d6", "--patches", str(patches)]
            if backend == "cuda":
                cmd.append("--gpu")
            subprocess.run(cmd, check=True)
        subprocess.run([sys.executable, str(tool), "analyze", "--root", str(root), "--source", source,
                        "--ref", labels[0], "--test", labels[1], "--patches", str(patches)], check=True)
print("COMPLETE", "all" if a.all else ("extras" if a.extras else "first-pass"), flush=True)
