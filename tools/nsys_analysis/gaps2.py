#!/usr/bin/env python3
"""GPU-idle attribution done properly: every idle interval is SPLIT at stage
boundaries and each piece charged to the stage covering it."""
import sqlite3, sys, collections
db=sys.argv[1]; c=sqlite3.connect(db)
def one(q,*a):
    r=c.execute(q,a).fetchone(); return r[0] if r and r[0] is not None else 0
ms=lambda x:x/1e6
R=collections.defaultdict(list)
for nm,a,b in c.execute("""select coalesce(e.text,s.value),e.start,e.end from NVTX_EVENTS e
                           left join StringIds s on s.id=e.textId where e.end is not null"""):
    R[nm].append((a,b))
def union(iv):
    iv=sorted(iv); m=[]
    for a,b in iv:
        if m and a<=m[-1][1]: m[-1][1]=max(m[-1][1],b)
        else: m.append([a,b])
    return [tuple(x) for x in m]
MOVIE="MOVIE (executeOwnMotionCorrection)"
mv=union(R[MOVIE]); m0,m1=mv[0][0],mv[-1][1]

# build a flat, non-overlapping segmentation of the whole timeline by stage
pts=set()
lo=one("select min(start) from CUPTI_ACTIVITY_KIND_RUNTIME")
hi=one("select max(end) from CUPTI_ACTIVITY_KIND_RUNTIME")
pts.update([lo,hi,m0,m1])
for nm,v in R.items():
    if nm==MOVIE: continue
    for a,b in v: pts.update([a,b])
pts=sorted(p for p in pts if lo<=p<=hi)
def owner(t):
    best=None;bl=None
    for nm,v in R.items():
        if nm==MOVIE: continue
        for a,b in v:
            if a<=t<b and (bl is None or (b-a)<bl): best,bl=nm,b-a
    if best: return best
    return "MOVIE: unmarked" if m0<=t<m1 else ("before movie" if t<m0 else "after movie")

iv=[(r[0],r[1]) for r in c.execute("select start,end from CUPTI_ACTIVITY_KIND_KERNEL")]
iv+=[(r[0],r[1]) for r in c.execute("select start,end from CUPTI_ACTIVITY_KIND_MEMCPY")]
gm=union(iv)
idle_iv=[];prev=lo
for a,b in gm:
    if a>prev: idle_iv.append((prev,a))
    prev=max(prev,b)
if prev<hi: idle_iv.append((prev,hi))

idle=collections.Counter(); busy=collections.Counter()
def charge(acc,iv):
    for a,b in iv:
        edges=[a]+[p for p in pts if a<p<b]+[b]
        for i in range(len(edges)-1):
            s,e=edges[i],edges[i+1]
            if e>s: acc[owner(s)]+=e-s
charge(idle,idle_iv); charge(busy,gm)
tot=sum(idle.values()); tb=sum(busy.values())
print("total traced %.1f ms = GPU busy %.1f ms + GPU idle %.1f ms" % (ms(hi-lo),ms(tb),ms(tot)))
print()
print("%-36s%11s%11s%10s%8s" % ("stage","gpu_busy_ms","gpu_idle_ms","wall_ms","idle%"))
for k in sorted(set(list(idle)+list(busy)), key=lambda k:-(idle[k]+busy[k])):
    w=idle[k]+busy[k]
    print("%-36s%11.1f%11.1f%10.1f%8.1f" % (k[:36],ms(busy[k]),ms(idle[k]),ms(w),100.0*idle[k]/w if w else 0))
print("%-36s%11.1f%11.1f%10.1f" % ("TOTAL",ms(tb),ms(tot),ms(hi-lo)))
