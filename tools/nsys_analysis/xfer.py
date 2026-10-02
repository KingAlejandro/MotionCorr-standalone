#!/usr/bin/env python3
import sys, sqlite3,sys,glob,os
print("%-20s%6s%16s%11s%9s%26s"%("report","nH2D","H2D bytes","H2D ms","GB/s","pageable/pinned (src)"))
for db in sorted(glob.glob(sys.argv[1] if len(sys.argv) > 1 else "*.sqlite")):
    c=sqlite3.connect(db)
    mk={r[0]:r[2] for r in c.execute("select id,name,label from ENUM_CUDA_MEM_KIND")}
    try:
        rows=list(c.execute("""select srcKind,count(*),sum(bytes),sum(end-start)
                               from CUPTI_ACTIVITY_KIND_MEMCPY where copyKind=1 group by srcKind"""))
    except Exception: continue
    if not rows: continue
    n=sum(r[1] for r in rows); b=sum(r[2] for r in rows); t=sum(r[3] for r in rows)
    kinds=", ".join("%s:%d"%(mk.get(r[0],"?"),r[1]) for r in rows)
    print("%-20s%6d%16s%11.2f%9.2f%26s"%(os.path.basename(db)[:-7],n,format(b,chr(44)),t/1e6,b/t,kinds))
print()
print("The byte count is identical in every profile; the rate is not.")
print("A100 80GB PCIe is gen4 x16 = 31.5 GB/s theoretical, ~24 GB/s achievable PINNED.")
