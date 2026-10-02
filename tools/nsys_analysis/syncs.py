#!/usr/bin/env python3
"""Synchronisation and concurrency structure: streams, blocking APIs, and how
long the host actually waits at each one."""
import sqlite3,sys,collections
db=sys.argv[1]; c=sqlite3.connect(db)
S={r[0]:r[1] for r in c.execute("select id,value from StringIds")}
def one(q,*a):
    r=c.execute(q,a).fetchone(); return r[0] if r and r[0] is not None else 0
ms=lambda x:x/1e6; us=lambda x:x/1e3

print("="*74); print("STREAMS AND CONCURRENCY"); print("="*74)
for r in c.execute("""select streamId, count(*) n, sum(end-start) t from
                      CUPTI_ACTIVITY_KIND_KERNEL group by streamId"""):
    print("  kernels on stream %-6s n=%-5d %8.2f ms" % (r[0],r[1],ms(r[2])))
for r in c.execute("""select streamId, count(*) n, sum(end-start) t from
                      CUPTI_ACTIVITY_KIND_MEMCPY group by streamId"""):
    print("  memcpy  on stream %-6s n=%-5d %8.2f ms" % (r[0],r[1],ms(r[2])))
try:
    for r in c.execute("select streamId, isDefaultStream, priority from TARGET_INFO_CUDA_STREAM"):
        print("  declared stream %-6s default=%s priority=%s" % r)
except Exception: pass
ctx=one("select count(*) from (select distinct contextId from CUPTI_ACTIVITY_KIND_KERNEL)")
dev=[r[0] for r in c.execute("select distinct deviceId from CUPTI_ACTIVITY_KIND_KERNEL")]
print("  distinct CUDA contexts with kernels: %d ; devices: %s" % (ctx,dev))
tids=one("select count(*) from (select distinct globalTid from CUPTI_ACTIVITY_KIND_RUNTIME)")
print("  host threads issuing CUDA API calls: %d" % tids)

print()
print("="*74); print("BLOCKING CALLS: host wait vs the device work they cover"); print("="*74)
# pair each blocking runtime call with the device activity it correlates to
BL=("cudaMemcpy_v3020","cudaDeviceSynchronize_v3020","cudaEventSynchronize_v3020",
    "cudaStreamSynchronize_v3020","cudaMalloc_v3020","cudaFree_v3020","cudaLaunchKernel_v7000")
print("  %-30s%6s%11s%11s%11s%10s"%("call","n","host_ms","dev_ms","idle_ms","eff%"))
grand_h=grand_d=0
for nm in BL:
    ids=[i for i,v in S.items() if v==nm]
    if not ids: continue
    ph=",".join("?"*len(ids))
    rows=list(c.execute("select start,end from CUPTI_ACTIVITY_KIND_RUNTIME where nameId in (%s)"%ph,ids))
    if not rows: continue
    h=sum(b-a for a,b in rows)
    d=0
    for a,b in rows:
        d+=one("select sum(min(end,?)-max(start,?)) from CUPTI_ACTIVITY_KIND_MEMCPY where start<? and end>?",b,a,b,a)
        d+=one("select sum(min(end,?)-max(start,?)) from CUPTI_ACTIVITY_KIND_KERNEL where start<? and end>?",b,a,b,a)
    grand_h+=h; grand_d+=d
    print("  %-30s%6d%11.2f%11.2f%11.2f%10.1f"%(nm.replace("_v3020","").replace("_v7000",""),
          len(rows),ms(h),ms(d),ms(h-d),100.0*d/h if h else 0))
print("  %-30s%6s%11.2f%11.2f%11.2f%10.1f"%("TOTAL","",ms(grand_h),ms(grand_d),ms(grand_h-grand_d),
      100.0*grand_d/grand_h if grand_h else 0))
print("  (eff% = fraction of the host's blocked time the GPU was actually working)")

print()
print("="*74); print("THE 10 LONGEST INDIVIDUAL HOST STALLS"); print("="*74)
rows=list(c.execute("""select s.value, r.start, r.end-r.start d from CUPTI_ACTIVITY_KIND_RUNTIME r
                       join StringIds s on s.id=r.nameId order by d desc limit 10"""))
m0=one("""select min(e.start) from NVTX_EVENTS e left join StringIds s on s.id=e.textId
          where coalesce(e.text,s.value) like 'MOVIE%'""")
print("  %-34s%12s%12s"%("call","dur_ms","t_rel_ms"))
for nm,st,d in rows:
    print("  %-34s%12.2f%12.1f"%(nm[:34],ms(d),ms(st-m0)))

print()
print("="*74); print("cudaMemcpy SIZE DISTRIBUTION (all are synchronous/blocking)"); print("="*74)
import math
buckets=collections.Counter(); bt=collections.Counter()
for b,st,en,ck in c.execute("select bytes,start,end,copyKind from CUPTI_ACTIVITY_KIND_MEMCPY"):
    k=1<<int(math.log2(max(b,1)))
    buckets[(ck,k)]+=1; bt[(ck,k)]+=en-st
op={r[0]:r[2] for r in c.execute("select id,name,label from ENUM_CUDA_MEMCPY_OPER")}
print("  %-20s%14s%7s%11s%10s"%("direction","size>=","n","tot_ms","GB/s"))
for (ck,k),n in sorted(buckets.items(),key=lambda x:-bt[x[0]]):
    t=bt[(ck,k)]
    print("  %-20s%14s%7d%11.2f%10.2f"%(op.get(ck,"?")[:20],
          ("%d KiB"%(k//1024)) if k>=1024 else ("%d B"%k), n, ms(t), (k*n)/t if t else 0))
