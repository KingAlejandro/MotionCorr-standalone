#!/usr/bin/env python3
"""Per-arm device-memory timeline, allocation census and GPU activity, from ONE capture.

Everything here comes from the single sqlite named on the command line. Nothing is
combined with, or subtracted from, another run.
"""
import collections,json,sqlite3,sys
db,arm,out=sys.argv[1],sys.argv[2],sys.argv[3]
NBINS=int(sys.argv[4]) if len(sys.argv)>4 else 200
c=sqlite3.connect(db)
def tbl(n): return c.execute("select count(*) from sqlite_master where type='table' and name=?",(n,)).fetchone()[0]>0
def one(q):
    try:
        r=c.execute(q).fetchone(); return r[0] if r and r[0] is not None else 0
    except sqlite3.OperationalError: return 0

ker=[(a,b) for a,b in c.execute("select start,end from CUPTI_ACTIVITY_KIND_KERNEL")] if tbl('CUPTI_ACTIVITY_KIND_KERNEL') else []
mem=[(a,b) for a,b in c.execute("select start,end from CUPTI_ACTIVITY_KIND_MEMCPY")] if tbl('CUPTI_ACTIVITY_KIND_MEMCPY') else []
lo=min([x[0] for x in ker+mem]+[one("select min(start) from CUPTI_ACTIVITY_KIND_RUNTIME") or 1<<62])
hi=max([x[1] for x in ker+mem]+[one("select max(end) from CUPTI_ACTIVITY_KIND_RUNTIME")])
span=(hi-lo)/1e9

# ---- device memory timeline, running total over alloc/free events
# id 0 = Allocation, 1 = Deallocation. Match on the *label* ("Allocation"), not the
# name ("CUDA_DEV_MEM_EVENT_OPR_ALLOCATION") -- the name does not start with "alloc".
opn={r[0]:(r[2] or r[1] or "") for r in c.execute("select id,name,label from ENUM_CUDA_DEV_MEM_EVENT_OPER")} if tbl('ENUM_CUDA_DEV_MEM_EVENT_OPER') else {}
pts=[]; cur=0; peak=0; peakt=0.0
alloc_sizes=collections.Counter(); n_alloc=0; n_free=0
if tbl('CUDA_GPU_MEMORY_USAGE_EVENTS'):
    for st,by,op in c.execute("select start,bytes,memoryOperationType from CUDA_GPU_MEMORY_USAGE_EVENTS order by start"):
        lab=str(opn.get(op,op)).lower()
        isalloc = ("dealloc" not in lab) and ("alloc" in lab or op==0)
        cur += by if isalloc else -by
        if isalloc: alloc_sizes[by]+=1; n_alloc+=1
        else: n_free+=1
        pts.append([round((st-lo)/1e9,4), cur])
        if cur>peak: peak,peakt=cur,(st-lo)/1e9

# ---- the quantity that actually matters here: the floor BETWEEN movies.
# Sample the running total on a fine grid, then take the minimum within the
# steady-state middle of the run (skip warm-up and teardown).
floor=None; steady=[]
if pts:
    t0,t1=span*0.25,span*0.85
    steady=[v for t,v in pts if t0<=t<=t1]
    floor=min(steady) if steady else None

# ---- GPU activity over time, 200 bins, union of kernel+copy within each bin
NB=NBINS; bins=[0.0]*NB
def add(iv):
    for a,b in iv:
        a=(a-lo)/1e9; b=(b-lo)/1e9
        i0=max(0,min(NB-1,int(a/span*NB))); i1=max(0,min(NB-1,int(b/span*NB)))
        for i in range(i0,i1+1):
            s=max(a,i*span/NB); e=min(b,(i+1)*span/NB)
            if e>s: bins[i]+=e-s
add(ker); add(mem)
w=span/NB
occ=[round(min(1.0,x/w),4) for x in bins]

json.dump({'arm':arm,'sqlite':db,'span_s':span,
           'vram':{'points':pts,'peak_bytes':peak,'peak_t_s':round(peakt,4),
                   'retained_floor_bytes':floor,
                   'alloc_events':n_alloc,'free_events':n_free,
                   'distinct_sizes':[[s,n] for s,n in alloc_sizes.most_common(14)]},
           'gpu':{'occupancy_bins':occ,'bin_s':w,'kernels':len(ker),'memcpys':len(mem)}},
          open(out,'w'))
print(f"{arm:14s} span={span:7.3f}s peak={peak/2**20:8.1f}MiB floor={(floor or 0)/2**20:8.1f}MiB "
      f"allocs={n_alloc:6d} frees={n_free:6d} kernels={len(ker)}")
