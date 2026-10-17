import json, statistics as st, collections, sys
R = sys.argv[1]
med = st.median
def prof(path):
    L = [json.loads(l) for l in open(path)]
    return [x for x in L if x.get("type") == "movie"], [x for x in L if x.get("type") == "process"][0]
runs = [json.loads(l) for l in open(f"{R}/runs.jsonl")]
KEYS = [("read gain", "stage"), ("session and device ingest", "stage"), ("hot pixels", "stage"), ("dose weighting", "stage"),
        ("session and device ingest/session setup", "sub"), ("session and device ingest/context warmup wait", "sub"),
        ("session and device ingest/device ingest/ingest setup", "sub")]
rows = collections.defaultdict(list)
for r in runs:
    if r["tag"].startswith("warm"): continue
    n = r["tag"].split("_")[1]
    mv, pr = prof(f"{R}/{r['tag']}/profile.jsonl")
    d = dict(rc=r["rc"], nmrc=r["n_mrc"], proc=r["proc_wall_ms"], run=pr["run_wall_ms"], first=mv[0]["wall_ms"],
             steady=med([m["wall_ms"] for m in mv[1:]]), rss=pr["peak_rss_kb"])
    for k, kind in KEYS:
        src = mv[0]["stages" if kind == "stage" else "sub"]
        d[k] = next((s["wall_ms"] for s in src if s["name"] == k or (kind == "sub" and s["name"] == k)), 0.0)
    d["warmup_thread"] = next((t["wall_ms"] for t in pr["threads"] if t["name"].startswith("warmup/")), 0.0)
    d["drain"] = next((t["wall_ms"] for t in pr["threads"] if t["name"] == "main/final writer drain"), 0.0)
    rows[(n, r["arm"])].append(d)
for n in ("n12", "n96"):
    print(f"\n== {n}  (median over rounds; ms)")
    cols = ["proc", "run", "first", "steady"] + [k for k, _ in KEYS] + ["warmup_thread", "drain", "rss"]
    print("%-10s %3s " % ("arm", "n") + " ".join("%12s" % c[-12:] for c in cols))
    for (nn, arm), v in sorted(rows.items()):
        if nn != n: continue
        print("%-10s %3d " % (arm, len(v)) + " ".join("%12.1f" % med([x[c] for x in v]) for c in cols) +
              "  rc=%s mrc=%s" % ({x['rc'] for x in v}, {x['nmrc'] for x in v}))
        print("%-10s     proc=%s" % ("", [x["proc"] for x in v]))
