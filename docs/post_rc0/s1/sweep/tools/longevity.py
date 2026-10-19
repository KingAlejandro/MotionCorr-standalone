#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Coarse S1.2 probes. CPU identity must pass before CUDA is interpreted.

Two S1-positive no-gain movies avoid conflating historical gain handling with
the local-fit question. F reference runs come from campaign.py on this host.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--root", required=True)
p.add_argument("--shas", default="6b6adf44,c499b1d3,2ff18e93")
p.add_argument("--movies", default="e10216-00,e10474f3-00")
p.add_argument("--patches", default="5")
p.add_argument("--result-name", default="longevity")
a = p.parse_args()
root = Path(a.root)
tool = root / "tools/sweep.py"
source = "/mnt/clathrin/alex-motioncorr-rc0/W-QF/src"
results = []
for sha in a.shas.split(","):
  for movie in a.movies.split(","):
    for patches in a.patches.split(","):
        assert patches in ("3", "5")
        tag = movie + "-p" + patches + "-" + sha
        cpu, gpu = tag + "-cpu", tag + "-cuda"
        ref = movie + "-p" + patches + "-F-cpu"
        for backend, label in (("cpu", cpu), ("cuda", gpu)):
            if backend == "cuda":
                identity = json.loads((root / "analysis" / (cpu + ".json")).read_text())
                if not identity["identical"]:
                    results.append(dict(sha=sha, movie=movie, patches=int(patches), control="FAIL", cuda="UNRUN: invalid CPU control"))
                    print("INVALID CPU CONTROL", sha, movie, flush=True)
                    break
            cmd = [sys.executable, str(tool), "arm", "--root", str(root), "--movie", movie,
                   "--label", label, "--binary", str(root / ("build-" + sha + "-" + backend) / "motioncorr"),
                   "--sha", sha, "--patches", patches]
            if backend == "cuda":
                cmd.append("--gpu")
            if sha not in ("6b6adf44", "c499b1d3"):
                cmd.append("--legacy")
            rec = root / "runs" / label / "run.json"
            if not (rec.is_file() and json.loads(rec.read_text()).get("exit_status") == 0):
                subprocess.run(cmd, check=True)
            cmd = [sys.executable, str(tool), "analyze", "--root", str(root), "--source", source,
                   "--ref", ref if backend == "cpu" else cpu, "--test", label, "--patches", patches]
            if backend == "cpu":
                cmd.append("--identity")
            subprocess.run(cmd, check=(backend == "cuda"))
            if backend == "cuda":
                analysis = json.loads((root / "analysis" / (gpu + ".json")).read_text())
                results.append(dict(sha=sha, movie=movie, patches=int(patches), control="PASS", relative_rmse=analysis["relative_rmse"], backend_status=analysis["backend_status"]))
        (root / (a.result_name + ".json")).write_text(json.dumps(results, indent=2) + "\n")
print("LONGEVITY COMPLETE", flush=True)
