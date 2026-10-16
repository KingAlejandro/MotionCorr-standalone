"""Per-round paired differences against main from fixed_ab.sh output."""
import json, statistics as st, sys, collections
from math import comb
R = sys.argv[1]
runs = [json.loads(l) for l in open(f"{R}/runs.jsonl")]
def sign_p(d):
    n = len(d); w = sum(x > 0 for x in d); k = min(w, n - w)
    return w, n, min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
rec = {}
for r in runs:
    if r["tag"].startswith("warm"): continue
    rd, n, arm = r["tag"].split("_", 2)
    L = [json.loads(l) for l in open(f"{R}/{r['tag']}/profile.jsonl")]
    mv = [x for x in L if x["type"] == "movie"]; pr = [x for x in L if x["type"] == "process"][0]
    sub = {s["name"]: s["wall_ms"] for s in mv[0]["sub"]}
    stg = {s["name"]: s["wall_ms"] for s in mv[0]["stages"]}
    rec[(rd, n, arm)] = dict(proc=r["proc_wall_ms"], run=pr["run_wall_ms"], first=mv[0]["wall_ms"], outside=r["proc_wall_ms"] - pr["run_wall_ms"],
        setup=sub.get("session and device ingest/session setup", 0) + sub.get("session and device ingest/context warmup wait", 0),
        ingest_setup=sub.get("session and device ingest/device ingest/ingest setup", 0), dw=stg["dose warping"] if False else stg["dose weighting"],
        rss=pr["peak_rss_kb"] / 1024)
for n in ("n12", "n96"):
    print(f"\n{n}: candidate minus main, per round (ms; negative = faster), arms rotate through positions")
    for arm in ("c1", "c2", "c3"):
        rounds = sorted({k[0] for k in rec if k[1] == n})
        print(f"  {arm}-main:")
        for m in ("proc", "run", "outside", "first", "setup", "ingest_setup", "dw", "rss"):
            d = [rec[(r, n, arm)][m] - rec[(r, n, "main")][m] for r in rounds if (r, n, arm) in rec and (r, n, "main") in rec]
            w, nn, p = sign_p([-x for x in d])
            print(f"    {m:13s} median {st.median(d):8.1f}   cand<main in {w}/{nn} rounds  p={p:.3f}   [{', '.join('%.0f' % x for x in d)}]")
