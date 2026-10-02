#!/usr/bin/env python3
import sqlite3,sys,json,collections
c=sqlite3.connect(sys.argv[1])
def one(q,*a):
    r=c.execute(q,a).fetchone(); return r[0] if r and r[0] is not None else 0
lo=one("select min(start) from CUPTI_ACTIVITY_KIND_RUNTIME")
hi=one("select max(end) from CUPTI_ACTIVITY_KIND_RUNTIME")
opn={r[0]:r[2] for r in c.execute("select id,name,label from ENUM_CUDA_DEV_MEM_EVENT_OPER")}
cur=0; pts=[(0,0)]; peak=0; peakt=0
for st,by,op in c.execute("""select start,bytes,memoryOperationType from
                             CUDA_GPU_MEMORY_USAGE_EVENTS order by start"""):
    cur += by if opn.get(op,"").lower().startswith("alloc") else -by
    pts.append(((st-lo)/1e6, cur))
    if cur>peak: peak,peakt=cur,(st-lo)/1e6
pts.append(((hi-lo)/1e6,cur))
R=collections.defaultdict(list)
for nm,a,b in c.execute("""select coalesce(e.text,s.value),e.start,e.end from NVTX_EVENTS e
    left join StringIds s on s.id=e.textId where e.end is not null"""):
    R[nm].append(((a-lo)/1e6,(b-lo)/1e6))
stages=[]
for nm,v in R.items():
    if nm.startswith("MOVIE"): continue
    a=min(x for x,y in v); b=max(y for x,y in v)
    if b-a<8: continue
    stages.append([nm,a,b])
stages.sort(key=lambda s:s[1])
json.dump(dict(pts=pts,peak=peak,peakt=peakt,span=(hi-lo)/1e6,stages=stages,
               movie=[min(x for x,y in R["MOVIE (executeOwnMotionCorrection)"]),
                      max(y for x,y in R["MOVIE (executeOwnMotionCorrection)"])]),
          open(sys.argv[2],"w"))
print("peak %.2f GiB at %.0f ms; %d points"%(peak/2**30,peakt,len(pts)))
