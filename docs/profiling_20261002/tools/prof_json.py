#!/usr/bin/env python3
"""Extract per-stage host walls and device occupancy from ONE nsys sqlite.

Everything emitted here comes from the single capture named on the command line.
No quantity is combined with, or subtracted from, a different run.
"""
import collections,json,sqlite3,sys
db,out=sys.argv[1],sys.argv[2]
c=sqlite3.connect(db); 
def one(q):
    try: r=c.execute(q).fetchone(); return r[0] if r and r[0] is not None else 0
    except sqlite3.OperationalError: return 0
def tbl(n):
    return c.execute("select count(*) from sqlite_master where type='table' and name=?",(n,)).fetchone()[0]>0

def union(iv):
    iv=sorted(iv); m=[]
    for a,b in iv:
        if m and a<=m[-1][1]: m[-1][1]=max(m[-1][1],b)
        else: m.append([a,b])
    return sum(b-a for a,b in m)

ranges=collections.defaultdict(list)
if tbl('NVTX_EVENTS'):
    for nm,a,b in c.execute("""select coalesce(e.text,s.value),e.start,e.end from NVTX_EVENTS e
                               left join StringIds s on s.id=e.textId where e.end is not null"""):
        if nm: ranges[nm].append((a,b))

ker=[(a,b) for a,b in c.execute("select start,end from CUPTI_ACTIVITY_KIND_KERNEL")] if tbl('CUPTI_ACTIVITY_KIND_KERNEL') else []
mem=[(a,b) for a,b in c.execute("select start,end from CUPTI_ACTIVITY_KIND_MEMCPY")] if tbl('CUPTI_ACTIVITY_KIND_MEMCPY') else []
h2d=one("select sum(bytes) from CUPTI_ACTIVITY_KIND_MEMCPY where copyKind=1") if tbl('CUPTI_ACTIVITY_KIND_MEMCPY') else 0
d2h=one("select sum(bytes) from CUPTI_ACTIVITY_KIND_MEMCPY where copyKind=2") if tbl('CUPTI_ACTIVITY_KIND_MEMCPY') else 0

bounds=[]
for t,col in (('CUPTI_ACTIVITY_KIND_KERNEL','start'),('CUPTI_ACTIVITY_KIND_RUNTIME','start'),('NVTX_EVENTS','start')):
    if tbl(t):
        lo=one(f"select min(start) from {t}"); hi=one(f"select max(end) from {t}")
        if lo: bounds.append((lo,hi))
lo=min(b[0] for b in bounds); hi=max(b[1] for b in bounds)
span=(hi-lo)/1e9

res={'sqlite':db,'traced_span_s':span,
     'device':{'kernel_union_s':union(ker)/1e9,'copy_union_s':union(mem)/1e9,
               'busy_union_s':union(ker+mem)/1e9,'launches':len(ker),'memcpys':len(mem),
               'h2d_bytes':h2d,'d2h_bytes':d2h,
               'traced':bool(ker or mem)},
     'stages':{}}
res['device']['idle_in_trace_s']=span-res['device']['busy_union_s'] if res['device']['traced'] else None
for nm,iv in ranges.items():
    res['stages'][nm]={'union_s':union(iv)/1e9,'instances':len(iv),
                       'inclusive_sum_s':sum(b-a for a,b in iv)/1e9}
json.dump(res,open(out,'w'),indent=2)
print(f"{db}: span={span:.3f}s stages={len(res['stages'])} kernels={len(ker)} memcpys={len(mem)} "
      f"busy={res['device']['busy_union_s']:.3f}s traced={res['device']['traced']}")
