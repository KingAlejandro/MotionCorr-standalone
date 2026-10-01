#!/usr/bin/env python3
import sqlite3,sys,json,collections
db=sys.argv[1]; c=sqlite3.connect(db)
def one(q,*a):
    r=c.execute(q,a).fetchone(); return r[0] if r and r[0] is not None else 0
R=collections.defaultdict(list)
for nm,a,b in c.execute("""select coalesce(e.text,s.value),e.start,e.end from NVTX_EVENTS e
    left join StringIds s on s.id=e.textId where e.end is not null"""):
    R[nm].append((a,b))
def u(iv):
    iv=sorted(iv);m=[]
    for a,b in iv:
        if m and a<=m[-1][1]: m[-1][1]=max(m[-1][1],b)
        else: m.append([a,b])
    return [tuple(x) for x in m]
MV="MOVIE (executeOwnMotionCorrection)"
mv=u(R[MV]); m0,m1=mv[0][0],mv[-1][1]
lo=one("select min(start) from CUPTI_ACTIVITY_KIND_RUNTIME")
hi=one("select max(end) from CUPTI_ACTIVITY_KIND_RUNTIME")
ker=u([(r[0],r[1]) for r in c.execute("select start,end from CUPTI_ACTIVITY_KIND_KERNEL")])
mem=u([(r[0],r[1]) for r in c.execute("select start,end from CUPTI_ACTIVITY_KIND_MEMCPY")])
def clip(iv,a,b): return sum(min(y,b)-max(x,a) for x,y in iv if x<b and y>a)
stages=[]
for nm,v in R.items():
    if nm==MV: continue
    w=u(v); wall=sum(b-a for a,b in w)
    if wall<200000: continue   # drop sub-0.2 ms markers
    kt=sum(clip(ker,a,b) for a,b in w); mt=sum(clip(mem,a,b) for a,b in w)
    stages.append(dict(name=nm,n=len(v),start=min(a for a,b in v)-lo,end=max(b for a,b in v)-lo,
                       wall=wall,kern=kt,mcpy=mt,segs=[[a-lo,b-lo] for a,b in w]))
stages.sort(key=lambda s:s["start"])
json.dump(dict(t0=0,t1=hi-lo,movie=[m0-lo,m1-lo],
               kernel=[[a-lo,b-lo] for a,b in ker],
               memcpy=[[a-lo,b-lo] for a,b in mem],
               stages=stages,
               tot_kern=sum(b-a for a,b in ker), tot_mcpy=sum(b-a for a,b in mem)),
          open(sys.argv[2],"w"))
print("wrote", sys.argv[2], len(stages),"stages", len(ker),"kernel-ivl", len(mem),"memcpy-ivl")
