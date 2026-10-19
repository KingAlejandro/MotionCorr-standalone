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
a = p.parse_args()
root = Path(a.root).resolve()
tool = root / "tools/sweep.py"
source = "/mnt/clathrin/alex-motioncorr-rc0/W-QF/src"
qf = "/mnt/clathrin/alex-motioncorr-rc0/W-QF"
lock = open(root / "campaign.lock", "a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
rows = json.loads((root / "manifest.json").read_text())["movies"]
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
print("COMPLETE", "extras" if a.extras else "first-pass", flush=True)
