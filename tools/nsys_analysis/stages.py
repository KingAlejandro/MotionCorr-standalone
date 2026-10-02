#!/usr/bin/env python3
"""Per-stage accounting. Multi-instance stages (OpenMP-parallel ones) are
unioned, and GPU device time is clipped into each stage's window."""
import sqlite3, sys, collections
db = sys.argv[1]
c = sqlite3.connect(db); c.row_factory = sqlite3.Row
S = {r[0]: r[1] for r in c.execute("select id,value from StringIds")}
def one(q, *a):
    r = c.execute(q, a).fetchone(); return r[0] if r and r[0] is not None else 0

KER = [(r[0], r[1]) for r in c.execute("select start,end from CUPTI_ACTIVITY_KIND_KERNEL")]
MEM = [(r[0], r[1], r[2]) for r in c.execute(
        "select start,end,bytes from CUPTI_ACTIVITY_KIND_MEMCPY")]
lo = min(one("select min(start) from CUPTI_ACTIVITY_KIND_KERNEL"),
         one("select min(start) from CUPTI_ACTIVITY_KIND_RUNTIME"))
hi = max(one("select max(end) from CUPTI_ACTIVITY_KIND_KERNEL"),
         one("select max(end) from CUPTI_ACTIVITY_KIND_RUNTIME"))

ranges = collections.defaultdict(list)
for r in c.execute("""select coalesce(e.text,s.value) nm, e.start, e.end, e.globalTid
                      from NVTX_EVENTS e left join StringIds s on s.id=e.textId
                      where e.end is not null"""):
    ranges[r[0]].append((r[1], r[2], r[3]))

def union(iv):
    iv = sorted((a, b) for a, b, *_ in iv); m = []
    for a, b in iv:
        if m and a <= m[-1][1]: m[-1][1] = max(m[-1][1], b)
        else: m.append([a, b])
    return m, sum(b-a for a, b in m)

def clip(iv, wins):
    t = 0; n = 0; by = 0
    for w0, w1 in wins:
        for row in iv:
            a, b = row[0], row[1]
            if a < w1 and b > w0:
                t += min(b, w1) - max(a, w0); n += 1
                if len(row) > 2: by += row[2]
    return t, n, by

MOVIE = "MOVIE (executeOwnMotionCorrection)"
order = sorted(ranges, key=lambda k: min(a for a, b, t in ranges[k]))
ms = lambda x: x/1e6
print("span(traced) = %.1f ms" % ms(hi-lo))
print()
print("%-40s%4s%10s%9s%10s%9s%8s%9s" %
      ("stage (in first-start order)", "n", "wall_ms", "kern_ms", "mcpy_ms", "H2D_MiB", "gpu%", "cpu_ms"))
for nm in order:
    wins, wall = union(ranges[nm])
    kt, kn, _ = clip(KER, wins)
    mt, mn, mb = clip(MEM, wins)
    gpu = kt + mt
    mark = "  " if nm != MOVIE else "* "
    print("%s%-38s%4d%10.1f%9.1f%10.1f%9.1f%8.1f%9.1f" %
          (mark, str(nm)[:38], len(ranges[nm]), ms(wall), ms(kt), ms(mt),
           mb/1048576.0, 100.0*gpu/wall if wall else 0, ms(wall-gpu)))

mw, mwall = union(ranges[MOVIE]) if MOVIE in ranges else ([], 0)
if mw:
    m0, m1 = mw[0][0], mw[-1][1]
    print()
    print("  before first movie : %8.1f ms   (process+CUDA init, arg parse, gain probe)" % ms(m0-lo))
    print("  inside movie       : %8.1f ms" % ms(mwall))
    print("  after last movie   : %8.1f ms   (STAR, logfile.pdf/ghostscript, teardown)" % ms(hi-m1))
