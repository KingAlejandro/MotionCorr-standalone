#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Collect proportionate evidence from scratch; never collect MRCs or binaries.

Run on 4GPUs with --root. Produces <root>/evidence, safe for a docs-only commit.
Original logs and all products remain in scratch.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--root", required=True)
p.add_argument("--out")
p.add_argument("--first-pass", action="store_true")
a = p.parse_args()
root = Path(a.root)
out = Path(a.out) if a.out else root / "evidence"
out.mkdir(exist_ok=True)
manifest = json.loads((root / "manifest.json").read_text())
excluded = {r["id"] for r in manifest["movies"] if a.first_pass and r["rank"] >= 2}
def wanted(name):
    return not any(name.startswith(movie + "-") for movie in excluded)

def copy(src, dst, compress=False):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if compress:
        with src.open("rb") as f, dst.open("wb") as g:
            with gzip.GzipFile(filename="", fileobj=g, mode="wb", mtime=0) as z:
                shutil.copyfileobj(f, z)
    else:
        shutil.copyfile(src, dst)

copy(root / "manifest.json", out / "manifest.json")
for src in sorted((root / "analysis").glob("*.json")):
    if not wanted(src.name):
        continue
    copy(src, out / "analysis" / src.name)
for src in sorted((root / "build-records").glob("*")):
    copy(src, out / "builds" / (src.name + ".gz"), True)
for src in root.glob("longevity*.json"):
    copy(src, out / src.name)
for src in (root / "acquisition").glob("*"):
    if src.is_file():
        compress = src.suffix == ".log"
        copy(src, out / "acquisition" / (src.name + (".gz" if compress else "")), compress)
for src in root.glob("*.exit"):
    copy(src, out / src.name)
for name in ("lane.json", "continuation-status.json", "queued-restart.json"):
    if (root / name).is_file():
        copy(root / name, out / name)
for run in sorted((root / "runs").iterdir()):
    if not run.is_dir():
        continue
    rec = run / "run.json"
    if not wanted(run.name) or not rec.is_file() or "exit_status" not in json.loads(rec.read_text()):
        continue
    for src in sorted(run.rglob("*")):
        if not src.is_file() or src.suffix == ".mrc":
            continue
        if src.name not in ("run.json", "witness.txt", "time-v.log", "stdout.log") and src.suffix not in (".star", ".log"):
            continue
        rel = src.relative_to(root)
        compress = src.name != "run.json"
        copy(src, out / (str(rel) + (".gz" if compress else "")), compress)
for name in ("first-pass.log", "extras.log", "longevity.log", "fetch-breadth.log", "breadth.log", "breadth-routed.log", "route-breadth.log", "extend-10441.log", "longevity-continuation.log", "older-continuation-build.log"):
    if a.first_pass and name == "extras.log":
        continue
    if (root / name).is_file():
        copy(root / name, out / (name + ".gz"), True)
rechecks = root / "comparator-rechecks-v1"
if rechecks.is_dir():
    for src in list((rechecks / "analysis").glob("*")) + list(rechecks.glob("*.log")):
        if src.is_file():
            copy(src, out / "comparator-rechecks" / (str(src.relative_to(rechecks)) + ".gz"), True)
    if (rechecks / "equivalence.json").is_file():
        copy(rechecks / "equivalence.json", out / "comparator-rechecks/equivalence.json")
if (root / "recheck-comparator.log").is_file():
    copy(root / "recheck-comparator.log", out / "recheck-comparator.log.gz", True)
qf = Path("/mnt/clathrin/alex-motioncorr-rc0/W-QF")
for cfg in ("cpu", "nvcomp"):
    for name in ("CMakeCache.txt", "CMakeFiles/motioncorr_core.dir/flags.make"):
        copy(qf / ("build-" + cfg) / name, out / "frozen-builds" / (cfg + "-" + Path(name).name + ".gz"), True)
    src = qf / ("build-" + cfg) / "motioncorr"
    h = hashlib.sha256(src.read_bytes()).hexdigest()
    (out / "frozen-builds" / (cfg + ".sha256")).write_text(h + "  " + str(src) + "\n")
commands = ["hostname", "uname -a", "lscpu", "nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total --format=csv", "g++ --version", "/usr/local/cuda-12.8/bin/nvcc --version", "df -h /mnt/clathrin", "git -C /mnt/clathrin/alex-motioncorr-rc0/W-QF/src rev-parse HEAD"]
records = []
for cmd in commands:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    records.append(dict(command=cmd, exit_status=r.returncode, stdout=r.stdout, stderr=r.stderr))
(out / "collection-host.json").write_text(json.dumps(records, indent=2) + "\n")
print(out)
