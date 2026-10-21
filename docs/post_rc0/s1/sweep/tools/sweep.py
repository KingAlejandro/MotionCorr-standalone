#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Evidence-only S1 runner. Remote modes need Linux; analyze needs NumPy.

One movie per process, relative STAR paths, unchanged backend comparator.
No performance assertions. Never removes inputs or another run's directory.
"""
import argparse
import collections
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys
import threading
import time

F = "6d68e2d6"
GPU = "GPU-eddb42fe-4f9a-adde-76d3-b924e14add54"
QF = Path("/mnt/clathrin/alex-motioncorr-rc0/W-QF")
QF_HASH = {"cpu": "43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42",
           "cuda": "2e00e0e8fb75aafaf23f15a3c2a142c7d35b6e30477d594244ecba495a5bb6b3"}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=2, sort_keys=True) + "\n")


def inventory(a):
    families = json.loads(Path(a.source, "docs/workload_corpus/families.json").read_text())["families"]
    text = Path(a.source, "docs/workload_corpus/corpus.md").read_text()
    expected = dict(re.findall(r"`([^`]+)`\s*\|\s*[\d,]+\s*\|\s*`([0-9a-f]{64})`", text))
    base = Path.home() / "motioncorr-validation-20261011-vm"
    roots = {"tutorial": base / "tutorial-data"}
    for f in families:
        acc = f["movies"][0].split("/")[0]
        if acc == "tutorial":
            continue
        roots[acc] = (Path("/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/data") / acc
                      if acc in ("EMPIAR-10164", "EMPIAR-10216")
                      else base / "corpus/data-https" / acc)
    rows, counts = [], {}
    for f in families:
        def source(rel):
            acc, tail = rel.split("/", 1)
            return roots[acc] / tail
        first = source(f["movies"][0])
        candidates = sorted(p for p in first.parent.glob("*" + first.suffix)
                            if p.is_file() and "gain" not in p.name.lower())
        extra = Path(a.root, "data", str(Path(f["movies"][0]).parent))
        candidates += sorted(p for p in extra.glob("*" + first.suffix) if p.is_file())
        # Keep the original corpus examples first, then all other staged movies.
        byname = {p.name: p for p in candidates}
        ordered = [byname[Path(r).name] for r in f["movies"] if Path(r).name in byname]
        ordered += [p for p in candidates if p not in ordered]
        counts[f["id"]] = {"staged_distinct_paths": len(ordered), "directory": str(first.parent)}
        gain = source(f["gain"]) if f.get("gain") else None
        gh = sha(gain) if gain else None
        if gain and f["gain"] in expected:
            assert gh == expected[f["gain"]], "gain hash mismatch"
        for i, p in enumerate(ordered):
            rel = str(Path(f["movies"][0]).parent / p.name)
            h = sha(p)
            if rel in expected:
                assert h == expected[rel], "movie hash mismatch: " + rel
            rows.append(dict(id=f["id"] + "-%02d" % i, family=f["id"], rank=i,
                             recipe=f, relative_path=rel, movie_source=str(p.resolve()),
                             movie_sha256=h, movie_bytes=p.stat().st_size,
                             expected_corpus_sha256=expected.get(rel),
                             gain_source=str(gain.resolve()) if gain else None,
                             gain_sha256=gh))
    # Equal hashes are duplicate bytes, never additional distinct movies.
    seen, unique = set(), []
    for r in rows:
        key = (r["family"], r["movie_sha256"])
        if key not in seen:
            unique.append(r)
            seen.add(key)
    write(Path(a.root, "manifest.json"), dict(source=F, inventory=counts, movies=unique))
    print(json.dumps({f: sum(r["family"] == f for r in unique) for f in counts}), flush=True)


def bench_free(path):
    with open(path, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            return True
        except BlockingIOError:
            return False


def arm(a):
    root = Path(a.root).resolve()
    lane_file = root / "lane.json"
    lane = json.loads(lane_file.read_text()) if lane_file.is_file() else dict(index=0, uuid=GPU, cpus="96-103")
    gpu_uuid = lane["uuid"]
    row = next(r for r in json.loads((root / "manifest.json").read_text())["movies"] if r["id"] == a.movie)
    f = row["recipe"]
    out = root / "runs" / a.label
    if out.exists():
        raise RuntimeError("refusing to overwrite run " + str(out))
    out.mkdir(parents=True)
    inp = root / "inputs" / a.movie
    (inp / "Movies").mkdir(parents=True, exist_ok=True)
    source = Path(row["movie_source"])
    gain = Path(row["gain_source"]) if row["gain_source"] else None
    if a.cpu64:
        source = Path("/home/ubuntu/mc-corpus-186/data") / row["relative_path"]
        if not source.is_file():
            source = root / "data" / row["relative_path"]
        gain = Path("/home/ubuntu/mc-corpus-186/data") / f["gain"] if gain else None
    assert sha(source) == row["movie_sha256"], "input mismatch"
    if gain:
        assert sha(gain) == row["gain_sha256"], "gain mismatch"
    suffix = ".mrcs" if source.suffix == ".mrc" else source.suffix
    name = source.stem.replace(".", "_") + suffix
    link = inp / "Movies" / name
    if not link.exists():
        link.symlink_to(source.resolve())
    if gain and not (inp / f["gain_link"]).exists():
        (inp / f["gain_link"]).symlink_to(gain.resolve())
    star = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 {angpix} {voltage} {cs} 0.1

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/{name} 1
""".format(name=name, **f)
    (inp / "movies.star").write_text(star)
    binary = Path(a.binary).resolve()
    bh = sha(binary)
    if str(binary).startswith(str(QF)):
        assert bh == QF_HASH["cuda" if a.gpu else "cpu"]
    args = [str(binary), "--use_own", "--dose_weighting", "--dose_per_frame", str(f["dose"]),
            "--bfactor", "150", "--seed", "1", "--i", "movies.star", "--o", str(out) + "/",
            "--j", "8", "--patch_x", str(a.patches), "--patch_y", str(a.patches)]
    if not a.legacy:
        args += ["--expected_frames", str(f["frames"]), "--ingest_witness", str(out / "witness.txt")]
    if gain:
        args += ["--gainref", f["gain_link"]]
    if f.get("eer_grouping"):
        args += ["--eer_grouping", str(f["eer_grouping"]), "--eer_upsampling", "1"]
    if a.gpu:
        args += ["--gpu", "0"]
        if not a.legacy:
            args += ["--ingest", "auto"]
    cpus = "48-55" if a.cpu64 else lane["cpus"]
    env = dict(os.environ, OMP_NUM_THREADS="8", OPENBLAS_NUM_THREADS="1",
               CUDA_VISIBLE_DEVICES=gpu_uuid if a.gpu else "",
               LD_LIBRARY_PATH="/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib")
    cmd = ["taskset", "-c", cpus, "/usr/bin/time", "-v", "-o", str(out / "time-v.log")] + args
    lockname = "/tmp/motioncorr-cpu64-bench.lock" if a.cpu64 else "/tmp/motioncorr-gpu%s-correctness.lock" % lane["index"]
    bench = "/tmp/motioncorr-bench.lock"
    rec = dict(label=a.label, movie=a.movie, source=a.sha, binary=str(binary), binary_sha256=bh,
               runner_sha256=sha(Path(__file__)), hostname=os.uname().nodename,
               movie_sha256=row["movie_sha256"], gain_sha256=row["gain_sha256"],
               input_star_sha256=sha(inp / "movies.star"), argv=cmd, cwd=str(inp), cpu_mask=cpus,
               lock=lockname, gpu=a.gpu, requested_gpu_uuid=gpu_uuid if a.gpu else None,
               environment={k: env[k] for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "CUDA_VISIBLE_DEVICES", "LD_LIBRARY_PATH")})
    stop = threading.Event()
    witnessed = set()
    def sample(pid):
        while not stop.is_set():
            family, pending = {pid}, [pid]
            while pending:
                k = pending.pop()
                try:
                    children = [int(x) for x in Path("/proc/%s/task/%s/children" % (k, k)).read_text().split()]
                except OSError:
                    children = []
                family.update(children)
                pending.extend(children)
            try:
                q = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"], capture_output=True, text=True, timeout=10)
            except subprocess.TimeoutExpired:
                continue
            for line in q.stdout.splitlines():
                u, p = [v.strip() for v in line.split(",")]
                if int(p) in family:
                    witnessed.add(u)
            stop.wait(.2)
    # Optional fallback lanes avoid waiting behind a long, unrelated lane holder.
    # Selection precedes the payload and is recorded by UUID, never CUDA ordinal.
    candidates = [lane] + lane.get("fallback_lanes", [])
    lock = None
    while lock is None:
        if not a.cpu64 and not bench_free(bench):
            time.sleep(5)
            continue
        for candidate in candidates:
            assert candidate["cpus"] == cpus or a.cpu64
            path = "/tmp/motioncorr-cpu64-bench.lock" if a.cpu64 else "/tmp/motioncorr-gpu%s-correctness.lock" % candidate["index"]
            fd = open(path, "a")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fd.close()
                continue
            if not a.cpu64 and not bench_free(bench):
                fd.close()
                continue
            occupancy = ""
            if a.gpu:
                occupancy = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"], capture_output=True, text=True, check=True, timeout=10).stdout
                if candidate["uuid"] in occupancy:
                    fd.close()
                    continue
            lock, lockname, gpu_uuid = fd, path, candidate["uuid"]
            break
        if lock is None:
            time.sleep(5)
    with lock:
        env["CUDA_VISIBLE_DEVICES"] = gpu_uuid if a.gpu else ""
        rec["environment"]["CUDA_VISIBLE_DEVICES"] = env["CUDA_VISIBLE_DEVICES"]
        rec["lock"] = lockname
        rec["requested_gpu_uuid"] = gpu_uuid if a.gpu else None
        rec["start_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if a.gpu:
            rec["occupancy_before"] = occupancy
        write(out / "run.json", rec)
        with (out / "stdout.log").open("w") as log:
            p = subprocess.Popen(cmd, cwd=inp, env=env, stdout=log, stderr=subprocess.STDOUT)
            th = threading.Thread(target=sample, args=(p.pid,)) if a.gpu else None
            if th:
                th.start()
            rec["exit_status"] = p.wait()
            stop.set()
            if th:
                th.join()
        rec["gpu_witness_uuids"] = sorted(witnessed)
        write(out / "run.json", rec)
    print(json.dumps({k: rec[k] for k in ("label", "exit_status", "gpu_witness_uuids")}), flush=True)
    return rec["exit_status"]


def analyze(a):
    root = Path(a.root)
    sys.path.insert(0, a.source + "/tools")
    from compare_motioncorr import parse_star_file, parse_mrc, discover_output_files
    dirs = [root / "runs" / label for label in (a.ref, a.test)]
    records = [json.loads((p / "run.json").read_text()) for p in dirs]
    if any(r["exit_status"] != 0 for r in records):
        raise RuntimeError("failed arm, no numerical verdict")
    result = dict(reference=a.ref, test=a.test, movie=records[0]["movie"])
    result["comparator_sha256"] = sha(Path(a.source, "tools/compare_motioncorr.py"))
    products = []
    for p in dirs:
        mrc, star, errors = discover_output_files(p)
        assert not errors and mrc and star, (errors, mrc, star)
        products.append((mrc, star))
    patchsets = []
    for p, (_, star) in zip(dirs, products):
        b = parse_star_file(star).get("local_shift", {"labels": [], "rows": []})
        rows = b["rows"]
        # The STAR stores frame, patch-center X/Y and observed X/Y shift.
        centers = collections.Counter((int(float(r[1])), int(float(r[2]))) for r in rows)
        log = next((p / "Movies").glob("*.log")).read_text()
        mapping = {(int(x), int(y)): (int(iy), int(ix)) for iy, ix, x, y in
                   re.findall(r"Patch \((\d+), (\d+)\):.*Center = \((\d+), (\d+)\)", log)}
        assert len(mapping) == a.patches ** 2, "missing patch logs"
        assert set(centers) <= set(mapping), "unmapped STAR center"
        kept = {mapping[c] for c in centers}
        manifest = json.loads((root / "manifest.json").read_text())
        recipe = next(r["recipe"] for r in manifest["movies"] if r["id"] == result["movie"])
        assert all(n == recipe["frames"] for n in centers.values()), "incomplete local-shift observations"
        patchsets.append(kept)
        result[p.name] = dict(local_shift_rows=len(rows), accepted_patches=len(kept),
                              accepted_set=sorted(kept), rejected_set=sorted(set(mapping.values()) - kept),
                              rows_per_center={str(k): v for k, v in centers.items()})
    result["cpu_only_patches"] = sorted(patchsets[0] - patchsets[1])
    result["test_only_patches"] = sorted(patchsets[1] - patchsets[0])
    target = root / "analysis" / (a.test + ".json")
    if a.identity:
        checks = []
        for (ma, sa), (mb, sb) in [products]:
            ha, pa, _ = parse_mrc(ma)
            hb, pb, _ = parse_mrc(mb)
            ba, bb = ma.read_bytes(), mb.read_bytes()
            na, nb = struct.unpack_from("<i", ba, 92)[0], struct.unpack_from("<i", bb, 92)[0]
            checks = dict(core_header=ba[:224] == bb[:224], payload=pa.tobytes() == pb.tobytes(),
                          extended_header=ba[1024:1024+na] == bb[1024:1024+nb],
                          star=sa.read_bytes() == sb.read_bytes(),
                          labels_unmasked=ba[224:1024] == bb[224:1024],
                          payload_sha256=[hashlib.sha256(p.tobytes()).hexdigest() for p in (pa, pb)])
        result["identity"] = checks
        result["identical"] = all(checks[k] for k in ("core_header", "payload", "extended_header", "star"))
        exact = root / "analysis" / (a.test + "-exact.json")
        exact.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, a.source + "/tools/compare_motioncorr.py", "--ref", str(dirs[0]),
               "--test", str(dirs[1]), "--gate", "exact", "--require-complete-coverage", "--json-out", str(exact)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        exact.with_suffix(".stdout.log").write_text(r.stdout + r.stderr)
        assert r.returncode in (0, 1) and exact.is_file(), "exact comparator execution failure"
        result["exact_comparator_argv"] = cmd
        result["exact_comparator_exit_status"] = r.returncode
        result["identical"] = result["identical"] and r.returncode == 0
        write(target, result)
        print(json.dumps(result), flush=True)
        return 0 if result["identical"] else 1
    gate = root / "analysis" / (a.test + "-backend.json")
    gate.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, a.source + "/tools/compare_motioncorr.py", "--ref", str(dirs[0]),
           "--test", str(dirs[1]), "--test-log", str(dirs[1] / "time-v.log"),
           "--gate", "backend", "--json-out", str(gate)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    (gate.with_suffix(".stdout.log")).write_text(r.stdout + r.stderr)
    assert r.returncode in (0, 1) and gate.is_file(), "comparator execution failure"
    report = json.loads(gate.read_text())
    result.update(comparator_argv=cmd, comparator_exit_status=r.returncode,
                  backend_status=report["overall_status"],
                  relative_rmse=report["checks"]["corrected_image"]["relative_rmse"])
    # Descriptive S1 screen only. The comparator's gates and tolerances are unchanged.
    result["large_disagreement_relative_rmse_ge_0_1"] = result["relative_rmse"] >= .1
    write(target, result)
    print(json.dumps(result), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode", required=True)
    inv = sub.add_parser("inventory")
    arm_p = sub.add_parser("arm")
    ana = sub.add_parser("analyze")
    for q in (inv, arm_p, ana):
        q.add_argument("--root", required=True)
    for q in (inv, ana):
        q.add_argument("--source", required=True)
    for name in ("movie", "label", "binary", "sha"):
        arm_p.add_argument("--" + name, required=True)
    for name in ("gpu", "cpu64", "legacy"):
        arm_p.add_argument("--" + name, action="store_true")
    for q in (arm_p, ana):
        q.add_argument("--patches", type=int, choices=(3, 5), required=True)
    for name in ("ref", "test"):
        ana.add_argument("--" + name, required=True)
    ana.add_argument("--identity", action="store_true")
    a = p.parse_args()
    return {"inventory": inventory, "arm": arm, "analyze": analyze}[a.mode](a)


if __name__ == "__main__":
    sys.exit(main())
