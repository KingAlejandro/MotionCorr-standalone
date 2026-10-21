#!/usr/bin/env python3
"""Verify retained bytes and recompute scalar controls; bulk MRC metrics stay native evidence."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import tarfile

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
R = ROOT / "results"
ap = argparse.ArgumentParser()
ap.add_argument("--write-index", action="store_true", help="record archive inventory before verification")
args = ap.parse_args()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def mix(h):
    h &= 0xffffffff
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xffffffff
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xffffffff
    return h ^ (h >> 16)


def global_star(b):
    text = re.search(r"data_global_shift\s*\n(.*?)(?=\n# version|\ndata_|\Z)", b.decode(), re.S).group(1)
    return [tuple(map(float, t[1:3])) for line in text.splitlines() if len(t := line.split()) == 3 and not t[0].startswith("_")]


def delta(a, b):
    assert len(a) == len(b) and a
    v = [math.hypot(x[0] - y[0], x[1] - y[1]) for x, y in zip(a, b)]
    return max(v), math.sqrt(sum(x*x for x in v) / len(v))


old_index = None if args.write_index else json.loads((RAW / "archive-index.json").read_text())
index = []
native_files = {}
small = {}
null_records = 0
for path in sorted(RAW.rglob("*.tar.gz")):
    a = {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha(path.read_bytes()), "members": []}
    assert a["bytes"] < 100_000_000
    with tarfile.open(path) as tar:
        for member in tar:
            if not member.isfile():
                continue
            assert not member.name.startswith("/") and ".." not in Path(member.name).parts
            assert not any(p.startswith("._") for p in Path(member.name).parts)
            b = tar.extractfile(member).read()
            entry = {"path": member.name, "bytes": len(b), "sha256": sha(b)}
            a["members"].append(entry)
            if path.parent.name == "native" and path.name != "original-references.tar.gz":
                assert member.name not in native_files
                native_files[member.name] = entry
                if member.name.endswith((".json", ".star", "/global.txt")):
                    small[member.name] = b
                if member.name.endswith("/null-dose.txt"):
                    seed = int(member.name.split("-Nnative")[1].split("/")[0])
                    for line in b.decode().splitlines():
                        t = line.split()
                        patch, iteration, frame = map(int, t[:3])
                        x, y, bx, by, nx, ny = map(float, t[3:])
                        h = mix(mix(mix(seed ^ ((patch + 2) & 0xffffffff)) ^ iteration) ^ frame)
                        assert f32(x + (1 if h & 1 else -1) * f32(abs(bx - x))) == nx
                        assert f32(y + (1 if h & 2 else -1) * f32(abs(by - y))) == ny
                        null_records += 1
            elif path.name == "original-references.tar.gz" and member.name.endswith((".star", ".json")):
                small[member.name] = b
    index.append(a)
if args.write_index:
    (RAW / "archive-index.json").write_text(json.dumps(index, indent=1) + "\n")
else:
    assert index == old_index, "archive bytes or member inventory changed"
manifest = json.loads((RAW / "native/capture-manifest.json").read_text())
assert {e["path"]: e for e in manifest} == native_files
ledger = json.loads((RAW / "native/run-ledger.json").read_text())
assert len(ledger) == 540
for run in ledger:
    assert json.loads(small[f'runs/{run["label"]}/run.json']) == run
    assert run["rc"] == 0
    cpus = set()
    for part in run["cpu_mask"].split(","):
        z = list(map(int, part.split("-")))
        cpus.update(range(z[0], z[-1] + 1))
    assert len(cpus) == 8 and min(cpus) >= 0 and max(cpus) <= 123
    if run["gpu"]:
        assert run["gpu_witness_uuids"] == [run["cuda_visible_devices"]]

primary = json.loads((R / "primary-60.json").read_text())
sources = {"A0": "4837b210", "A1": "9a834380", "A2": "9a834380", "N1": "7fe2864e", "N2": "7fe2864e"}
for row in primary:
    assert row["A0_identity_parent"]
    label = f'{row["movie"]}-p{row["grid"]}'
    reference = [b for name, b in small.items() if name.startswith(f"references/{label}/Movies/") and name.endswith(".star")]
    assert len(reference) == 1
    ref = global_star(reference[0])
    ref_run = json.loads(small[f"references/{label}/run.json"])
    assert ref_run.get("rc", ref_run.get("exit_status")) == 0
    for arm, source in sources.items():
        folder = f'runs/{label}-{ {"N1": "Nnative1", "N2": "Nnative2"}.get(arm, arm)}'
        run = json.loads(small[folder + "/run.json"])
        assert run["source_sha"].startswith(source) and run["gpu"]
        assert ("MC_DIAG_ZERO_CCF_DC" in run["extra_env"]) == (arm == "A2")
        if arm in ("N1", "N2"):
            assert run["extra_env"]["MC_DIAG_FIT_NULL"] == arm[1:]
        if arm == "A0":
            assert json.loads(small[folder + "/identity-parent.json"])["identical"]
        metrics = json.loads(small[folder + "/metrics.json"])
        assert all(row["arms"][arm][k] == v for k, v in metrics.items())
        stars = [b for name, b in small.items() if name.startswith(folder + "/Movies/") and name.endswith(".star")]
        assert len(stars) == 1
        mx, rms = delta(ref, global_star(stars[0]))
        assert abs(mx - row["arms"][arm]["global_max_px"]) < 1e-12
        assert abs(rms - row["arms"][arm]["global_rms_px"]) < 1e-12
assert len(primary) == 60
assert [sum(r["arms"][a]["relative_rmse"] >= .1 for r in primary) for a in sources] == [17, 19, 16, 21, 15]
assert null_records == 510732
fair = json.loads((R / "conditioned-cpu-60.json").read_text())
assert len(fair) == 60
for row in fair:
    label = f'{row["movie"]}-p{row["grid"]}'
    folder = "runs/" + label + "-cpuDC"
    run = json.loads(small[folder + "/run.json"])
    assert not run["gpu"] and run["extra_env"]["MC_DIAG_ZERO_CCF_DC"] == "1"
    def captured_global(b):
        return [tuple(map(float, t[1:3])) for l in b.decode().splitlines() if len(t := l.split()) == 3]
    ref = captured_global(small[folder + "/global.txt"])
    for arm in ("A0", "A1", "A2"):
        d = "runs/" + label + "-" + arm
        met = json.loads(small[d + "/cpuDC-reference-metrics.json"])
        assert all(row["arms"][arm][k] == v for k, v in met.items())
        mx, rms = delta(ref, captured_global(small[d + "/global.txt"]))
        assert abs(mx - row["arms"][arm]["global_max_px"]) < 1e-12
        assert abs(rms - row["arms"][arm]["global_rms_px"]) < 1e-12
assert [sum(r["arms"][a]["relative_rmse"] >= .1 for r in fair) for a in ("A0", "A1", "A2")] == [17, 20, 0]
for name, rows in (("primary", primary), ("conditioned", fair)):
    stored = json.loads((R / (name + "-transitions.json")).read_text())
    for group, contrasts in stored.items():
        family, grid = group.rsplit("-", 1)
        selected = [r for r in rows if (family == "pooled" or r["movie"].startswith(family + "-")) and (grid == "both" or r["grid"] == int(grid[1:]))]
        for q in contrasts:
            cells = [0, 0, 0, 0]
            for r in selected:
                x, y = (r["arms"][a]["relative_rmse"] >= .1 for a in (q["from"], q["to"]))
                cells[0 if x and y else 1 if x else 2 if y else 3] += 1
            assert cells == list(q["cells"].values()) and sum(cells) == q["n"]
            n = cells[1] + cells[2]
            p = min(1, 2 * sum(math.comb(n, i) for i in range(min(cells[1:3]) + 1)) / 2**n)
            assert p == q["mcnemar_exact_two_sided_p"]
assert all(r["star_identical"] for r in json.loads((R / "regenerated-reference-star-controls.json").read_text()))
report = {"status": "PASS", "archives": len(index), "archive_members": sum(len(a["members"]) for a in index), "native_capture_files": len(native_files), "selected_runs": len(ledger), "selected_gpu_runs": sum(r["gpu"] for r in ledger), "primary_configs": len(primary), "primary_GPU_runs": 300, "null_records_exactly_replayed": null_records, "limitations": "MRC pixel metrics are retained native scalar measurements; bulk MRCs remain on 4GPUs. This verifier checks their stored values, not recomputation from committed pixels."}
(RAW / "verification.json").write_text(json.dumps(report, indent=1) + "\n")
print(json.dumps(report))
