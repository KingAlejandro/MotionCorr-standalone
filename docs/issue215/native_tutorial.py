#!/usr/bin/env python3
"""#215 healthy tutorial identity; run inside the caller's GPU lock/CPU cap.

Usage: python native_tutorial.py --work /mnt/clathrin/alex-motioncorr-215
The fixed and reverse-applied binaries must already exist (see README).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--work", type=Path, required=True)
a = ap.parse_args()
w = a.work.resolve()
src = w / "src"
sys.path.insert(0, str(src / "docs/rc0/qf/tools"))
from compact_compare_output_trees import compare_trees  # noqa: E402

root = w / "tutorial"
root.mkdir()
inp = root / "input"
(inp / "Movies").mkdir(parents=True)
fam = json.loads((src / "docs/workload_corpus/families.json").read_text())["families"][0]
assets = Path.home() / "motioncorr-validation-20261011-vm/tutorial-data/Movies"
movies = ["Movies/" + Path(p).name for p in fam["movies"]]
identities = {}
for name in [Path(p).name for p in movies] + ["gain.mrc"]:
    p = assets / name
    dest = inp / ("gain.mrc" if name == "gain.mrc" else "Movies/" + name)
    dest.symlink_to(p)
    identities[name] = dict(source=str(p), bytes=p.stat().st_size,
                            sha256=hashlib.sha256(p.read_bytes()).hexdigest())
star = inp / "movies.star"
star.write_text("data_optics\n\nloop_\n_rlnOpticsGroupName #1\n_rlnOpticsGroup #2\n"
                "_rlnMicrographOriginalPixelSize #3\n_rlnVoltage #4\n_rlnSphericalAberration #5\n"
                "_rlnAmplitudeContrast #6\nopticsGroup1 1 0.885 200 1.4 0.1\n\n"
                "data_movies\n\nloop_\n_rlnMicrographMovieName #1\n_rlnOpticsGroup #2\n" +
                "".join(p + " 1\n" for p in movies))
(root / "inputs.json").write_text(json.dumps(identities, indent=2) + "\n")
records = []
for cfg in ("G", "L"):
    outputs = {}
    for arm, binary, ingest in (("unfixed", w / "unfixed/motioncorr", "auto"),
                                 ("fixed", w / "build-nvcomp/motioncorr", "auto"),
                                 ("compact", w / "build-nvcomp/motioncorr", "compact")):
        out = root / f"{cfg}-{arm}"
        out.mkdir()
        wit = root / f"{cfg}-{arm}.witness"
        cmd = [str(binary), "--use_own", "--dose_weighting", "--dose_per_frame", "1.277",
               "--bfactor", "150", "--seed", "1", "--expected_frames", "24",
               "--i", str(star), "--o", str(out) + "/", "--j", "8", "--max_io_threads", "4",
               "--gainref", "gain.mrc", "--gpu", "0", "--ingest", ingest, "--ingest_witness", str(wit)]
        if cfg == "L":
            cmd += ["--patch_x", "5", "--patch_y", "5"]
        r = subprocess.run(cmd, cwd=inp, text=True, capture_output=True, timeout=300)
        (root / f"{cfg}-{arm}.process.log").write_text(r.stdout + r.stderr)
        routes = [line.split()[1] for line in wit.read_text().splitlines()] if wit.exists() else []
        logs = {p.name: [line for line in p.read_text().splitlines() if "nvCOMP ingestion" in line]
                for p in out.rglob("*.log")}
        rec = dict(config=cfg, arm=arm, command=cmd, returncode=r.returncode, routes=routes,
                   route_logs=logs, binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
        records.append(rec)
        assert r.returncode == 0 and routes == ["compact" if arm == "compact" else "nvcomp"] * 2, rec
        outputs[arm] = out
    first = outputs["fixed"] / (str(Path(movies[0]).with_suffix(".mrc")))
    dims = list(struct.unpack("<3i", first.read_bytes()[:12]))
    assert sorted(dims[:2]) == sorted([fam["nx"], fam["ny"]]) and dims[2] == 1
    manifest = dict(schema_version=1, input_star_sha256=hashlib.sha256(star.read_bytes()).hexdigest(),
                    expected_shape_xyz=dims, joint_star="corrected_micrographs.star", movies=movies)
    for arm in ("unfixed", "compact"):
        result = compare_trees(outputs[arm], outputs["fixed"], manifest, compare_auxiliary=False)
        (root / f"{cfg}-{arm}-identity.json").write_text(json.dumps(result, indent=2) + "\n")
        assert result["status"] == "PASS", result
(root / "result.json").write_text(json.dumps(records, indent=2) + "\n")
print("tutorial: G/L, two distinct movies, fixed/unfixed/compact product identity PASS")
