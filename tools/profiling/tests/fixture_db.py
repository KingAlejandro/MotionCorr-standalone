"""Known-answer Nsight Systems SQLite fixture on the real nsys 2024.6.2 schema.

The schema comes from fixtures/nsys_2024_6_schema.sql, captured with
`nsys export --type sqlite` on 4GPUs. Rows describe two movies; every derived
quantity below is worked out by hand in EXPECTED. Times are ns.

  movie 0  [100,1000]: setup [100,200]  A [200,600] (sub SUB [250,300])  B [600,1000]
  movie 1 [1100,2000]: setup [1100,1200] A [1200,1500]                    B [1500,2000]
  kernels  k_alpha [150,250] [700,800]; k_beta [220,300] [1300,1350]
  copies   HtoD pageable->device [280,400] 1000 B; DtoH device->pinned [790,850] 500 B
  runtime  window 50..2100 (cudaMalloc at 50, cudaFree at 2090)
"""
from __future__ import annotations

import os
import sqlite3

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "nsys_2024_6_schema.sql")
TID, OTHER_TID, PID = 100, 200, 7

STRINGS = {1: "k_alpha", 2: "k_beta", 3: "cudaMemcpy_v3020", 4: "cudaDeviceSynchronize_v3020",
           5: "cudaFree_v3020", 6: "cudaMalloc_v3020", 7: "cudaLaunchKernel_v7000", 8: "motioncorr",
           9: "k_alpha(float*)", 10: "k_beta(int)", 11: "main", 12: "libfoo.so", 13: "0x7f00", 14: "do_work",
           15: "[kernel.kallsyms]", 16: "page_fault"}

NVTX = [(100, 1000, "movie"), (100, 200, "setup"), (200, 600, "A"), (250, 300, "SUB"), (600, 1000, "B"),
        (1100, 2000, "movie"), (1100, 1200, "setup"), (1200, 1500, "A"), (1500, 2000, "B")]
KERNELS = [(150, 250, 1), (220, 300, 2), (700, 800, 1), (1300, 1350, 2)]
COPIES = [(280, 400, 1000, 1, 0, 2), (790, 850, 500, 2, 2, 1)]  # start end bytes copyKind src dst
RUNTIME = [(50, 60, 6), (140, 150, 7), (215, 220, 7), (270, 410, 3), (650, 820, 4), (900, 950, 5),
           (1290, 1300, 7), (2090, 2100, 5)]
MEMORY = [  # start, op(0 alloc/1 free), kind(2 Device, 5 Device Static), address, bytes
    (95, 0, 5, 0x99, 8), (96, 0, 5, 0x99, 8), (210, 0, 2, 0x10, 100), (300, 0, 2, 0x20, 50),
    (500, 1, 2, 0x10, 100), (1250, 0, 2, 0x30, 200), (1600, 1, 2, 0x20, 50), (1900, 1, 2, 0x30, 200)]

EXPECTED = {
    "window": (50, 2100),
    "segments": [("before first movie", 50, 100), ("setup", 100, 200), ("A", 200, 600), ("B", 600, 1000),
                 ("between movies", 1000, 1100), ("setup", 1100, 1200), ("A", 1200, 1500), ("B", 1500, 2000),
                 ("after last movie", 2000, 2100)],
    "busy": [0, 50, 200, 150, 0, 0, 50, 0, 0],
    "idle": [50, 50, 200, 250, 100, 100, 250, 500, 100],
    "idle_intervals": [1, 1, 1, 2, 1, 1, 2, 1, 1],
    "max_idle_interval": [50, 50, 200, 150, 100, 100, 150, 500, 100],
    "kernel_busy": [0, 50, 100, 100, 0, 0, 50, 0, 0],
    "copy_busy": [0, 0, 120, 60, 0, 0, 0, 0, 0],
    "kernels": [0, 1, 1, 1, 0, 0, 1, 0, 0],
    "sync_calls": [0, 0, 1, 2, 0, 0, 0, 0, 1],
    "sync_blocked_idle": [0, 0, 10, 100, 0, 0, 0, 0, 10],
    "malloc": [1, 0, 0, 0, 0, 0, 0, 0, 0],
    "free": [0, 0, 0, 1, 0, 0, 0, 0, 1],
    "segment_mem_peak": [8, 8, 158, 58, 58, 58, 258, 258, 8],
    "totals": {"busy_ns": 450, "idle_ns": 1600, "kernel_sum_ns": 330, "kernel_union_ns": 300,
               "copy_sum_ns": 180, "copy_union_ns": 180, "overlap_ns": 30, "kernels": 4, "copies": 2,
               "copy_bytes": 1500, "movies": 2},
    "mem_peak": 258, "mem_peak_time": 1250, "mem_residual": 8,
}


def _insert(con, table, **vals):
    cols = con.execute("pragma table_info([%s])" % table).fetchall()
    row = {}
    for _, name, _, notnull, _, _ in cols:
        if name in vals:
            row[name] = vals[name]
        elif notnull:
            row[name] = 0
    con.execute("insert into [%s] (%s) values (%s)" % (table, ",".join(row), ",".join("?" * len(row))),
                list(row.values()))


def build(path: str, drop_tables=(), drop_nvtx=False, extra=None) -> str:
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    with open(SCHEMA) as f:
        con.executescript(f.read())
    for i, v in STRINGS.items():
        _insert(con, "StringIds", id=i, value=v)
    _insert(con, "ThreadNames", nameId=8, globalTid=TID)
    _insert(con, "PROCESSES", globalPid=PID, pid=1234, name="/x/motioncorr")
    if not drop_nvtx:
        for s, e, t in NVTX:
            _insert(con, "NVTX_EVENTS", start=s, end=e, eventType=59, text=t, globalTid=TID)
        # A range on another thread and an instantaneous mark must not disturb the tiling.
        _insert(con, "NVTX_EVENTS", start=300, end=400, eventType=59, text="worker", globalTid=OTHER_TID)
        _insert(con, "NVTX_EVENTS", start=150, end=None, eventType=34, text="mark", globalTid=TID)
    for s, e, n in KERNELS:
        _insert(con, "CUPTI_ACTIVITY_KIND_KERNEL", start=s, end=e, shortName=n, demangledName=n + 8,
                streamId=7, deviceId=0, gridX=4, gridY=1, gridZ=1, blockX=128, blockY=1, blockZ=1,
                registersPerThread=32)
    for s, e, b, k, src, dst in COPIES:
        _insert(con, "CUPTI_ACTIVITY_KIND_MEMCPY", start=s, end=e, bytes=b, copyKind=k, srcKind=src,
                dstKind=dst, streamId=7)
    for s, e, n in RUNTIME:
        _insert(con, "CUPTI_ACTIVITY_KIND_RUNTIME", start=s, end=e, nameId=n, globalTid=TID, eventClass=1)
    for s, op, kind, addr, b in MEMORY:
        _insert(con, "CUDA_GPU_MEMORY_USAGE_EVENTS", start=s, globalPid=PID, deviceId=0, contextId=1,
                address=addr, bytes=b, memKind=kind, memoryOperationType=op)
    # CPU samples: two on the main thread, one without a callchain.
    for cid, tid in ((1, TID), (2, TID), (3, TID)):
        _insert(con, "COMPOSITE_EVENTS", id=cid, start=100 + cid, globalTid=tid)
    for cid, sym, mod, km, depth in ((1, 11, 12, 0, 2), (1, 14, 12, 0, 1), (1, 16, 15, 1, 0),
                                     (2, 11, 12, 0, 1), (2, 13, 12, 0, 0)):
        _insert(con, "SAMPLING_CALLCHAINS", id=cid, symbol=sym, module=mod, kernelMode=km, stackDepth=depth)
    if extra:
        extra(con, _insert)
    for t in drop_tables:
        con.execute("drop table [%s]" % t)
    con.commit()
    con.close()
    return path
