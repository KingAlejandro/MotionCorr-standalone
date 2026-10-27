import hashlib, json, os, subprocess, sys, glob, collections
OUTP = "/home/alex/mc-dcnative-stagec-20261027-r1"; R = OUTP + "/runs"
STAGE = "/home/alex/mc-dcnative-stagec-parent-20261027-r1"
pins = json.load(open(STAGE + "/docs/post_rc0/ccf_dc_native_compat_20261026/evidence/stageC/STAGEC_PINS.json"))
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
out = {}
# 1. all 59 input/truth files against the frozen pins
bad = []
for tag in ("k267", "n"):
    f = pins["fixtures"][tag]
    for name, h in f["file_hashes"].items():
        if sha(f["dir"] + "/" + name) != h: bad.append(tag + "/" + name)
out["fixtures_rehash"] = dict(files=sum(len(pins["fixtures"][t]["file_hashes"]) for t in ("k267", "n")), mismatches=bad)
# 2. binaries (and oracles) and the pinned guard, modules
out["binaries"] = {k: sha(v["path"]) == v["sha256"] for k, v in pins["binaries"].items()}
out["guard_pinned_path"] = sha(pins["guard"]["path"]) == pins["guard"]["sha256"]
# 3. release copy and final status
rc = sha(R + "/release_copy.json"); fs = json.load(open(R + "/final_status.json"))
PR = "83183e0481218f0eab0e3d5fff6d9ccd267f743fb1cabdce68f910ce4373461a"
out["release"] = dict(copy_sha256=rc, equals_parent=rc == PR, final_status_release=fs["release"], final_status_equals_parent=fs["release"]["sha256"] == PR)
# 4. manifest closure
lines = open(R + "/SHA256SUMS").read().splitlines(); okc, badc, names = 0, [], []
for l in lines:
    h, n = l.split("  ", 1); names.append(n)
    if sha(R + "/" + n) == h: okc += 1
    else: badc.append(n)
out["manifest"] = dict(entries=len(lines), ok=okc, failed=badc, lists_itself="SHA256SUMS" in names,
                       files_on_disk=sum(len(f) for _, _, f in os.walk(R)) - 1)
# 5. coverage, rows, GPU attribution
cov = json.load(open(R + "/coverage.json")); out["coverage"] = {k: v for k, v in cov.items() if k != "not_run"}; out["not_run_count"] = len(cov["not_run"])
ev = [json.loads(l) for l in open(R + "/events.jsonl")]
jobs = [e for e in ev if e["kind"] == "job"]
out["job_events"] = collections.Counter((e["phase"], e["row_status"], e["rc"]) for e in jobs).most_common()
gpu = {}
GPU2 = pins["gpu"]["uuid"]
for e in jobs:
    rec = json.load(open(f"{R}/runs/{e['job_id']}/receipt.json"))
    if rec["ledger_row"]["backend"] == "cuda":
        s = rec["sampling"]
        seen = s.get("gpu_uuids_seen_by_pid", {})
        gpu[e["job_id"]] = dict(status=s.get("status"), gpu_status=s.get("gpu_status"), samples=s.get("samples"),
                                uuids={u for v in seen.values() for u in v} and sorted({u for v in seen.values() for u in v}),
                                only_granted=bool(seen) and all(set(v) == {GPU2} for v in seen.values()))
out["cuda_rows"] = len(gpu); out["cuda_gpu2_only_rows"] = sum(v["only_granted"] for v in gpu.values())
out["cuda_not_attributed"] = [k for k, v in gpu.items() if not v["only_granted"]]
thr = []
for e in jobs:
    rec = json.load(open(f"{R}/runs/{e['job_id']}/receipt.json")); s = rec["sampling"]
    thr.append((s.get("status", "")[:10], s.get("max_threads_total"), tuple(s.get("cpus_allowed_lists", []))))
out["sampling_summary"] = collections.Counter(thr).most_common(6)
# 6. resources and locks after the run
sh = lambda c: subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()
out["post"] = dict(
    driver_alive=sh("kill -0 4029862 2>/dev/null && echo yes || echo no"),
    stray_procs=sh("ps -eo pid,args --no-headers | grep -E '[c]cf_dc_stagec|[b]uild-(def|exp|iso)/motioncorr' | head"),
    locks={n: dict(inode=int(sh(f"stat -c %i /tmp/{n}.lock")), held_lines=int(sh(f"grep -c ':'$(stat -c %i /tmp/{n}.lock)' ' /proc/locks") or 0))
           for n in ("motioncorr-cuda-boundary-cpu80-87", "motioncorr-gpu2-correctness", "motioncorr-dcnative-gpu2-cpu80-87")},
    gpu=sh("nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader"),
    gpu_apps=sh("nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader"),
    outdir_du=sh(f"du -sh {OUTP} | cut -f1"), disk=sh("df -h /home/alex | tail -1"))
json.dump(out, sys.stdout, indent=1, default=lambda o: sorted(o) if isinstance(o, set) else str(o))
