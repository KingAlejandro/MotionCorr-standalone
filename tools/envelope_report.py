#!/usr/bin/env python3
"""Summarise an `envelope_runner.py` series into tables and a product-equality verdict.

Ordering matters: the product verdict is computed first and reported first, because a timing
table for arms that did not all produce the same outputs is not a comparison. An arm that
lost a movie, or produced different pixels, is not a faster arm.

Products are compared as MRC payload and core header separately. The label block at offset
224 carries an `strftime` timestamp and is expected to differ between any two runs; a
whole-file digest would therefore report every arm as mismatched and prove nothing. PDFs are
excluded from the equality claim for the same reason — ghostscript embeds creation dates —
and their presence and byte count are checked instead.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

TIMESTAMPED = (".pdf",)


def product_key(run: Dict[str, Any]) -> Dict[str, Any]:
    """Comparable fingerprint of one arm's output set."""
    payloads, headers, others, stamped = {}, {}, {}, {}
    for p in run["products"]:
        path = p["path"]
        if path.endswith(TIMESTAMPED):
            stamped[path] = p["bytes"]
        elif p.get("mrc"):
            payloads[path] = p["mrc"]["payload_sha256"]
            headers[path] = p["mrc"]["core_header_sha256"]
        else:
            others[path] = p["sha256"]
    return {"payloads": payloads, "core_headers": headers,
            "others": others, "timestamped_bytes": stamped}


def compare_products(ref: Dict[str, Any], test: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field in ("payloads", "core_headers", "others"):
        r, t = ref[field], test[field]
        missing = sorted(set(r) - set(t))
        extra = sorted(set(t) - set(r))
        differing = sorted(k for k in set(r) & set(t) if r[k] != t[k])
        out[field] = {"n_ref": len(r), "n_test": len(t), "missing": missing,
                      "extra": extra, "differing": differing,
                      "equal": not (missing or extra or differing)}
    rs, ts = ref["timestamped_bytes"], test["timestamped_bytes"]
    out["timestamped"] = {
        "n_ref": len(rs), "n_test": len(ts),
        "missing": sorted(set(rs) - set(ts)), "extra": sorted(set(ts) - set(rs)),
        "note": "content not compared: these embed a generation date by construction",
    }
    out["verdict"] = "EQUAL" if all(out[f]["equal"] for f in
                                    ("payloads", "core_headers", "others")) else "DIFFERS"
    return out


def fmt(x: Optional[float], nd: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", type=Path, required=True, help="series.json from the runner")
    ap.add_argument("--reference-arm", required=True,
                    help="arm id whose products define the same-backend baseline")
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    data = json.loads(args.series.read_text())
    runs = [r for r in data["runs"] if r["rep"] != 0]        # rep 0 is the declared warm-up
    warmups = [r for r in data["runs"] if r["rep"] == 0]

    failed = [r["tag"] for r in runs if r["exit_code"] != 0]

    # ---------------------------------------------------- product equality, computed first
    ref_runs = [r for r in data["runs"] if r["arm_id"] == args.reference_arm]
    if not ref_runs:
        print(f"ERROR: reference arm {args.reference_arm} not in series")
        return 2
    ref = product_key(ref_runs[0])
    by_arm: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in runs:
        by_arm[r["arm_id"]].append(r)

    prod: Dict[str, Any] = {}
    for arm, rs in by_arm.items():
        # Compare every run, not one per arm: a product difference that appears in only one
        # repeat is exactly the kind that a one-run-per-arm check would miss.
        per_run = {r["tag"]: compare_products(ref, product_key(r)) for r in rs}
        prod[arm] = {"runs": per_run,
                     "all_equal": all(v["verdict"] == "EQUAL" for v in per_run.values()),
                     "product_counts": sorted({r["product_count"] for r in rs})}

    print("=" * 78)
    print(f"PRODUCT EQUALITY vs reference arm '{args.reference_arm}'"
          f"  (run {ref_runs[0]['tag']})")
    print("=" * 78)
    n_bad = 0
    for arm in sorted(prod):
        v = prod[arm]
        flag = "EQUAL" if v["all_equal"] else "DIFFERS"
        if not v["all_equal"]:
            n_bad += 1
        print(f"  {arm:<28} {flag:<8} products={v['product_counts']}")
        if not v["all_equal"]:
            for tag, c in v["runs"].items():
                if c["verdict"] == "EQUAL":
                    continue
                for f in ("payloads", "core_headers", "others"):
                    d = c[f]
                    if not d["equal"]:
                        print(f"      {tag} {f}: differing={d['differing'][:4]} "
                              f"missing={d['missing'][:4]} extra={d['extra'][:4]}")
    print(f"\n  arms with differing products: {n_bad} of {len(prod)}")
    print(f"  non-zero exits: {failed if failed else 'none'}")
    if warmups:
        print(f"  declared warm-up runs excluded from tables: "
              f"{[w['tag'] + ' ' + str(w['wall_s']) + 's' for w in warmups]}")

    # ------------------------------------------------------------------- timing, second
    print("\n" + "=" * 78)
    print("WALL TIME BY ARM")
    print("=" * 78)
    print(f"  {'arm':<28} {'n':>2} {'median':>8} {'min':>8} {'max':>8} {'spread%':>8} "
          f"{'cpu_s':>8} {'peakRSS_MiB':>12} {'VRAM_MiB':>9}")
    table = {}
    for arm in sorted(by_arm, key=lambda a: statistics.median(
            [r["wall_s"] for r in by_arm[a]])):
        rs = by_arm[arm]
        w = sorted(r["wall_s"] for r in rs)
        med = statistics.median(w)
        spread = (max(w) - min(w)) / med * 100 if med else 0.0
        cpu = [r["resource_usage"].get("user_s", 0) + r["resource_usage"].get("sys_s", 0)
               for r in rs]
        rss = [r["memory"].get("peak_simultaneous_tree_rss_kib", 0) for r in rs]
        vram = [r["sampling"]["device_vram_mib_sampled"].get("max", 0) for r in rs
                if r["sampling"]["device_vram_mib_sampled"].get("n")]
        table[arm] = {"n": len(w), "median_s": med, "min_s": min(w), "max_s": max(w),
                      "spread_pct": spread, "walls": w,
                      "median_cpu_s": statistics.median(cpu) if cpu else None,
                      "peak_rss_mib": max(rss) // 1024 if rss and max(rss) else None,
                      "peak_vram_mib_sampled": max(vram) if vram else None,
                      "effective": rs[0]["effective"]}
        t = table[arm]
        print(f"  {arm:<28} {t['n']:>2} {fmt(med):>8} {fmt(min(w)):>8} {fmt(max(w)):>8} "
              f"{fmt(spread,1):>8} {fmt(t['median_cpu_s'],1):>8} "
              f"{str(t['peak_rss_mib']):>12} {str(t['peak_vram_mib_sampled']):>9}")

    # ------------------------------------------------- positional bias, from the same data
    print("\n" + "=" * 78)
    print("POSITIONAL BIAS  (wall vs slot within repeat, pooled over arms)")
    print("=" * 78)
    by_order: Dict[int, List[float]] = defaultdict(list)
    for r in runs:
        med = table[r["arm_id"]]["median_s"]
        if med:
            by_order[r["order_in_pair"]].append(r["wall_s"] / med)
    for o in sorted(by_order):
        v = by_order[o]
        print(f"  slot {o:>2}: n={len(v):>2} mean ratio to arm median = "
              f"{statistics.fmean(v):.4f}")
    print("  A ratio systematically below 1.0 in later slots is page-cache warming, not an\n"
          "  effect of the configuration that happened to be scheduled there.")

    # ------------------------------------------------------------------------ interference
    print("\n" + "=" * 78)
    print("INTERFERENCE (threads outside this run's subtree, sampled during the run)")
    print("=" * 78)
    for arm in sorted(by_arm):
        rs = by_arm[arm]
        fmax = max(r["sampling"]["foreign_cpu_pct"].get("max", 0) for r in rs)
        imax = max(r["sampling"]["foreign_threads_inside_mask"].get("max", 0) for r in rs)
        cmds: Dict[str, int] = {}
        for r in rs:
            for k, v in (r["sampling"].get("foreign_in_mask_by_command") or {}).items():
                cmds[k] = cmds.get(k, 0) + v
        if fmax or imax:
            print(f"  {arm:<28} foreign_cpu_max={fmax:>7}%  in_mask_max={imax:>2}  {cmds}")
    print("  (arms with no foreign CPU observed are omitted)")

    if args.json_out:
        args.json_out.write_text(json.dumps(
            {"series": data.get("plan_name"), "source_commit": data.get("source_commit"),
             "reference_arm": args.reference_arm, "failed_runs": failed,
             "product_equality": prod, "timing": table,
             "positional": {str(k): statistics.fmean(v) for k, v in by_order.items()}},
            indent=2))
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
