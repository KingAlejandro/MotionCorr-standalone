#!/usr/bin/env python3
"""Full-picture analysis of an nsys SQLite export for a single-GPU MotionCorr run."""
import sqlite3, sys, collections

DB = sys.argv[1]
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
Q = lambda s, *a: list(c.execute(s, a))
def one(s, *a):
    r = c.execute(s, a).fetchone()
    return r[0] if r and r[0] is not None else 0
def has(t):
    return bool(c.execute("select 1 from sqlite_master where name=?", (t,)).fetchone()) and \
           one(f"select count(*) from [{t}]") > 0

def us(ns): return ns / 1e3
def ms(ns): return ns / 1e6
def s_(ns): return ns / 1e9
def human(b):
    for u in ("B","KiB","MiB","GiB"):
        if abs(b) < 1024: return f"{b:,.1f} {u}"
        b /= 1024
    return f"{b:,.1f} TiB"

strings = {r[0]: r[1] for r in Q("select id, value from StringIds")}
P = print
def hdr(t): P("\n" + "="*78); P(t); P("="*78)

# ---------------------------------------------------------------- 0. session
hdr("0. SESSION / HARDWARE")
for r in Q("select * from TARGET_INFO_GPU"):
    d = dict(r)
    P(f"  GPU dev{d.get('id')}  {d.get('name')}  SMs={d.get('smCount')} "
      f"clk={d.get('clockRate',0)/1e6:.2f}GHz  mem={human(d.get('memoryBandwidth',0))}/s bw "
      f"L2={human(d.get('l2CacheSize',0))}  cc={d.get('computeMajor')}.{d.get('computeMinor')}")
for r in Q("select name, value from TARGET_INFO_SYSTEM_ENV where name in "
           "('Hostname','CpuCores','CudaDriverVersion','KernelVersion','OsName')"):
    P(f"  {r[0]:<20} {r[1]}")

# traced window: first to last activity of any kind
bounds = []
for t, cs, ce in (("CUPTI_ACTIVITY_KIND_KERNEL","start","end"),
                  ("CUPTI_ACTIVITY_KIND_MEMCPY","start","end"),
                  ("CUPTI_ACTIVITY_KIND_RUNTIME","start","end"),
                  ("OSRT_API","start","end"),
                  ("COMPOSITE_EVENTS","start","start")):
    if has(t):
        bounds.append((one(f"select min({cs}) from [{t}]"), one(f"select max({ce}) from [{t}]")))
T0 = min(b[0] for b in bounds); T1 = max(b[1] for b in bounds)
SPAN = T1 - T0
P(f"\n  traced span          {s_(SPAN):.4f} s   [{T0} .. {T1}] ns")
P(f"  processes={one('select count(*) from (select distinct globalPid from PROCESSES)')}"
  f"  threads_seen={one('select count(*) from (select distinct globalTid from ThreadNames)')}")

# ---------------------------------------------------------------- 1. GPU busy
hdr("1. GPU OCCUPANCY OF THE WALL CLOCK  (device-side intervals, union)")
iv = []
if has("CUPTI_ACTIVITY_KIND_KERNEL"):
    iv += [(r[0], r[1], "kernel") for r in Q("select start,end from CUPTI_ACTIVITY_KIND_KERNEL")]
if has("CUPTI_ACTIVITY_KIND_MEMCPY"):
    iv += [(r[0], r[1], "memcpy") for r in Q("select start,end from CUPTI_ACTIVITY_KIND_MEMCPY")]
if has("CUPTI_ACTIVITY_KIND_MEMSET"):
    iv += [(r[0], r[1], "memset") for r in Q("select start,end from CUPTI_ACTIVITY_KIND_MEMSET")]
iv.sort()
def union(ivs):
    tot = 0; merged = []
    for s, e, *_ in ivs:
        if merged and s <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], e)
        else: merged.append([s, e])
    for s, e in merged: tot += e - s
    return tot, merged
busy, merged = union(iv)
k_tot = one("select sum(end-start) from CUPTI_ACTIVITY_KIND_KERNEL")
m_tot = one("select sum(end-start) from CUPTI_ACTIVITY_KIND_MEMCPY")
P(f"  kernel time (sum)        {ms(k_tot):10.3f} ms   {100*k_tot/SPAN:5.1f}% of span")
P(f"  memcpy time (sum)        {ms(m_tot):10.3f} ms   {100*m_tot/SPAN:5.1f}% of span")
P(f"  GPU busy (union, no dbl) {ms(busy):10.3f} ms   {100*busy/SPAN:5.1f}% of span")
P(f"  GPU IDLE                 {ms(SPAN-busy):10.3f} ms   {100*(SPAN-busy)/SPAN:5.1f}% of span")
P(f"  overlap (kern+mcpy-union){ms(k_tot+m_tot-busy):10.3f} ms  <- concurrency actually achieved")

P("\n  Largest GPU idle gaps (device doing nothing):")
gaps = []
prev = merged[0][1] if merged else T0
gaps.append((merged[0][0]-T0, T0, merged[0][0])) if merged else None
for s, e in merged[1:]:
    gaps.append((s - prev, prev, s)); prev = e
gaps.append((T1 - prev, prev, T1))
gaps.sort(reverse=True)
P(f"    {'dur_ms':>10}  {'start_rel_ms':>13}  cumulative%")
cum = 0
for d, s, e in gaps[:15]:
    cum += d
    P(f"    {ms(d):10.3f}  {ms(s-T0):13.3f}  {100*cum/(SPAN-busy):8.1f}%")
P(f"    ({len(gaps)} gaps total, {ms(SPAN-busy):.1f} ms idle)")

# ---------------------------------------------------------------- 2. kernels
hdr("2. KERNEL CENSUS  (sorted by total device time)")
rows = Q("""select shortName, count(*) n, sum(end-start) tot, avg(end-start) avg,
                   min(end-start) mn, max(end-start) mx,
                   gridX*gridY*gridZ gx, blockX*blockY*blockZ bx,
                   registersPerThread reg, staticSharedMemory ssm, streamId
            from CUPTI_ACTIVITY_KIND_KERNEL group by shortName order by tot desc""")
P(f"  {'kernel':<44}{'n':>5}{'tot_ms':>10}{'avg_us':>10}{'max_us':>9}{'%gpu':>7}{'grid':>8}{'blk':>6}{'reg':>5}")
for r in rows:
    nm = strings.get(r["shortName"], str(r["shortName"]))
    nm = nm.split("(")[0][:43]
    P(f"  {nm:<44}{r['n']:>5}{ms(r['tot']):>10.3f}{us(r['avg']):>10.1f}{us(r['mx']):>9.1f}"
      f"{100*r['tot']/k_tot:>7.1f}{r['gx']:>8}{r['bx']:>6}{r['reg']:>5}")
P(f"  {'TOTAL':<44}{one('select count(*) from CUPTI_ACTIVITY_KIND_KERNEL'):>5}{ms(k_tot):>10.3f}")

# ---------------------------------------------------------------- 3. memory
hdr("3. HOST<->DEVICE TRAFFIC  (bytes are contention-immune; rates are not)")
oper = {r[0]: r[2] for r in Q("select id,name,label from ENUM_CUDA_MEMCPY_OPER")}
mk   = {r[0]: r[2] for r in Q("select id,name,label from ENUM_CUDA_MEM_KIND")}
rows = Q("""select copyKind, srcKind, dstKind, count(*) n, sum(bytes) b,
                   sum(end-start) t, max(bytes) mxb
            from CUPTI_ACTIVITY_KIND_MEMCPY group by copyKind, srcKind, dstKind
            order by b desc""")
P(f"  {'direction':<26}{'src':<10}{'dst':<10}{'n':>5}{'bytes':>15}{'ms':>9}{'GB/s':>8}")
tb = 0
for r in rows:
    tb += r["b"]
    gbs = r["b"]/r["t"] if r["t"] else 0   # bytes/ns == GB/s
    P(f"  {oper.get(r['copyKind'],'?')[:25]:<26}{mk.get(r['srcKind'],'?')[:9]:<10}"
      f"{mk.get(r['dstKind'],'?')[:9]:<10}{r['n']:>5}{r['b']:>15,}{ms(r['t']):>9.2f}{gbs:>8.2f}")
P(f"  {'TOTAL':<26}{'':<20}{one('select count(*) from CUPTI_ACTIVITY_KIND_MEMCPY'):>5}"
  f"{tb:>15,}{ms(m_tot):>9.2f}")
P(f"\n  total moved over PCIe+device: {human(tb)}")
pageable = one("select count(*) from CUPTI_ACTIVITY_KIND_MEMCPY where srcKind=1 or dstKind=1")
P(f"  copies touching PAGEABLE host memory: {pageable} "
  f"(pageable blocks the CPU and cannot overlap; pinned can)")

# ---------------------------------------------------------------- 4. API
hdr("4. CUDA RUNTIME API  (host-side cost; this is where the CPU actually waits)")
rows = Q("""select nameId, count(*) n, sum(end-start) tot, avg(end-start) avg, max(end-start) mx
            from CUPTI_ACTIVITY_KIND_RUNTIME group by nameId order by tot desc limit 25""")
api_tot = one("select sum(end-start) from CUPTI_ACTIVITY_KIND_RUNTIME")
P(f"  {'api':<42}{'n':>6}{'tot_ms':>10}{'avg_us':>10}{'max_us':>10}{'%span':>8}")
for r in rows:
    nm = strings.get(r["nameId"], "?")[:41]
    P(f"  {nm:<42}{r['n']:>6}{ms(r['tot']):>10.3f}{us(r['avg']):>10.1f}"
      f"{us(r['mx']):>10.1f}{100*r['tot']/SPAN:>8.1f}")
P(f"  {'(sum of all API, wall-overlapping)':<42}{'':<6}{ms(api_tot):>10.3f}")

# ---------------------------------------------------------------- 5. syncs
hdr("5. SYNCHRONIZATION CENSUS")
st = {r[0]: r[2] for r in Q("select id,name,label from ENUM_CUPTI_SYNC_TYPE")}
rows = Q("""select syncType, count(*) n, sum(end-start) tot, avg(end-start) avg, max(end-start) mx
            from CUPTI_ACTIVITY_KIND_SYNCHRONIZATION group by syncType order by tot desc""")
P("  device-side synchronization records:")
P(f"  {'syncType':<40}{'n':>6}{'tot_ms':>10}{'avg_us':>10}{'max_us':>10}")
for r in rows:
    P(f"  {st.get(r['syncType'],'?')[:39]:<40}{r['n']:>6}{ms(r['tot']):>10.3f}"
      f"{us(r['avg']):>10.1f}{us(r['mx']):>10.1f}")
P("\n  host-side blocking API calls (the CPU stall these cause):")
for pat in ("cudaDeviceSynchronize","cudaStreamSynchronize","cudaEventSynchronize",
            "cudaMemcpy","cudaFree","cudaMalloc","cudaHostAlloc","cudaLaunchKernel"):
    ids = [i for i, v in strings.items() if v.startswith(pat)]
    if not ids: continue
    ph = ",".join("?"*len(ids))
    n = one(f"select count(*) from CUPTI_ACTIVITY_KIND_RUNTIME where nameId in ({ph})", *ids)
    t = one(f"select sum(end-start) from CUPTI_ACTIVITY_KIND_RUNTIME where nameId in ({ph})", *ids)
    if n: P(f"    {pat:<26}{n:>6} calls{ms(t):>10.3f} ms{100*t/SPAN:>8.1f}% of span")

# ---------------------------------------------------------------- 6. NVTX
if has("NVTX_EVENTS"):
    hdr("6. NVTX STAGE BREAKDOWN  (host wall per pipeline stage)")
    rows = Q("""select coalesce(e.text, s.value) nm, count(*) n,
                       sum(e.end-e.start) tot, min(e.start) first_start, max(e.end) last_end
                from NVTX_EVENTS e left join StringIds s on s.id=e.textId
                where e.end is not null group by nm order by tot desc""")
    P(f"  {'stage':<42}{'n':>5}{'tot_ms':>10}{'%span':>8}{'first_rel_ms':>14}")
    for r in rows:
        P(f"  {str(r['nm'])[:41]:<42}{r['n']:>5}{ms(r['tot']):>10.3f}"
          f"{100*r['tot']/SPAN:>8.1f}{ms(r['first_start']-T0):>14.3f}")

    # GPU work attributed into each top-level stage window
    P("\n  GPU work inside each stage window (kernel+memcpy device time):")
    P(f"  {'stage':<42}{'gpu_ms':>10}{'kern_ms':>10}{'mcpy_ms':>10}{'stage_ms':>10}{'gpu%':>7}")
    for r in rows:
        if r["n"] != 1: continue
        a, b = r["first_start"], r["last_end"]
        kk = one("select sum(min(end,?)-max(start,?)) from CUPTI_ACTIVITY_KIND_KERNEL "
                 "where start<? and end>?", b, a, b, a)
        mm = one("select sum(min(end,?)-max(start,?)) from CUPTI_ACTIVITY_KIND_MEMCPY "
                 "where start<? and end>?", b, a, b, a)
        dur = b - a
        if dur <= 0: continue
        P(f"  {str(r['nm'])[:41]:<42}{ms(kk+mm):>10.3f}{ms(kk):>10.3f}{ms(mm):>10.3f}"
          f"{ms(dur):>10.3f}{100*(kk+mm)/dur:>7.1f}")

# ---------------------------------------------------------------- 7. VRAM
if has("CUDA_GPU_MEMORY_USAGE_EVENTS"):
    hdr("7. DEVICE MEMORY OVER TIME")
    ev = Q("select start, bytes, memoryOperationType, memKind from CUDA_GPU_MEMORY_USAGE_EVENTS order by start")
    opn = {r[0]: r[2] for r in Q("select id,name,label from ENUM_CUDA_DEV_MEM_EVENT_OPER")}
    cur = 0; peak = 0; peak_t = 0; nalloc = 0; nfree = 0; total_alloced = 0
    for e in ev:
        if opn.get(e["memoryOperationType"], "").lower().startswith("alloc"):
            cur += e["bytes"]; nalloc += 1; total_alloced += e["bytes"]
        else:
            cur -= e["bytes"]; nfree += 1
        if cur > peak: peak, peak_t = cur, e["start"]
    P(f"  allocations={nalloc}  frees={nfree}  churn(sum of allocs)={human(total_alloced)}")
    P(f"  PEAK resident VRAM = {human(peak)}  at t={ms(peak_t-T0):.1f} ms")
    P(f"  residual at end    = {human(cur)}")
    rows = Q("""select memKind, count(*) n, sum(bytes) b from CUDA_GPU_MEMORY_USAGE_EVENTS
                where memoryOperationType=0 group by memKind order by b desc""")
    for r in rows:
        P(f"    {mk.get(r['memKind'],'?'):<20} n={r['n']:<5} {human(r['b'])}")

# ---------------------------------------------------------------- 8. threads
hdr("8. CPU THREAD ACTIVITY (sampled)")
if has("COMPOSITE_EVENTS"):
    tsN = {r[0]: r[2] for r in Q("select id,name,label from ENUM_SAMPLING_THREAD_STATE")}
    tot = one("select count(*) from COMPOSITE_EVENTS")
    P(f"  total CPU samples: {tot}  over {s_(SPAN):.3f} s")
    P("\n  by thread state:")
    for r in Q("select threadState, count(*) n from COMPOSITE_EVENTS group by threadState order by n desc"):
        P(f"    {str(tsN.get(r[0],r[0]))[:34]:<36}{r[1]:>7}{100*r[1]/tot:>7.1f}%")
    P("\n  by thread (top 12):")
    names = {r[0]: strings.get(r[1], "?") for r in Q("select globalTid, nameId from ThreadNames")}
    for r in Q("select globalTid, count(*) n from COMPOSITE_EVENTS group by globalTid order by n desc limit 12"):
        P(f"    tid {r[0]&0xffffff:<10}{names.get(r[0],'?')[:22]:<24}{r[1]:>7}{100*r[1]/tot:>7.1f}%")

# ---------------------------------------------------------------- 9. OSRT
if has("OSRT_API"):
    hdr("9. OS RUNTIME  (where the process blocks outside CUDA)")
    rows = Q("""select nameId, count(*) n, sum(end-start) tot, avg(end-start) avg, max(end-start) mx
                from OSRT_API group by nameId order by tot desc limit 18""")
    P(f"  {'call':<34}{'n':>7}{'tot_ms':>11}{'avg_us':>11}{'max_ms':>10}")
    for r in rows:
        P(f"  {strings.get(r['nameId'],'?')[:33]:<34}{r['n']:>7}{ms(r['tot']):>11.2f}"
          f"{us(r['avg']):>11.1f}{ms(r['mx']):>10.2f}")
P("")
