#!/usr/bin/env python3
"""24-movie arm comparison: device work, PCIe traffic, and stage totals."""
import sqlite3, collections, sys
ARMS = [("main @1d7e13f",        "nsys24/r1_cuda_nvtx.sqlite"),
        ("cand --ingest float",  "nsys24/c5_cand_float.sqlite"),
        ("cand --ingest nvcomp", "nsys24/c1_cand_nvcomp.sqlite")]
def one(c, q, *a):
    r = c.execute(q, a).fetchone(); return r[0] if r and r[0] is not None else 0
print("%-24s%10s%10s%10s%12s%16s%10s" %
      ("arm", "span_s", "kern_ms", "mcpy_ms", "launches", "H2D bytes", "H2D GB/s"))
for nm, db in ARMS:
    c = sqlite3.connect("./" + db)
    k = one(c, "select sum(end-start) from CUPTI_ACTIVITY_KIND_KERNEL")
    m = one(c, "select sum(end-start) from CUPTI_ACTIVITY_KIND_MEMCPY")
    n = one(c, "select count(*) from CUPTI_ACTIVITY_KIND_KERNEL")
    hb = one(c, "select sum(bytes) from CUPTI_ACTIVITY_KIND_MEMCPY where copyKind=1")
    ht = one(c, "select sum(end-start) from CUPTI_ACTIVITY_KIND_MEMCPY where copyKind=1")
    lo = one(c, "select min(start) from CUPTI_ACTIVITY_KIND_RUNTIME")
    hi = one(c, "select max(end) from CUPTI_ACTIVITY_KIND_RUNTIME")
    print("%-24s%10.1f%10.0f%10.0f%12d%16s%10.2f" %
          (nm, (hi-lo)/1e9, k/1e6, m/1e6, n, format(hb, ","), (hb/ht) if ht else 0))
print()
print("%-24s%10s  %s" % ("arm", "peak VRAM", "top-3 kernels"))
for nm, db in ARMS:
    c = sqlite3.connect("./" + db)
    S = {r[0]: r[1] for r in c.execute("select id,value from StringIds")}
    try:
        opn = {r[0]: r[2] for r in c.execute("select id,name,label from ENUM_CUDA_DEV_MEM_EVENT_OPER")}
        cur = pk = 0
        for st, by, op in c.execute("select start,bytes,memoryOperationType from CUDA_GPU_MEMORY_USAGE_EVENTS order by start"):
            cur += by if opn.get(op, "").lower().startswith("alloc") else -by
            pk = max(pk, cur)
    except Exception: pk = 0
    top = list(c.execute("select shortName,sum(end-start) t from CUPTI_ACTIVITY_KIND_KERNEL group by shortName order by t desc limit 3"))
    print("%-24s%8.2f GiB  %s" % (nm, pk/2**30,
          ", ".join("%s %.0fms" % (S.get(s, "?")[:26], t/1e6) for s, t in top)))
print()
# aggregate stage totals
for nm, db in ARMS:
    c = sqlite3.connect("./" + db)
    R = collections.defaultdict(list)
    for s, a, b in c.execute("""select coalesce(e.text,x.value),e.start,e.end from NVTX_EVENTS e
        left join StringIds x on x.id=e.textId where e.end is not null"""):
        R[s].append((a, b))
    def u(iv):
        iv = sorted(iv); mm = []
        for a, b in iv:
            if mm and a <= mm[-1][1]: mm[-1][1] = max(mm[-1][1], b)
            else: mm.append([a, b])
        return sum(b-a for a, b in mm)
    tot = sorted(((u(v), k) for k, v in R.items() if not k.startswith("MOVIE")), reverse=True)
    print("%s -- top stages (s):" % nm)
    print("   " + "  ".join("%s=%.1f" % (k[:18], w/1e9) for w, k in tot[:8]))
