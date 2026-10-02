#!/usr/bin/env python3
"""Per-arm device-memory and GPU-execution facts from nsys SQLite exports.

Three separate quantities, never mixed:
  * allocation events   -> running total, peak, inter-movie floor, alloc/free counts
  * kernel/copy spans   -> union busy time and per-bin occupancy
  * copy sizes          -> H2D/D2H bytes
A profiled run is attribution. It is not a timing claim.
"""
import json, sqlite3, sys
from pathlib import Path

ARMS = ["A0", "A1", "B", "C", "D", "E"]
MIB = 1024.0 * 1024.0


def union_seconds(spans):
    """Total wall time covered by at least one span. Not a sum of durations."""
    if not spans:
        return 0.0
    spans = sorted(spans)
    total, cur_s, cur_e = 0, spans[0][0], spans[0][1]
    for s, e in spans[1:]:
        if s > cur_e:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    return (total + cur_e - cur_s) / 1e9


def analyse(path, bins=900):
    c = sqlite3.connect(path)
    out = {}

    # ---- allocation events: running total of alloc minus free -------------
    rows = list(c.execute(
        "select start, bytes, memoryOperationType, memKind "
        "from CUDA_GPU_MEMORY_USAGE_EVENTS order by start"))
    t0 = rows[0][0] if rows else 0
    t1 = rows[-1][0] if rows else 0
    live, series, allocs, frees = 0, [], 0, 0
    for start, nbytes, op, kind in rows:
        if op == 0:
            live += nbytes
            allocs += 1
        else:
            live -= nbytes
            frees += 1
        series.append(((start - t0) / 1e9, live / MIB))
    out["alloc_events"] = len(rows)
    out["allocs"] = allocs
    out["frees"] = frees
    out["peak_mib"] = round(max((v for _, v in series), default=0), 1)
    out["series"] = series

    # The floor between movies: the low point AFTER the first movie's buffers
    # exist, so process start-up (where nothing is allocated yet) is excluded.
    # Troughs are taken over the middle 80% of the span for the same reason.
    span = series[-1][0] if series else 0
    mid = [v for t, v in series if 0.1 * span < t < 0.9 * span]
    out["floor_mib"] = round(min(mid), 1) if mid else 0.0

    # ---- kernels and copies ------------------------------------------------
    kern = list(c.execute("select start, end from CUPTI_ACTIVITY_KIND_KERNEL"))
    cpy = list(c.execute("select start, end from CUPTI_ACTIVITY_KIND_MEMCPY"))
    out["kernels"] = len(kern)
    out["copies"] = len(cpy)
    out["kernel_union_s"] = round(union_seconds(kern), 4)
    out["copy_union_s"] = round(union_seconds(cpy), 4)
    out["gpu_union_s"] = round(union_seconds(kern + cpy), 4)
    out["trace_span_s"] = round((t1 - t0) / 1e9, 4)

    # copy bytes by direction (1 = HtoD, 2 = DtoH in CUPTI's enum)
    for label, oper in (("h2d_bytes", 1), ("d2h_bytes", 2)):
        n = c.execute("select coalesce(sum(bytes),0) from CUPTI_ACTIVITY_KIND_MEMCPY "
                      "where copyKind = ?", (oper,)).fetchone()[0]
        out[label] = int(n)

    # ---- occupancy per bin: fraction of each bin covered by kernel or copy --
    all_spans = sorted(kern + cpy)
    lo = min((s for s, _ in all_spans), default=t0)
    hi = max((e for _, e in all_spans), default=t1)
    width = max(1, (hi - lo) // bins)
    occ = [0] * bins
    for s, e in all_spans:
        b0, b1 = (s - lo) // width, (e - lo) // width
        for b in range(int(max(0, b0)), int(min(bins - 1, b1)) + 1):
            bs, be = lo + b * width, lo + (b + 1) * width
            occ[b] += max(0, min(e, be) - max(s, bs))
    out["occupancy"] = [min(1.0, x / width) for x in occ]
    out["mean_occupancy_pct"] = round(100 * sum(out["occupancy"]) / bins, 1)
    out["bin_width_s"] = width / 1e9
    c.close()
    return out


def main():
    root = Path(sys.argv[1])
    result = {}
    for arm in ARMS:
        p = root / f"{arm}.sqlite"
        if not p.exists():
            print(f"{arm}: missing"); continue
        result[arm] = analyse(str(p))
        r = result[arm]
        print(f"{arm:3s} peak={r['peak_mib']:8.1f} MiB floor={r['floor_mib']:7.1f} MiB "
              f"allocs={r['allocs']:6d} frees={r['frees']:6d} "
              f"kern={r['kernels']:6d} kunion={r['kernel_union_s']:.3f}s "
              f"cunion={r['copy_union_s']:.3f}s occ={r['mean_occupancy_pct']:.1f}% "
              f"h2d={r['h2d_bytes']/1e9:.2f}GB")
    (root / "profile-summary.json").write_text(json.dumps(
        {k: {kk: vv for kk, vv in v.items() if kk not in ("series", "occupancy")}
         for k, v in result.items()}, indent=1))
    (root / "profile-series.json").write_text(json.dumps(
        {k: {"series": v["series"], "occupancy": v["occupancy"],
             "bin_width_s": v["bin_width_s"]} for k, v in result.items()}))
    print("wrote profile-summary.json and profile-series.json")


if __name__ == "__main__":
    main()
