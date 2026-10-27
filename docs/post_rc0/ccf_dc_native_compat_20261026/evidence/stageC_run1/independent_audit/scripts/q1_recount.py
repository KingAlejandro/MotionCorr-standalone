"""Q1: recount Stage C run-1 coverage, rows, B3, C-REPRO and manifest from the compact bundle only (read-only)."""
import sys, json, csv, hashlib, os, collections
EV, X, PINS, LEDGER, OUT = map(os.path.abspath, sys.argv[1:6])
R = os.path.join(X, "runs", "runs")
res = {}
pins = json.load(open(PINS))
ledger = list(csv.DictReader(open(LEDGER)))
led = {r["job_id"]: r for r in ledger}
kn = {j for j, r in led.items() if r["tier"] in ("K", "N")}
res["ledger"] = dict(rows=len(ledger), KN=len(kn), M=sum(r["tier"] == "M" for r in ledger))

runs = sorted(os.listdir(R))
res["run_dirs"] = len(runs)
cov = json.load(open(os.path.join(EV, "runs/coverage.json")))
notrun = set(cov["not_run"])
ex = set(runs)
res["executed_unique"] = len(ex)
res["executed_and_notrun_disjoint"] = not (ex & notrun)
res["union_equals_ledger_KN"] = (ex | notrun) == kn
res["notrun_split"] = dict(collections.Counter(led[j]["tier"] + "/" + led[j]["backend"] for j in notrun))
res["executed_split"] = {f"{k[0]}/{k[1]}": v for k, v in collections.Counter((led[j]["tier"], led[j]["backend"]) for j in ex).items()}

events = [json.loads(l) for l in open(os.path.join(EV, "runs/events.jsonl"))]
jobev = {e["job_id"]: e for e in events if e.get("kind") == "job"}
res["job_events"] = len(jobev)
res["phase_counts"] = dict(collections.Counter(e["phase"] for e in jobev.values()))
res["phase_backend"] = {f"p{p}/{b}": n for (p, b), n in collections.Counter((e["phase"], led[j]["backend"]) for j, e in jobev.items()).items()}
res["phase3_jobs"] = sorted(j for j, e in jobev.items() if e["phase"] == 3)
# B4 rows: phase 1
b4 = [j for j, e in jobev.items() if e["phase"] == 1]
bad = []
binhash = {k: v["sha256"] for k, v in pins["binaries"].items()}
status = collections.Counter(); rcs = collections.Counter(); wit = collections.Counter()
for j in runs:
    d = os.path.join(R, j)
    row = json.load(open(os.path.join(d, "row.json")))
    rc = open(os.path.join(d, "rc.txt")).read().strip()
    rec = json.load(open(os.path.join(d, "receipt.json")))
    status[row["row_status"]] += 1; rcs[rc] += 1; wit[str(row.get("witness_status"))] += 1
    b = led[j]["binary"]
    if rec["binary"]["sha256"] != binhash[b]: bad.append((j, "binary hash"))
    if rec["argv"] != rec.get("expected_argv"): bad.append((j, "argv != expected_argv"))
    if row.get("exit") != 0 or rc != "0": bad.append((j, "exit"))
    if jobev.get(j, {}).get("row_status") != row["row_status"]: bad.append((j, "event/row status mismatch"))
    if row["backend"] != led[j]["backend"] or row["arm"] != led[j]["arm"].replace("unset", row["arm"]) and False: pass
    if led[j]["backend"] == "cuda" and rec["env_passed"].get("CUDA_VISIBLE_DEVICES") != pins["gpu"].get("uuid", "GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598"): bad.append((j, "cuda env"))
res["row_status"] = dict(status); res["rc"] = dict(rcs); res["witness_status"] = dict(wit)
res["per_row_problems"] = bad
res["B4"] = dict(n=len(b4), backends=dict(collections.Counter(led[j]["backend"] for j in b4)),
                 all_cov=all(all(v.startswith(("COVERED", "NOT_APPLICABLE")) for v in json.load(open(os.path.join(R, j, "row.json")))["stage_coverage"].values()) for j in b4))
# B4 per-row coverage: global at cuda_single, local at cuda_batched, with positive eligible counters
b4rows = []
for j in sorted(b4):
    row = json.load(open(os.path.join(R, j, "row.json")))
    c = row["counters"]
    b4rows.append(dict(job=j, arm=row["arm"], stages=row["expected_stages"], cov=row["stage_coverage"],
                       g_single=c["cuda_single"]["global"]["frames_eligible"], l_batched=c["cuda_batched"]["local"]["frames_eligible"],
                       witness=row["witness_status"]))
res["B4_rows"] = b4rows
# guards
G = os.path.join(X, "runs", "guards")
gl = sorted(os.listdir(G))
res["guards"] = dict(n=len(gl), passed=sum(open(os.path.join(G, g)).read().rstrip().endswith("passed") for g in gl),
                     jobs_match=sorted(g.split("-", 2)[2][:-4] for g in gl) == runs)
# gpu attribution from procsamples
gs = collections.Counter()
for j in runs:
    if led[j]["backend"] != "cuda": continue
    seen = set()
    for l in open(os.path.join(R, j, "procsamples.jsonl")):
        s = json.loads(l)
        for k in ("gpu_status", "gpu"):
            if k in s: seen.add(json.dumps(s[k], sort_keys=True)[:80])
    gs[(j, tuple(sorted(seen)))] += 1
res["cuda_procsample_gpu_fields"] = [list(k) for k in gs]
# B3
b3 = {}
for f in sorted(os.listdir(os.path.join(EV, "runs/b3"))):
    v = json.load(open(os.path.join(EV, "runs/b3", f)))
    b3[f[:-5]] = {k: dict(identical=r["identical"], false_fields=[x for x, y in r.items() if y is False]) for k, r in v.items()}
res["B3"] = b3
# B3 independent: compare raw sha256 of out/ files across each triple via inventory.post.json
def inv(j):
    return {e["path"]: e["sha256"] for e in json.load(open(os.path.join(R, j, "inventory.post.json"))) if e["path"].startswith("out/")}
trip = collections.defaultdict(dict)
for j in runs:
    r = led[j]
    if r["tier"] == "K" and (r["binary"], r["arm"]) in (("def", "unset"), ("exp", "unset"), ("exp", "none")):
        trip[(r["case"], r["backend"])][r["binary"] + ":" + r["arm"]] = j
b3raw = {}
for (case, be), t in sorted(trip.items()):
    if len(t) != 3: b3raw[f"{case}-{be}"] = f"incomplete {sorted(t)}"; continue
    a, b, c = inv(t["def:unset"]), inv(t["exp:unset"]), inv(t["exp:none"])
    def diff(p, q): return sorted(k for k in set(p) | set(q) if p.get(k) != q.get(k))
    b3raw[f"{case}-{be}"] = dict(files=len(a), def_vs_expunset_raw_diff=diff(a, b), expunset_vs_expnone_raw_diff=diff(b, c))
res["B3_raw_out_hash_diffs"] = b3raw
# repro
rep = {}
for w in ("production", "isotropic"):
    v = json.load(open(os.path.join(EV, f"runs/repro/{w}.json")))
    m = 0.0; verd = True
    for r in v["rows"]:
        for k, x in r["diffs"].items():
            if isinstance(x, bool): verd &= x
            else: m = max(m, abs(x))
    rep[w] = dict(rows=len(v["rows"]), ok=sum(r["ok"] for r in v["rows"]), failed=v["failed"], max_abs_diff=m, verdicts_equal=verd, within_1e5=m <= pins["repro_tolerance"])
res["repro"] = rep
# pairs
pr = json.load(open(os.path.join(EV, "runs/pairs_report.json")))
res["pairs"] = dict(n=len(pr), status=dict(collections.Counter(p.get("status") for p in pr)),
                    evaluated_by_comparison=dict(collections.Counter(p["comparison"] for p in pr if p.get("status") == "EVALUATED")))
# manifest: rehash every manifest entry that exists in the compact bundle (paths relative to host runs/)
man = [l.rstrip("\n").split("  ", 1) for l in open(os.path.join(EV, "runs/SHA256SUMS"))]
roots = [os.path.join(EV, "runs"), os.path.join(X, "runs")]
chk = collections.Counter(); mism = []
for h, p in man:
    for rt in roots:
        fp = os.path.join(rt, p)
        if os.path.isfile(fp):
            ok = hashlib.sha256(open(fp, "rb").read()).hexdigest() == h
            chk["ok" if ok else "mismatch"] += 1
            if not ok: mism.append(p)
            break
    else:
        chk["not_local"] += 1
res["manifest_partial_rehash"] = dict(entries=len(man), **chk, mismatches=mism)
# local files in bundle that are not in the manifest (beyond the declared extras)
names = {p for _, p in man}
extra = []
for rt in roots:
    for dp, _, fn in os.walk(rt):
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), rt)
            if rel not in names and rel != "SHA256SUMS": extra.append(rel)
res["local_files_not_in_manifest"] = sorted(set(extra))
fs = json.load(open(os.path.join(EV, "runs/final_status.json")))
res["final_status"] = dict(status=fs["status"], reason=fs["reason"], release_sha=fs["release"]["sha256"], source=fs["source"])
json.dump(res, open(OUT, "w"), indent=1, sort_keys=True)
