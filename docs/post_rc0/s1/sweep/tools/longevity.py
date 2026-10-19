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
a = p.parse_args()
root = Path(a.root)
tool = root / "tools/sweep.py"
source = "/mnt/clathrin/alex-motioncorr-rc0/W-QF/src"
results = []
for sha in ("6b6adf44", "c499b1d3", "2ff18e93"):
    for movie in ("e10216-00", "e10474f3-00"):
        tag = movie + "-p5-" + sha
        cpu, gpu = tag + "-cpu", tag + "-cuda"
        ref = movie + "-p5-F-cpu"
        for backend, label in (("cpu", cpu), ("cuda", gpu)):
            if backend == "cuda":
                identity = json.loads((root / "analysis" / (cpu + ".json")).read_text())
                if not identity["identical"]:
                    results.append(dict(sha=sha, movie=movie, control="FAIL", cuda="UNRUN: invalid CPU control"))
                    print("INVALID CPU CONTROL", sha, movie, flush=True)
                    break
            cmd = [sys.executable, str(tool), "arm", "--root", str(root), "--movie", movie,
                   "--label", label, "--binary", str(root / ("build-" + sha + "-" + backend) / "motioncorr"),
                   "--sha", sha, "--patches", "5"]
            if backend == "cuda":
                cmd.append("--gpu")
            if sha == "2ff18e93":
                cmd.append("--legacy")
            subprocess.run(cmd, check=True)
            cmd = [sys.executable, str(tool), "analyze", "--root", str(root), "--source", source,
                   "--ref", ref if backend == "cpu" else cpu, "--test", label, "--patches", "5"]
            if backend == "cpu":
                cmd.append("--identity")
            subprocess.run(cmd, check=(backend == "cuda"))
            if backend == "cuda":
                analysis = json.loads((root / "analysis" / (gpu + ".json")).read_text())
                results.append(dict(sha=sha, movie=movie, control="PASS", relative_rmse=analysis["relative_rmse"], backend_status=analysis["backend_status"]))
        (root / "longevity.json").write_text(json.dumps(results, indent=2) + "\n")
print("LONGEVITY COMPLETE", flush=True)
