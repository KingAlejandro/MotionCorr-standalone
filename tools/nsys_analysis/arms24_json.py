#!/usr/bin/env python3
"""Build the 24-movie comparison payload for the charts."""
import sqlite3, json, collections
W = sys.argv[1] if len(sys.argv) > 1 else "./"
ARMS = [("main @1d7e13f",        "nsys24/r1_cuda_nvtx.sqlite", [31.705, 31.013]),
        ("cand --ingest float",  "nsys24/c5_cand_float.sqlite", [26.137, 25.357]),
        ("cand --ingest compact", None,                          [20.897, 20.992]),
        ("cand --ingest nvcomp", "nsys24/c1_cand_nvcomp.sqlite", [12.819, 12.591])]
def one(c, q, *a):
    r = c.execute(q, a).fetchone(); return r[0] if r and r[0] is not None else 0
def u(iv):
    iv = sorted(iv); m = []
    for a, b in iv:
        if m and a <= m[-1][1]: m[-1][1] = max(m[-1][1], b)
        else: m.append([a, b])
    return [tuple(x) for x in m]

out = {"arms": [], "lanes": {}, "stages": {}, "vram": {}, "permovie": {}}
for nm, db, walls in ARMS:
    rec = {"name": nm, "wall": sum(walls)/len(walls), "walls": walls}
    if db:
        c = sqlite3.connect(W+db)
        S = {r[0]: r[1] for r in c.execute("select id,value from StringIds")}
        lo = one(c, "select min(start) from CUPTI_ACTIVITY_KIND_RUNTIME")
        hi = one(c, "select max(end) from CUPTI_ACTIVITY_KIND_RUNTIME")
        ker = u([(r[0], r[1]) for r in c.execute("select start,end from CUPTI_ACTIVITY_KIND_KERNEL")])
        mem = u([(r[0], r[1]) for r in c.execute("select start,end from CUPTI_ACTIVITY_KIND_MEMCPY")])
        rec.update(span=(hi-lo)/1e9,
                   kern=one(c, "select sum(end-start) from CUPTI_ACTIVITY_KIND_KERNEL")/1e9,
                   mcpy=one(c, "select sum(end-start) from CUPTI_ACTIVITY_KIND_MEMCPY")/1e9,
                   h2d_bytes=one(c, "select sum(bytes) from CUPTI_ACTIVITY_KIND_MEMCPY where copyKind=1"),
                   launches=one(c, "select count(*) from CUPTI_ACTIVITY_KIND_KERNEL"))
        key = "main" if "main" in nm else ("nvcomp" if "nvcomp" in nm else "float")
        out["lanes"][key] = {"span": (hi-lo)/1e9,
                             "kernel": [[(a-lo)/1e9, (b-lo)/1e9] for a, b in ker],
                             "memcpy": [[(a-lo)/1e9, (b-lo)/1e9] for a, b in mem]}
        R = collections.defaultdict(list)
        for s, a, b in c.execute("""select coalesce(e.text,x.value),e.start,e.end from NVTX_EVENTS e
            left join StringIds x on x.id=e.textId where e.end is not null"""):
            R[s].append((a, b))
        st = {}
        for k, v in R.items():
            if k.startswith("MOVIE"): continue
            w = sum(b-a for a, b in u(v))
            if w > 3e7: st[k] = w/1e9
        out["stages"][key] = st
        mv = sorted(R.get("MOVIE (executeOwnMotionCorrection)", []))
        out["permovie"][key] = [(b-a)/1e9 for a, b in mv]
        try:
            opn = {r[0]: r[2] for r in c.execute("select id,name,label from ENUM_CUDA_DEV_MEM_EVENT_OPER")}
            cur = 0; pts = [[0, 0]]
            for stt, by, op in c.execute("select start,bytes,memoryOperationType from CUDA_GPU_MEMORY_USAGE_EVENTS order by start"):
                cur += by if opn.get(op, "").lower().startswith("alloc") else -by
                pts.append([(stt-lo)/1e9, cur])
            pts.append([(hi-lo)/1e9, cur])
            out["vram"][key] = pts
            rec["peak_vram"] = max(p[1] for p in pts)
        except Exception: pass
    out["arms"].append(rec)
json.dump(out, open(W+"results24/arms24.json", "w"))
for a in out["arms"]:
    print("%-24s wall=%5.1fs span=%s kern=%s mcpy=%s h2d=%s" %
          (a["name"], a["wall"],
           ("%.1f" % a["span"]) if "span" in a else "-",
           ("%.2f" % a["kern"]) if "kern" in a else "-",
           ("%.2f" % a["mcpy"]) if "mcpy" in a else "-",
           format(a.get("h2d_bytes", 0), ",")))
