"""Derived device metrics from an Nsight Systems trace (docs/profiling.md, "trace").

All times are integer nanoseconds on the trace clock. The functions take plain
lists so they can be tested with known answers, independently of SQLite.

Definitions:

* busy: the union of kernel, memcpy and memset intervals. Overlapping device
  work is counted once.
* segments: a tiling of the traced window. Inside each movie the top-level
  `--profile` stages (NVTX depth 1 under "movie") are the segments; gaps
  between stages, if any, are "movie: unattributed"; time outside movies is
  "before first movie", "between movies" and "after last movie".
* idle: segment wall minus busy inside it. Every idle interval is split at
  segment boundaries, so each piece is charged to the segment it lies in
  (ported from tools/nsys_analysis/gaps2.py, which fixed charging a whole gap
  to the stage at its start).
* point events (API calls, kernel launches, copies) are charged to the segment
  containing their start time.
"""
from __future__ import annotations

import bisect
import re
from collections import OrderedDict, defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Interval = Tuple[int, int]

MOVIE_RANGE = "movie"
BEFORE = "before first movie"
BETWEEN = "between movies"
AFTER = "after last movie"
UNATTRIBUTED = "movie: unattributed"
NO_STAGES = "whole trace (no --profile NVTX ranges)"


class MetricError(Exception):
    pass


# ----------------------------------------------------------------- intervals

def union(intervals: Iterable[Sequence[int]]) -> List[Interval]:
    """Merge intervals; touching intervals merge."""
    merged: List[List[int]] = []
    for s, e, *_ in sorted((iv[0], iv[1]) for iv in intervals):
        if e < s:
            raise MetricError("interval ends before it starts: (%d, %d)" % (s, e))
        if merged and s <= merged[-1][1]:
            if e > merged[-1][1]:
                merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def total(merged: Sequence[Interval]) -> int:
    return sum(e - s for s, e in merged)


def clip(merged: Sequence[Interval], lo: int, hi: int, _starts: Optional[List[int]] = None) -> int:
    """Length of merged (sorted, disjoint) intervals inside [lo, hi]."""
    if hi <= lo or not merged:
        return 0
    starts = _starts if _starts is not None else [s for s, _ in merged]
    i = max(bisect.bisect_right(starts, lo) - 1, 0)
    t = 0
    while i < len(merged) and merged[i][0] < hi:
        s, e = merged[i]
        if e > lo:
            t += min(e, hi) - max(s, lo)
        i += 1
    return t


def complement(merged: Sequence[Interval], lo: int, hi: int,
               _starts: Optional[List[int]] = None) -> List[Interval]:
    """Gaps of merged intervals inside [lo, hi]."""
    if hi <= lo:
        return []
    starts = _starts if _starts is not None else [s for s, _ in merged]
    i = max(bisect.bisect_right(starts, lo) - 1, 0)
    gaps = []
    cur = lo
    while i < len(merged) and merged[i][0] < hi:
        s, e = merged[i]
        if e > cur:
            if s > cur:
                gaps.append((cur, s))
            cur = max(cur, e)
        i += 1
    if cur < hi:
        gaps.append((cur, hi))
    return gaps


# ----------------------------------------------------------------- segments

class Segment:
    __slots__ = ("start", "end", "label", "movie", "kind")

    def __init__(self, start: int, end: int, label: str, movie: Optional[int], kind: str):
        self.start, self.end, self.label, self.movie, self.kind = start, end, label, movie, kind

    @property
    def wall(self) -> int:
        return self.end - self.start

    def as_dict(self) -> Dict:
        return {"start": self.start, "end": self.end, "label": self.label, "movie": self.movie, "kind": self.kind}


def nest(ranges: Sequence[Tuple[int, int, str, int]]) -> List[Tuple[int, int, str, int, int, Optional[int]]]:
    """Depth and parent index for push/pop ranges, per thread.

    Input rows are (start, end, name, tid). Output rows are
    (start, end, name, tid, depth, parent_index) in input order.
    """
    out: List = [None] * len(ranges)
    by_tid: Dict[int, List[int]] = defaultdict(list)
    for i, r in enumerate(ranges):
        by_tid[r[3]].append(i)
    for idx in by_tid.values():
        idx.sort(key=lambda i: (ranges[i][0], -ranges[i][1]))
        stack: List[int] = []
        for i in idx:
            s, e = ranges[i][0], ranges[i][1]
            while stack and ranges[stack[-1]][1] <= s:
                stack.pop()
            # A range that starts inside the top of the stack but outlives it
            # is not nested; NVTX push/pop cannot produce one.
            if stack and e > ranges[stack[-1]][1]:
                raise MetricError("NVTX ranges overlap without nesting: %r and %r"
                                  % (ranges[stack[-1]][:3], ranges[i][:3]))
            out[i] = tuple(ranges[i]) + (len(stack), stack[-1] if stack else None)
            stack.append(i)
    return out


def segments(ranges: Sequence[Tuple[int, int, str, int]], lo: int, hi: int) -> List[Segment]:
    """Tile [lo, hi] with movie stages and outside-movie segments."""
    if hi <= lo:
        raise MetricError("empty trace window")
    nested = nest(ranges)
    movies = sorted((r for r in nested if r[4] == 0 and r[2] == MOVIE_RANGE), key=lambda r: r[0])
    if not movies:
        return [Segment(lo, hi, NO_STAGES, None, "whole")]
    index = {id(r): i for i, r in enumerate(nested)}
    children: Dict[int, List] = defaultdict(list)
    for r in nested:
        if r[4] == 1 and r[5] is not None:
            children[r[5]].append(r)
    segs: List[Segment] = []

    def add(s: int, e: int, label: str, movie: Optional[int], kind: str) -> None:
        s, e = max(s, lo), min(e, hi)
        if e > s:
            segs.append(Segment(s, e, label, movie, kind))

    cursor = lo
    for mi, m in enumerate(movies):
        add(cursor, m[0], BEFORE if mi == 0 else BETWEEN, None, "outside")
        cursor = m[0]
        for c in sorted(children[index[id(m)]], key=lambda r: r[0]):
            add(cursor, c[0], UNATTRIBUTED, mi, "unattributed")
            add(c[0], c[1], c[2], mi, "stage")
            cursor = max(cursor, c[1])
        add(cursor, m[1], UNATTRIBUTED, mi, "unattributed")
        cursor = max(cursor, m[1])
    add(cursor, hi, AFTER, None, "outside")
    return segs


class SegmentIndex:
    """Charge point events to the segment containing them."""

    def __init__(self, segs: Sequence[Segment]):
        self.segs = list(segs)
        self.starts = [s.start for s in self.segs]

    def find(self, t: int) -> Optional[int]:
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0:
            return None
        if t < self.segs[i].end or (i == len(self.segs) - 1 and t == self.segs[i].end):
            return i
        return None


# ----------------------------------------------------------------- per segment

def device_per_segment(segs: Sequence[Segment], busy: Sequence[Interval]) -> List[Dict]:
    """Busy, idle and idle-interval statistics for each segment."""
    starts = [s for s, _ in busy]
    out = []
    for g in segs:
        b = clip(busy, g.start, g.end, starts)
        gaps = complement(busy, g.start, g.end, starts)
        out.append({"busy_ns": b, "idle_ns": g.wall - b, "idle_intervals": len(gaps),
                    "max_idle_interval_ns": max((e - s for s, e in gaps), default=0)})
    return out


_SUFFIX = re.compile(r"(_v\d+|_ptsz|_ptds)+$")


def api_base(name: str) -> str:
    return _SUFFIX.sub("", name)


SYNC_CLASS = {
    "cudaDeviceSynchronize": "device sync", "cuCtxSynchronize": "device sync",
    "cudaStreamSynchronize": "stream sync", "cuStreamSynchronize": "stream sync",
    "cudaEventSynchronize": "event sync", "cuEventSynchronize": "event sync",
    "cudaMemcpy": "synchronous memcpy", "cudaMemcpy2D": "synchronous memcpy",
    "cudaMemcpy3D": "synchronous memcpy", "cudaMemcpyToSymbol": "synchronous memcpy",
    "cudaMemcpyFromSymbol": "synchronous memcpy", "cuMemcpy": "synchronous memcpy",
    "cuMemcpyHtoD": "synchronous memcpy", "cuMemcpyDtoH": "synchronous memcpy",
    "cuMemcpyDtoD": "synchronous memcpy", "cuMemcpy2D": "synchronous memcpy",
    "cudaFree": "free (implicit sync)", "cuMemFree": "free (implicit sync)",
    "cudaFreeHost": "free (implicit sync)", "cuMemFreeHost": "free (implicit sync)",
}
ALLOC_CLASS = {
    "cudaMalloc": "device malloc", "cuMemAlloc": "device malloc", "cudaMallocPitch": "device malloc",
    "cudaMallocHost": "pinned malloc", "cudaHostAlloc": "pinned malloc", "cuMemHostAlloc": "pinned malloc",
    "cuMemAllocHost": "pinned malloc", "cudaMallocAsync": "async malloc", "cuMemAllocAsync": "async malloc",
    "cudaFree": "device free", "cuMemFree": "device free",
    "cudaFreeHost": "pinned free", "cuMemFreeHost": "pinned free",
    "cudaFreeAsync": "async free", "cuMemFreeAsync": "async free",
}
LAUNCH_APIS = {"cudaLaunchKernel", "cuLaunchKernel", "cudaLaunchKernelExC", "cuLaunchKernelEx",
               "cudaLaunchCooperativeKernel", "cuLaunchCooperativeKernel"}


def api_census(segs: Sequence[Segment], calls: Sequence[Tuple[int, int, str]],
               busy: Sequence[Interval]) -> Tuple[List[Dict], Dict]:
    """Per segment: blocking calls by class (count, host ns, device-busy ns
    inside the call), allocation calls, launch API calls. Also a per-API total."""
    idx = SegmentIndex(segs)
    starts = [s for s, _ in busy]
    per = [{"sync": defaultdict(lambda: [0, 0, 0]), "alloc": defaultdict(int), "launch_api": 0}
           for _ in segs]
    by_api: Dict[str, List[int]] = defaultdict(lambda: [0, 0, 0])
    for s, e, name in calls:
        base = api_base(name)
        i = idx.find(s)
        host = e - s
        rec = by_api[base]
        rec[0] += 1
        rec[1] += host
        if base in SYNC_CLASS:
            dev = clip(busy, s, e, starts)
            rec[2] += dev
            if i is not None:
                c = per[i]["sync"][SYNC_CLASS[base]]
                c[0] += 1
                c[1] += host
                c[2] += dev
        if i is None:
            continue
        if base in ALLOC_CLASS:
            per[i]["alloc"][ALLOC_CLASS[base]] += 1
        if base in LAUNCH_APIS:
            per[i]["launch_api"] += 1
    out = []
    for p in per:
        out.append({"sync": {k: {"n": v[0], "host_ns": v[1], "device_busy_ns": v[2],
                                 "blocked_idle_ns": v[1] - v[2]} for k, v in sorted(p["sync"].items())},
                    "alloc": dict(sorted(p["alloc"].items())), "launch_api": p["launch_api"]})
    apis = {k: {"n": v[0], "host_ns": v[1], "device_busy_ns": v[2] if k in SYNC_CLASS else None,
                "class": SYNC_CLASS.get(k) or ALLOC_CLASS.get(k) or ("launch" if k in LAUNCH_APIS else None)}
            for k, v in by_api.items()}
    return out, apis


def copies_per_segment(segs: Sequence[Segment], copies: Sequence[Dict]) -> List[Dict]:
    """copies rows: {start, end, bytes, direction, src, dst}."""
    idx = SegmentIndex(segs)
    per: List[Dict] = [defaultdict(lambda: {"n": 0, "bytes": 0, "device_ns": 0}) for _ in segs]
    for c in copies:
        i = idx.find(c["start"])
        if i is None:
            continue
        key = "%s %s->%s" % (c["direction"], c["src"], c["dst"])
        r = per[i][key]
        r["n"] += 1
        r["bytes"] += c["bytes"]
        r["device_ns"] += c["end"] - c["start"]
    return [dict(sorted(p.items())) for p in per]


def count_per_segment(segs: Sequence[Segment], times: Iterable[int]) -> List[int]:
    idx = SegmentIndex(segs)
    n = [0] * len(segs)
    for t in times:
        i = idx.find(t)
        if i is not None:
            n[i] += 1
    return n


class _LiveMemory:
    """Live device allocations keyed by (pid, context, device, address)."""

    def __init__(self):
        self.live: Dict[Tuple, int] = {}
        self.cur: Dict[int, int] = defaultdict(int)
        self.peak: Dict[int, int] = {}
        self.peak_t: Dict[int, int] = {}
        self.allocs: Dict[str, int] = defaultdict(int)
        self.frees = 0
        self.duplicate_static = 0
        self.total = 0

    def apply(self, e: Dict) -> None:
        key = (e["pid"], e["context"], e["device"], e["address"])
        d = e["device"]
        if e["op"] == "Allocation":
            if key in self.live:
                if e["kind"] == "Device Static" and self.live[key] == e["bytes"]:
                    self.duplicate_static += 1
                    return
                raise MetricError("duplicate live CUDA allocation key %r" % (key,))
            self.live[key] = e["bytes"]
            self.cur[d] += e["bytes"]
            self.total += e["bytes"]
            self.allocs[e["kind"]] += 1
        elif e["op"] == "Deallocation":
            if key not in self.live:
                raise MetricError("unmatched CUDA deallocation %r" % (key,))
            size = self.live.pop(key)
            self.cur[d] -= size
            self.total -= size
            self.frees += 1
        else:
            raise MetricError("unknown memory operation %r" % (e["op"],))
        if self.cur[d] > self.peak.get(d, -1):
            self.peak[d] = self.cur[d]
            self.peak_t[d] = e["start"]


def memory_high_water(events: Sequence[Dict], segs: Sequence[Segment]) -> Dict:
    """Device memory high-water from allocation events.

    events rows: {start, pid, context, device, address, bytes, op, kind} with
    op in {"Allocation", "Deallocation"}. Nsight repeats some Device Static
    symbols without a matching free; a repeat of a live static key with the
    same size is counted once (ported from tools/profile_cuda_movie.py). Any
    other duplicate or unmatched free is an error, not a guess.
    segment_peak_bytes[i] is the largest total resident during segment i,
    including what was already resident when it began.
    """
    mem = _LiveMemory()
    ev = sorted(events, key=lambda e: e["start"])
    seg_peak = [0] * len(segs)
    j = 0
    for si, g in enumerate(segs):
        while j < len(ev) and ev[j]["start"] < g.start:
            mem.apply(ev[j])
            j += 1
        seg_peak[si] = mem.total
        while j < len(ev) and ev[j]["start"] < g.end:
            mem.apply(ev[j])
            seg_peak[si] = max(seg_peak[si], mem.total)
            j += 1
    for e in ev[j:]:
        mem.apply(e)
    idx = SegmentIndex(segs)
    devices = {}
    for d in mem.peak:
        i = idx.find(mem.peak_t[d])
        devices[str(d)] = {"peak_bytes": mem.peak[d], "peak_time_ns": mem.peak_t[d],
                           "peak_segment": segs[i].label if i is not None else None,
                           "peak_movie": segs[i].movie if i is not None else None,
                           "residual_bytes": mem.cur[d]}
    return {"scope": "traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); "
                     "excludes CUDA context, cuFFT/driver internal and untraced memory",
            "devices": devices, "allocations_by_kind": dict(sorted(mem.allocs.items())),
            "frees": mem.frees, "duplicate_device_static_counted_once": mem.duplicate_static,
            "segment_peak_bytes": seg_peak}


# ----------------------------------------------------------------- aggregation

def aggregate_by_stage(segs: Sequence[Segment], per_seg: Sequence[Dict], keys: Sequence[str]) -> "OrderedDict[str, Dict]":
    """Per stage name: per-movie values (zero where a movie lacks the stage),
    the first movie, the steady-state median (movies after the first) and sums.
    Outside-movie segments are kept as their own rows."""
    movies = sorted({g.movie for g in segs if g.movie is not None})
    rows: "OrderedDict[str, Dict]" = OrderedDict()
    for g, v in zip(segs, per_seg):
        row = rows.setdefault(g.label, {"kind": g.kind, "per_movie": defaultdict(lambda: defaultdict(int)),
                                        "outside": defaultdict(int), "count": 0})
        row["count"] += 1
        tgt = row["per_movie"][g.movie] if g.movie is not None else row["outside"]
        for k in keys:
            tgt[k] += v[k]
    out: "OrderedDict[str, Dict]" = OrderedDict()
    for name, row in rows.items():
        r: Dict = {"kind": row["kind"], "segments": row["count"]}
        if row["kind"] in ("stage", "unattributed"):
            for k in keys:
                vals = [row["per_movie"][m][k] if m in row["per_movie"] else 0 for m in movies]
                steady = vals[1:] if len(vals) > 1 else vals
                r[k] = {"per_movie": vals, "sum": sum(vals), "first": vals[0] if vals else 0,
                        "steady_median": _median(steady), "steady_sum": sum(steady)}
        else:
            for k in keys:
                r[k] = {"sum": row["outside"][k]}
        out[name] = r
    return out


def _median(v: Sequence[float]) -> float:
    s = sorted(v)
    n = len(s)
    if n == 0:
        return 0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# ----------------------------------------------------------------- folded stacks

_HEX = re.compile(r"^0x[0-9a-fA-F]+$")


def folded_stacks(samples: Dict[int, int], frames: Dict[int, List[Tuple[int, str, str, int]]],
                  thread_names: Dict[int, str], only_thread: Optional[str] = None) -> Tuple[Dict[str, int], int]:
    """Collapse CPU samples into folded stacks (ported from tools/nsys_analysis/folded.py).

    samples: event id -> globalTid. frames: event id -> [(depth, symbol, module,
    kernelMode)]. Unresolved frames collapse to their module; kernel-mode
    frames are prefixed "[k] ". Returns ({stack: count}, samples without callchain).
    """
    counts: Dict[str, int] = defaultdict(int)
    dropped = 0
    for cid, tid in samples.items():
        f = frames.get(cid)
        if not f:
            dropped += 1
            continue
        tname = thread_names.get(tid, "?")
        if only_thread is not None and tname != only_thread:
            continue
        stack = [tname] + [_frame_label(sym, mod, km) for _, sym, mod, km in sorted(f, key=lambda x: -x[0])]
        dedup = [stack[0]]
        for x in stack[1:]:
            if x != dedup[-1]:
                dedup.append(x)
        counts[";".join(dedup)] += 1
    return dict(counts), dropped


def _frame_label(sym: Optional[str], mod: Optional[str], kernel_mode) -> str:
    md = (mod or "[unknown]").split("/")[-1]
    if sym and not _HEX.match(sym):
        label = sym.split("(")[0][:70]
    elif md.startswith("["):
        label = md
    else:
        label = "[%s]" % md
    return ("[k] " + label) if kernel_mode else label


# ----------------------------------------------------------------- whole-trace analysis

def analyze(db, top_kernels: int = 15) -> Dict:
    """Everything `mcprof trace` reports, from one NsysDB. Times in ns."""
    lo, hi = db.window()
    kernels = db.kernels()
    copies = db.memcpys()
    memsets = db.memsets()
    busy = union([(k["start"], k["end"]) for k in kernels] + [(c["start"], c["end"]) for c in copies]
                 + [(m["start"], m["end"]) for m in memsets])
    kern_u = union([(k["start"], k["end"]) for k in kernels])
    copy_u = union([(c["start"], c["end"]) for c in copies])
    segs = segments(db.nvtx_ranges(), lo, hi)
    dev = device_per_segment(segs, busy)
    kbusy = device_per_segment(segs, kern_u)
    cbusy = device_per_segment(segs, copy_u)
    calls = [(s, e, n) for s, e, n, _ in db.runtime()]
    census, apis = api_census(segs, calls, busy)
    cps = copies_per_segment(segs, copies)
    kcount = count_per_segment(segs, (k["start"] for k in kernels))
    mem_events = db.memory_events()
    memory = memory_high_water(mem_events, segs) if mem_events else None
    per_seg = []
    for i, g in enumerate(segs):
        row = {"wall_ns": g.wall, "busy_ns": dev[i]["busy_ns"], "idle_ns": dev[i]["idle_ns"],
               "kernel_busy_ns": kbusy[i]["busy_ns"], "copy_busy_ns": cbusy[i]["busy_ns"],
               "idle_intervals": dev[i]["idle_intervals"], "kernels": kcount[i],
               "malloc": census[i]["alloc"].get("device malloc", 0),
               "free": census[i]["alloc"].get("device free", 0),
               "pinned_malloc": census[i]["alloc"].get("pinned malloc", 0),
               "sync_calls": sum(v["n"] for v in census[i]["sync"].values()),
               "sync_blocked_idle_ns": sum(v["blocked_idle_ns"] for v in census[i]["sync"].values()),
               "copy_bytes": sum(v["bytes"] for v in cps[i].values()),
               "pageable_copies": sum(v["n"] for k, v in cps[i].items() if "Pageable" in k),
               "mem_peak_bytes": memory["segment_peak_bytes"][i] if memory else 0}
        per_seg.append(row)
    keys = list(per_seg[0].keys()) if per_seg else []
    stages = aggregate_by_stage(segs, per_seg, [k for k in keys if k != "mem_peak_bytes"])
    # High-water is a maximum, not a sum: aggregate it separately.
    if memory:
        peaks: Dict[str, int] = defaultdict(int)
        for g, row in zip(segs, per_seg):
            peaks[g.label] = max(peaks[g.label], row["mem_peak_bytes"])
        for name in stages:
            stages[name]["mem_peak_bytes"] = peaks[name]
    # Copies and syncs by stage name with their breakdown.
    copy_detail: Dict[str, Dict] = defaultdict(lambda: defaultdict(lambda: {"n": 0, "bytes": 0, "device_ns": 0}))
    sync_detail: Dict[str, Dict] = defaultdict(lambda: defaultdict(lambda: {"n": 0, "host_ns": 0, "device_busy_ns": 0,
                                                                            "blocked_idle_ns": 0}))
    for g, cp, ce in zip(segs, cps, census):
        for k, v in cp.items():
            for f in v:
                copy_detail[g.label][k][f] += v[f]
        for k, v in ce["sync"].items():
            for f in v:
                sync_detail[g.label][k][f] += v[f]
    ktab: Dict[str, List[int]] = defaultdict(lambda: [0, 0, 0])
    for k in kernels:
        r = ktab[k["name"]]
        r[0] += 1
        r[1] += k["end"] - k["start"]
        r[2] = max(r[2], k["end"] - k["start"])
    ktot = sum(v[1] for v in ktab.values())
    top = [{"name": n, "launches": v[0], "device_ns": v[1], "mean_ns": v[1] / v[0], "max_ns": v[2],
            "share": v[1] / ktot if ktot else 0} for n, v in sorted(ktab.items(), key=lambda kv: -kv[1][1])]
    movies = sorted({g.movie for g in segs if g.movie is not None})
    return {
        "window_ns": [lo, hi], "span_ns": hi - lo,
        "totals": {"busy_ns": total(busy), "idle_ns": (hi - lo) - total(busy),
                   "kernel_sum_ns": sum(k["end"] - k["start"] for k in kernels),
                   "kernel_union_ns": total(kern_u), "copy_sum_ns": sum(c["end"] - c["start"] for c in copies),
                   "copy_union_ns": total(copy_u),
                   "overlap_ns": total(kern_u) + total(copy_u) + total(union([(m["start"], m["end"]) for m in memsets]))
                   - total(busy),
                   "kernels": len(kernels), "copies": len(copies), "memsets": len(memsets),
                   "copy_bytes": sum(c["bytes"] for c in copies), "movies": len(movies),
                   "streams_with_kernels": len({k["stream"] for k in kernels})},
        "stages": stages,
        "copies_by_stage": {k: dict(v) for k, v in copy_detail.items()},
        "syncs_by_stage": {k: dict(v) for k, v in sync_detail.items()},
        "apis": dict(sorted(apis.items(), key=lambda kv: -kv[1]["host_ns"])),
        "sync_records": db.sync_records(),
        "memory": memory,
        "top_kernels": top[:top_kernels], "kernel_kinds": len(top),
        "segments": [g.as_dict() for g in segs],
        "per_segment": per_seg,
        "gpus": db.gpus(),
        "nsys": {k: v for k, v in db.meta().items() if k in ("EXPORT_PRODUCT_VERSION", "EXPORT_SCHEMA_VERSION")},
    }


def timeline(db, analysis: Dict) -> Dict:
    """Per-movie device timeline: stages, kernels and copies relative to the movie start (ms)."""
    segs = analysis["segments"]
    movies: Dict[int, Dict] = {}
    for g in segs:
        if g["movie"] is None:
            continue
        m = movies.setdefault(g["movie"], {"movie": g["movie"], "start_ns": g["start"], "end_ns": g["end"],
                                           "stages": [], "kernels": [], "copies": []})
        m["start_ns"] = min(m["start_ns"], g["start"])
        m["end_ns"] = max(m["end_ns"], g["end"])
    for g in segs:
        if g["movie"] is not None:
            m = movies[g["movie"]]
            m["stages"].append([g["label"], round((g["start"] - m["start_ns"]) / 1e6, 3),
                                round((g["end"] - m["start_ns"]) / 1e6, 3)])
    order = sorted(movies.values(), key=lambda m: m["start_ns"])
    starts = [m["start_ns"] for m in order]

    def owner(t):
        i = bisect.bisect_right(starts, t) - 1
        return order[i] if i >= 0 and t < order[i]["end_ns"] else None

    for k in db.kernels():
        m = owner(k["start"])
        if m:
            m["kernels"].append([round((k["start"] - m["start_ns"]) / 1e6, 4),
                                 round((k["end"] - m["start_ns"]) / 1e6, 4), k["name"]])
    for c in db.memcpys():
        m = owner(c["start"])
        if m:
            m["copies"].append([round((c["start"] - m["start_ns"]) / 1e6, 4),
                                round((c["end"] - m["start_ns"]) / 1e6, 4), c["direction"], c["bytes"]])
    for m in order:
        m["wall_ms"] = round((m["end_ns"] - m["start_ns"]) / 1e6, 3)
    return {"units": "ms relative to the movie's first NVTX stage", "movies": order}


# ----------------------------------------------------------------- Nsight Compute

NCU_PCT = {"Compute (SM) Throughput": "sm_pct", "Memory Throughput": "mem_pct", "DRAM Throughput": "dram_pct",
           "Achieved Occupancy": "achieved_occ_pct", "Theoretical Occupancy": "theoretical_occ_pct",
           "L1/TEX Hit Rate": "l1_hit_pct", "L2 Hit Rate": "l2_hit_pct"}
NCU_TIME = {"ns": 1e-3, "nsecond": 1e-3, "us": 1.0, "usecond": 1.0, "ms": 1e3, "msecond": 1e3, "s": 1e6, "second": 1e6}


def ncu_summary(csv_text: str) -> Dict:
    """Per-kernel medians of percentage metrics from `ncu --csv --page details`.

    Metrics are filtered by unit: "Memory Throughput" appears both as % and as
    Gbyte/s, and mixing them produces nonsense (tools/nsys_analysis/ncu_sum.py).
    ncu replays and serialises kernels, so its Duration is reported for
    reference only; device time comes from Nsight Systems.
    """
    import csv
    import io
    lines = csv_text.splitlines()
    try:
        hi = next(i for i, l in enumerate(lines) if l.startswith('"ID"'))
    except StopIteration:
        raise MetricError("no ncu CSV header (\"ID\",...) found; were any kernels profiled?")
    rows = csv.DictReader(io.StringIO("\n".join(lines[hi:])))
    vals: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    launches: Dict[str, set] = defaultdict(set)
    rejected_units: Dict[str, set] = defaultdict(set)
    for row in rows:
        name = (row.get("Kernel Name") or "").split("(")[0]
        metric = row.get("Metric Name", "")
        unit = (row.get("Metric Unit") or "").strip()
        try:
            v = float((row.get("Metric Value") or "").replace(",", ""))
        except ValueError:
            continue
        launches[name].add(row.get("ID"))
        if metric in NCU_PCT:
            if unit == "%":
                vals[name][NCU_PCT[metric]].append(v)
            else:
                rejected_units[metric].add(unit)
        elif metric == "Duration" and unit in NCU_TIME:
            vals[name]["ncu_duration_us"].append(v * NCU_TIME[unit])
        elif metric == "Registers Per Thread":
            vals[name]["registers"].append(v)
        elif metric == "Grid Size":
            vals[name]["grid"].append(v)
        elif metric == "Block Size":
            vals[name]["block"].append(v)
    out = {}
    for name, m in vals.items():
        out[name] = {"launches_profiled": len(launches[name])}
        for k, v in m.items():
            out[name][k] = _median(v)
    return {"kernels": out, "units_rejected": {k: sorted(v) for k, v in rejected_units.items()}}
