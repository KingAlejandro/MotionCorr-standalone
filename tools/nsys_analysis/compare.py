#!/usr/bin/env python3
"""Cross-report comparison: how much of the measured span is the profiler?"""
import sys, sqlite3, glob, os
rows=[]
for db in sorted(glob.glob(sys.argv[1] if len(sys.argv) > 1 else "*.sqlite")):
    c=sqlite3.connect(db); c.row_factory=sqlite3.Row
    def one(s,*a):
        try:
            r=c.execute(s,*a).fetchone(); return r[0] if r and r[0] is not None else 0
        except Exception: return 0
    tag=os.path.basename(db).replace(".sqlite","")
    k=one("select sum(end-start) from CUPTI_ACTIVITY_KIND_KERNEL")
    m=one("select sum(end-start) from CUPTI_ACTIVITY_KIND_MEMCPY")
    kb=one("select sum(bytes) from CUPTI_ACTIVITY_KIND_MEMCPY where copyKind=1")
    nk=one("select count(*) from CUPTI_ACTIVITY_KIND_KERNEL")
    nm=one("select count(*) from CUPTI_ACTIVITY_KIND_MEMCPY")
    lo=[]; hi=[]
    for t in ("CUPTI_ACTIVITY_KIND_KERNEL","CUPTI_ACTIVITY_KIND_RUNTIME","OSRT_API"):
        a=one(f"select min(start) from {t}"); b=one(f"select max(end) from {t}")
        if a: lo.append(a); hi.append(b)
    span=(max(hi)-min(lo)) if lo else 0
    ovh=one("select sum(end-start) from PROFILER_OVERHEAD")
    mod=one("select sum(end-start) from CUPTI_ACTIVITY_KIND_RUNTIME r join StringIds s "
            "on s.id=r.nameId where s.value like 'cuModuleLoad%'")
    mcpy_api=one("select sum(end-start) from CUPTI_ACTIVITY_KIND_RUNTIME r join StringIds s "
                 "on s.id=r.nameId where s.value like 'cudaMemcpy%'")
    rows.append((tag,span/1e6,k/1e6,m/1e6,nk,nm,kb,mod/1e6,mcpy_api/1e6,ovh/1e6))
print(f"{'report':<22}{'span_ms':>10}{'kern_ms':>9}{'mcpy_ms':>9}{'nkern':>7}{'nmcpy':>7}"
      f"{'H2D_bytes':>15}{'modLoad_ms':>11}{'memcpyAPI':>10}{'nsysOvh':>9}")
for r in rows:
    print(f"{r[0]:<22}{r[1]:>10.1f}{r[2]:>9.2f}{r[3]:>9.2f}{r[4]:>7}{r[5]:>7}{r[6]:>15,}"
          f"{r[7]:>11.1f}{r[8]:>10.1f}{r[9]:>9.1f}")
