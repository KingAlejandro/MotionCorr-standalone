#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build STAGEC_PINS.json from repository files and the retained Stage A/B and attempt-2 venue records. Reads, never runs a producer.

    python3 -I make_stagec_pins.py > STAGEC_PINS.json      (needs NumPy to regenerate the fixtures; checks them against the venue)

Deployment (done by the parent, not by this script): the staged tree `/home/alex/mc-dcnative-ab-20261026/src96e` (source `96e7e7be`)
gets exactly two added files, `tools/ccf_dc_stagec_driver.py` and `tools/stageC_guard.sh`; the pins hash the guard, the release hashes the driver.
"""
import hashlib, json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
D = ROOT / "docs/post_rc0/ccf_dc_native_compat_20261026"
STAGED = "/home/alex/mc-dcnative-ab-20261026/src96e"
STAGED_D = STAGED + "/docs/post_rc0/ccf_dc_native_compat_20261026"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
sys.path.insert(0, str(ROOT / "test-data"))
sys.path.insert(0, str(ROOT / "tools"))

venue = {}
for line in (D / "evidence/stageAB/run1/logs/input-hashes.sha256").read_text().splitlines():
    h, name = line.split()
    venue[name] = h
a2 = {}
for k in ("def", "exp", "iso"):
    h, path = (D / f"evidence/venue_attempt2/binary-{k}.sha256").read_text().split()
    a2[k] = dict(path=path, sha256=h)


def fixtures(tag, gen):
    """Pinned file hashes come from the venue's own MANIFEST (retained under venue_manifests/, sha equal to the venue record);
    the K267 manifest embeds the NumPy version, so a local regeneration differs in that one file. Locally regenerated fixture
    files are cross-checked against the venue record (every mrcs/star) and against the manifest entries; differences are listed."""
    fx = "fx-n" if tag == "n" else "fx-k267"
    mpath = D / "evidence/stageC/venue_manifests" / fx / "MANIFEST.json"
    assert sha(mpath) == venue[f"{fx}/MANIFEST.json"], "retained manifest differs from the venue record"
    man = json.loads(mpath.read_text())
    files = {"MANIFEST.json": sha(mpath)}
    for c in man["cases"].values():
        files.update(c["files"])
    if tag == "n":
        files["base_target.npy"] = man["base_sha256"]
    for name, h in venue.items():
        d_, _, fn = name.partition("/")
        if d_ == fx and fn != "MANIFEST.json":
            assert files[fn] == h, f"manifest entry {fn} differs from the venue record"
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "fx"
        gen(out)
        diff = [n for n in files if n != "MANIFEST.json" and sha(out / n) != files[n]]
        print(f"{tag}: local regeneration vs venue manifest entries, differing files: {diff}", file=sys.stderr)
        assert not [n for n in diff if n.endswith((".mrcs", ".star"))], "local mrcs/star differ from the venue"
    return files


import generate_ccf_dc_n_controls as ngen
import generate_motion_diagnostics as kgen
kfiles, nfiles = fixtures("k267", kgen.generate), fixtures("n", ngen.generate)
assert len(kfiles) == 33 and len(nfiles) == 26

mods = {m: sha(ROOT / "tools" / f"{m}.py") for m in ("ccf_dc_native_rows", "ccf_dc_tap_field", "check_motion_diagnostics",
                                                        "check_realistic_motion", "motion_field")}
f = lambda name: dict(path=f"{STAGED_D}/{name}", sha256=sha(D / name))
pins = dict(
    schema="stagec-pins/1", fake=False,
    source=dict(commit="96e7e7be0f08469da51c67a1ab251ae4e97cdfc3",
                archive_sha256="313f671f4af90e227754ec17c6e8a9cae70a7ea5aaca713de62aa1d297b8ea36", staged_tree=STAGED),
    ledger=f("ledger.csv"), pairs=f("pairs.csv"), repro=f("repro.csv"), counts=f("counts.json"),
    retained_cpu_reference=f("evidence/retained_cpu_reference.json"), retained_render_report=f("evidence/retained_render_report.json"),
    guard=dict(path=f"{STAGED}/tools/stageC_guard.sh", sha256=sha(ROOT / "tools/stageC_guard.sh")),
    expected=dict(jobs=160, pairs=96, repro=16),
    binaries=a2,
    fixtures=dict(k267=dict(dir="/home/alex/mc-dcnative-ab-20261026/fx-k267", manifest_sha256=kfiles["MANIFEST.json"], files=33, file_hashes=kfiles),
                  n=dict(dir="/home/alex/mc-dcnative-ab-20261026/fx-n", manifest_sha256=nfiles["MANIFEST.json"], files=26, file_hashes=nfiles)),
    python=dict(executable="/home/alex/.mc-venv/bin/python3", version="3.12.3", numpy="2.5.3"),
    modules=mods,
    compiler_provenance=dict(note="recorded from attempt 2 (binaries built there); not re-verified by the driver",
                             gcc="13.3.0", nvcc="12.8.61", cmake="3.28.3", cuda_arch="80", build_type="Release"),
    cpus=list(range(80, 88)), omp=dict(k267=8, n=2), repro_tolerance=1e-5,
    gpu=dict(uuid="GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598", foreign_pid=3983855,
             allocation="shared FOREIGN-CONTEXT correctness window; not exclusive, not timing, not science"),
    locks=dict(own="/tmp/motioncorr-dcnative-gpu2-cpu80-87.lock", cpu="/tmp/motioncorr-cuda-boundary-cpu80-87.lock",
               gpu2="/tmp/motioncorr-gpu2-correctness.lock"),
    guard_thresholds=dict(core_busy_percent=50, gpu2_util_percent=50), scratch_cap_gib=20,
    order="B4 rows first, then CPU rows (K, then N: arm none before arm both per weight set), then remaining CUDA rows",
)
print(json.dumps(pins, indent=1, sort_keys=True))
