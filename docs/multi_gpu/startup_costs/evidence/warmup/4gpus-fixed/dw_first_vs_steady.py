import json,statistics as st,collections
R="/home/alex/mc-small/wu/runs-fixed"
runs=[json.loads(l) for l in open(R+"/runs.jsonl")]
ex=collections.defaultdict(list)
for r in runs:
    if r["tag"].startswith("warm"): continue
    L=[json.loads(l) for l in open("%s/%s/profile.jsonl"%(R,r["tag"]))]
    mv=[x for x in L if x["type"]=="movie"]
    d=lambda m: {s["name"]:s["wall_ms"] for s in m["stages"]}
    first=d(mv[0]); steady=collections.defaultdict(list)
    for m in mv[1:]:
        for k,v in d(m).items(): steady[k].append(v)
    n=r["tag"].split("_")[1]
    ex[(n,r["arm"],"dw first")].append(first["dose weighting"])
    ex[(n,r["arm"],"dw steady")].append(st.median(steady["dose weighting"]))
for k in sorted(ex):
    print(k, "median %.1f"%st.median(ex[k]), [round(x) for x in ex[k]])
