#!/usr/bin/env python3
"""Collate the Issue #85 lane A raw JSON into the report tables.

Produces, per storage regime and never across them:
  - the per-worker wall table for every arm, as seconds for the whole 24-movie set;
  - the additive attribution chain with each link's cost and share;
  - the comparator control matrix;
  - a scaling table so "more workers is better" is checked rather than assumed.

Nothing here computes a speedup of the application. The arms measure ingest
components; an application claim needs an application run.
"""

import argparse
import json
import os
import sys

# The chain each link adds exactly one component to. Order matters.
CHAIN = [
    ("pread_strip_extents",         "storage read of compressed strips"),
    ("tiff_read_raw_strip",         "+ LibTIFF strip bookkeeping"),
    ("tiff_decode_only",            "+ Deflate decompression"),
    ("decode_place_u16_natural",    "+ write decoded rows to destination"),
    ("persistent_handle_to_u16",    "+ Y-flipped placement"),
    ("persistent_handle_to_f32",    "+ uint16 to float conversion"),
    ("openperframe_handle_to_f32",  "+ one TIFFOpen per frame"),
    ("production_image_read",       "+ Image/fImageHandler lifecycle and allocation"),
]

CONTEXT_ARMS = [
    "pread_whole_file",
    "tiff_dirscan_persistent",
    "tiff_open_per_frame_meta",
    "convert_u16_to_f32_resident",
    "alloc_first_touch_f32",
    "alloc_first_touch_f32_malloc",
    "alloc_first_touch_f32_perframe",
    "alloc_first_touch_u16",
    "omp_dispatch_only",
]


def load(path):
    with open(path) as f:
        return json.load(f)


def aggregate(doc):
    """Sum per-movie medians into a whole-set total for each (arm, workers).

    Summing per-movie medians is the right aggregate here because the
    production loop processes movies strictly one after another, so the set
    total is the sum of per-movie costs -- not a median of set totals, which
    this harness never measures.
    """
    totals, counts, cpu, exact = {}, {}, {}, {}
    for m in doc.get("movies", []):
        for r in m.get("runs", []):
            k = (r["arm"], r["workers"])
            totals[k] = totals.get(k, 0.0) + r["wall_median_s"]
            cpu[k] = cpu.get(k, 0.0) + r["cpu_median_s"]
            counts[k] = counts.get(k, 0) + 1
            if r.get("produces_pixels"):
                ok = r.get("exact_all_repeats", r.get("exact_equal", False))
                exact[k] = exact.get(k, True) and bool(ok)
    return totals, counts, cpu, exact


def geometry(doc):
    m = doc["movies"][0]
    return {k: m[k] for k in (
        "nx", "ny", "nframes", "bits_per_sample", "sample_format", "compression",
        "predictor", "rows_per_strip", "strips_per_frame", "strips_total",
        "strip_size_bytes", "max_compressed_strip_bytes", "compressed_bytes",
        "decoded_bytes_u16", "decoded_bytes_f32", "file_bytes")}


def fmt_table(rows, headers):
    w = [max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))]
    out = ["| " + " | ".join(str(headers[i]).ljust(w[i]) for i in range(len(headers))) + " |"]
    out.append("|" + "|".join("-" * (w[i] + 2) for i in range(len(headers))) + "|")
    for r in rows:
        out.append("| " + " | ".join(str(r[i]).ljust(w[i]) for i in range(len(r))) + " |")
    return "\n".join(out)


def report(path, label):
    doc = load(path)
    totals, counts, cpu, exact = aggregate(doc)
    if not totals:
        return f"\n### {label}\n\n(no runs in {os.path.basename(path)})\n"

    ws = sorted({w for (_, w) in totals})
    arms = []
    for (a, _) in totals:
        if a not in arms:
            arms.append(a)
    nmov = max(counts.values())

    out = [f"\n### {label}",
           "",
           f"Source: `{os.path.basename(path)}`  ·  regime `{doc['regime']}`  ·  "
           f"mask `{doc['cpu_mask']}` ({doc['cpu_mask_count']} vCPU)  ·  "
           f"median of {doc['repeats']} per movie  ·  {nmov} movie(s), summed",
           ""]

    # ---- full arm x worker table
    rows = []
    for a in arms:
        vals = [totals.get((a, w)) for w in ws]
        present = [v for v in vals if v is not None]
        if not present:
            continue
        best = ws[vals.index(min(present))] if len(present) == len(vals) else "-"
        rows.append([a] + [f"{v:.3f}" if v is not None else "-" for v in vals] + [f"W={best}"])
    out.append("**Wall seconds for the whole set, by decode worker count**")
    out.append("")
    out.append(fmt_table(rows, ["arm"] + [f"W={w}" for w in ws] + ["fastest"]))
    out.append("")

    # ---- attribution chain
    for w in ws:
        chain_present = [(a, d) for a, d in CHAIN if (a, w) in totals]
        if len(chain_present) < len(CHAIN):
            continue
        total = totals[("production_image_read", w)]
        rows, prev = [], 0.0
        for a, desc in CHAIN:
            cur = totals[(a, w)]
            delta = cur - prev
            rows.append([desc, f"{cur:.3f}", f"{delta:+.3f}",
                         f"{100.0 * delta / total:+.1f}%"])
            prev = cur
        out.append(f"**Attribution chain at W={w} (cumulative, and what each step adds)**")
        out.append("")
        out.append(fmt_table(rows, ["component", "cumulative s", "adds s", "share of stage"]))
        out.append("")

    # ---- exactness gate
    gated = sorted({a for (a, _) in exact})
    if gated:
        rows = [[a, "PASS" if all(exact.get((a, w), True) for w in ws) else "FAIL"]
                for a in gated]
        out.append("**Exact ordered pixel equality against the production reference, "
                   "every worker count and every repeat**")
        out.append("")
        out.append(fmt_table(rows, ["arm", "verdict"]))
        out.append("")

    # ---- CPU efficiency, so scaling is judged rather than assumed
    rows = []
    for a in arms:
        if (a, 1) not in totals:
            continue
        base = totals[(a, 1)]
        if base <= 0:
            continue
        rows.append([a] + [f"{base / totals[(a, w)] / w * 100:.0f}%"
                           if (a, w) in totals and totals[(a, w)] > 0 else "-"
                           for w in ws])
    if rows:
        out.append("**Parallel efficiency vs W=1** (speedup / workers; 100% would be linear)")
        out.append("")
        out.append(fmt_table(rows, ["arm"] + [f"W={w}" for w in ws]))
        out.append("")
    return "\n".join(out)


def controls(evdir):
    out = ["\n### Comparator controls", ""]
    sp = os.path.join(evdir, "raw", "selftest.json")
    if os.path.exists(sp):
        d = load(sp)
        rows = []
        for c in d["selftest"]["cases"]:
            if c["mutation"] == "none":
                continue
            rows.append([c["mutation"],
                         "detects" if c["exact_detects"] else "BLIND",
                         "detects" if c["global_sum_detects"] else "BLIND",
                         "detects" if c["row_sums_detect"] else "BLIND",
                         c["n_pixels_differing"]])
        out.append("**Oracle sensitivity** (mutation applied to the reference buffer)")
        out.append("")
        out.append(fmt_table(rows, ["mutation class", "exact ordered",
                                    "global sum", "ordered row sums", "pixels differing"]))
        out.append("")

    rows = []
    for fn in sorted(os.listdir(os.path.join(evdir, "raw"))):
        if not fn.startswith("inject_") or not fn.endswith(".json"):
            continue
        d = load(os.path.join(evdir, "raw", fn))
        r = d["movies"][0]["runs"][0]
        rows.append([d["injected_mutation"] or "none",
                     "FAIL (correct)" if not r["exact_equal"] else "pass",
                     r["n_pixels_differing"]])
    if rows:
        out.append("**Live fault injection** into the real output of `production_image_read`. "
                   "The uninjected row must pass and every injected row must fail, "
                   "or the gate is not falsifiable.")
        out.append("")
        out.append(fmt_table(rows, ["injected fault", "exact-gate verdict", "pixels differing"]))
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("evdir")
    ap.add_argument("--out", default="-")
    args = ap.parse_args()

    raw = os.path.join(args.evdir, "raw")
    chunks = []

    ident = os.path.join(args.evdir, "identity.txt")
    if os.path.exists(ident):
        chunks.append("### Run identity\n\n```\n" + open(ident).read().strip() + "\n```\n")

    for fn in sorted(os.listdir(raw)):
        g = os.path.join(raw, fn)
        if fn == "warm_ext4_rep.json":
            d = load(g)
            chunks.insert(0, "### Input identity\n\n```\n" +
                          "\n".join(f"{k} = {v}" for k, v in geometry(d).items()) + "\n```\n")

    chunks.append(controls(args.evdir))

    for fn, label in [
        ("warm_ext4_rep.json", "Regime 1a - warm page cache, local ext4, one representative movie"),
        ("tmpfs_rep.json",     "Regime 2a - tmpfs (/dev/shm), one representative movie"),
    ]:
        pp = os.path.join(raw, fn)
        if os.path.exists(pp):
            chunks.append(report(pp, label))

    # The per-arm phases write one file per arm. Merge them into one table each,
    # keeping every movie's own median rather than a median of set totals.
    for prefix, label in [
        ("warm_ext4_all24_", "Regime 1b - warm page cache, local ext4, ALL 24 tutorial movies"),
        ("tmpfs_subset_",    "Regime 2b - tmpfs (/dev/shm), 4-movie subset"),
    ]:
        files = sorted(f for f in os.listdir(raw)
                       if f.startswith(prefix) and f.endswith(".json"))
        if not files:
            continue
        agg, spread, nmov, hdr = {}, {}, 0, None
        for f in files:
            d = load(os.path.join(raw, f))
            hdr = hdr or d
            t, c, _, e = aggregate(d)
            for k, v in t.items():
                agg[k] = v
                per = [r["wall_median_s"] for m in d["movies"] for r in m["runs"]
                       if r["workers"] == k[1]]
                spread[k] = (min(per), max(per), len(per))
            nmov = max(nmov, max(c.values()))
        ws = sorted({w for (_, w) in agg})
        arms = []
        for (a, _) in agg:
            if a not in arms:
                arms.append(a)
        out = ["\n### " + label, "",
               "mask `%s` (%d vCPU) · median of %d per movie · %d movies, summed. "
               "Per-movie min/max show how much one movie can mislead: "
               "`20170629_00021` sits at the low end of this set."
               % (hdr["cpu_mask"], hdr["cpu_mask_count"], hdr["repeats"], nmov),
               "",
               "**Read the per-arm totals, not the small differences between them.** "
               "Each arm in this phase is a separate process invocation, so arms did "
               "not run back-to-back under the same machine conditions the way they "
               "do in the representative-movie phase. Differences of a few percent "
               "here are interference, not work: any link below that is reported as "
               "`n/a`. The fine-grained attribution comes from the "
               "representative-movie phase, where every arm is measured inside one "
               "process; this phase exists to confirm that the large components keep "
               "their magnitude across all 24 movies.", ""]
        rows = []
        for a in arms:
            r = [a]
            for w in ws:
                if (a, w) in agg:
                    lo, hi, _ = spread[(a, w)]
                    r.append("%.3f  (%.4f-%.4f)" % (agg[(a, w)], lo, hi))
                else:
                    r.append("-")
            rows.append(r)
        out.append(fmt_table(rows, ["arm"] + ["W=%d  set total (per-movie range)" % w
                                              for w in ws]))
        out.append("")
        # Chain over the merged set totals.
        for w in ws:
            if not all((a, w) in agg for a, _ in CHAIN):
                continue
            total = agg[("production_image_read", w)]
            rows, prev = [], 0.0
            for a, desc in CHAIN:
                cur = agg[(a, w)]
                delta, share = cur - prev, 100.0 * (cur - prev) / total
                # A link this phase cannot resolve: either it went backwards
                # (strictly more work took less time) or it is inside the
                # cross-invocation noise floor.
                unresolved = delta <= 0 or abs(share) < 5.0
                rows.append([desc, "%.3f" % cur,
                             "n/a" if unresolved else "%+.3f" % delta,
                             "n/a" if unresolved else "%+.1f%%" % share])
                prev = cur
            out.append("**Attribution chain at W=%d, whole 24-movie set "
                       "(stage total %.3f s)**" % (w, total))
            out.append("")
            out.append(fmt_table(rows, ["component", "cumulative s", "adds s",
                                        "share of stage"]))
            out.append("")
        # Exact-gate verdict for this phase, from the arms that produce pixels.
        verdicts = []
        for f in files:
            d = load(os.path.join(raw, f))
            for m in d["movies"]:
                for r in m["runs"]:
                    if r.get("produces_pixels"):
                        ok = r.get("exact_all_repeats", r.get("exact_equal", False))
                        verdicts.append((r["arm"], bool(ok)))
        if verdicts:
            byarm = {}
            for arm, ok in verdicts:
                byarm[arm] = byarm.get(arm, True) and ok
            out.append("**Exact ordered pixel equality against the production "
                       "reference, every movie, every worker count, every repeat**")
            out.append("")
            out.append(fmt_table([[k, "PASS" if v else "FAIL"]
                                  for k, v in sorted(byarm.items())],
                                 ["arm", "verdict"]))
            out.append("")
        chunks.append("\n".join(out))

    cold = sorted(f for f in os.listdir(raw) if f.startswith("cold_ext4_") and f.endswith(".json"))
    if cold:
        chunks.append("\n### Regime 3 - cold, per-file page-cache eviction, local ext4\n")
        chunks.append("`posix_fadvise(POSIX_FADV_DONTNEED)` on the movie before every repeat. "
                      "This evicts that file's clean pages only; it does not clear LibTIFF, "
                      "allocator or CPU cache state, so it is a cold-*file* arm, not a cold "
                      "machine.\n")
        agg = {}
        for fn in cold:
            d = load(os.path.join(raw, fn))
            t, c, _, _ = aggregate(d)
            for k, v in t.items():
                agg[k] = v
        ws = sorted({w for (_, w) in agg})
        arms = []
        for (arm, _) in agg:
            if arm not in arms:
                arms.append(arm)
        rows = [[arm] + [f"{agg[(arm, w)]:.3f}" if (arm, w) in agg else "-" for w in ws]
                for arm in arms]
        chunks.append(fmt_table(rows, ["arm"] + [f"W={w}" for w in ws]))
        chunks.append("")

    h2d = os.path.join(raw, "h2d_tutorial.json")
    if os.path.exists(h2d):
        d = load(h2d)
        rows = [[x["arm"], f"{x['bytes'] / 2**30:.3f}", f"{x['wall_median_s'] * 1000:.1f}",
                 f"{x['event_median_s'] * 1000:.1f}", f"{x['event_GBps']:.2f}",
                 f"{x['host_alloc_median_s'] * 1000:.1f}"] for x in d["arms"]]
        chunks.append(f"\n### H2D staging, one movie at tutorial geometry\n\n"
                      f"Device `{d['device_name']}` `{d['device_uuid']}`, "
                      f"median of {d['repeats']}. Wall and CUDA-event time are different "
                      f"quantities and are reported separately, not summed.\n")
        chunks.append(fmt_table(rows, ["arm", "GiB", "wall ms", "event ms",
                                       "event GB/s", "host alloc ms"]))
        chunks.append("")

    text = "\n".join(chunks)
    if args.out == "-":
        sys.stdout.write(text)
    else:
        with open(args.out, "w") as f:
            f.write(text)


if __name__ == "__main__":
    main()
