#!/usr/bin/env python3
"""Summarise an `envelope_runner.py` series into tables and a product-equality verdict.

Ordering matters: the product verdict is computed first and reported first, because a timing
table for arms that did not all produce the same outputs is not a comparison. An arm that
lost a movie, or produced different pixels, is not a faster arm.

Products are compared as MRC payload and core header separately. The label block at offset
224 carries an `strftime` timestamp and is expected to differ between any two runs; a
whole-file digest would therefore report every arm as mismatched and prove nothing.

Three other product types carry per-run content that is not a numerical result. They are
**normalised and then compared**, not dropped, so they stay inside the equality claim:

- `_shifts.eps` embeds its own absolute output path in the plot title, which necessarily
  differs between two arms because they write to different directories. The path is
  substituted out and the rest of the PostScript — including every plotted shift — is
  compared.
- `.log` embeds the measured GPU profile in milliseconds, which differs between any two runs
  by construction. Numeric timings are substituted out and the remaining text is compared.
- `.pdf` is the one exception: ghostscript embeds a creation date and an ID derived from it,
  so only presence and byte count are checked. This is stated as a limitation, not hidden.

Arms are compared only against a reference that consumed the same input set. A 4-movie
screening arm and a 24-movie baseline arm do not have comparable product sets, and scoring
one against the other would report a difference that means nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

TIMESTAMPED = (".pdf",)
TIMING_VALUE = re.compile(rb"[0-9]+\.[0-9]+(?=\s*(?:ms|sec|s)\b)")
# Lines in a per-movie log that echo the configuration under test. They are removed from the
# parity digest and checked separately -- they are the witness that the requested settings
# actually took effect, which is worth more than treating them as noise.
CONFIG_ECHO = re.compile(
    rb"^(?:Working on .* with \d+ thread\(s\)\.|"
    rb"Limitted the number of IO threads per movie to \d+ thread\(s\)\.)[ \t]*\r?\n", re.M)
EFFECTIVE_J = re.compile(rb"Working on .* with (\d+) thread\(s\)\.")
EFFECTIVE_IO = re.compile(rb"Limitted the number of IO threads per movie to (\d+) thread\(s\)\.")
# The project's exact gate enforces MRC labels 224-1023 with only RELION's clock stamp in the
# first 80-byte label masked (docs/gate_contract.md, "MRC labels 224-1023, run timestamp
# masked | enforced"; tools/compare_motioncorr.py:161-166). Dropping the label block instead
# would make this report strictly weaker than the gate the project already publishes. The
# rule is reimplemented rather than imported because compare_motioncorr.py needs NumPy, which
# is not installed on the GPU benchmark host.
MRC_TIMESTAMP = re.compile(rb"\b\d{2}-[A-Za-z]{3}-\d{2}\s+\d{2}:\d{2}:\d{2}\b")


def normalized_mrc_labels(path: Path) -> Optional[str]:
    try:
        labels = bytearray(path.read_bytes()[224:1024])
    except Exception:
        return None
    if len(labels) < 800:
        return None
    labels[:80] = MRC_TIMESTAMP.sub(lambda m: b"0" * len(m.group()), bytes(labels[:80]))
    return hashlib.sha256(bytes(labels)).hexdigest()


def normalized_bytes(path: Path, out_root: Path) -> bytes:
    """Content with per-run, non-result artefacts substituted out.

    Every arm writes to its own directory and MotionCorr embeds the absolute output path in
    its text products -- the EPS plot title, `corrected_micrographs.star`, and the `.pdf.lst`
    file lists. Substituting the run's own output root is therefore the general rule, not an
    EPS special case; without it every text product differs between any two arms for a reason
    that has nothing to do with the computation.
    """
    raw = path.read_bytes()
    if path.suffix == ".mrc":
        return raw
    raw = raw.replace(str(out_root).encode(), b"<OUTDIR>")
    if path.suffix == ".log":
        raw = CONFIG_ECHO.sub(b"", TIMING_VALUE.sub(b"<T>", raw))
    return raw


def effective_settings_from_logs(out_root: Path) -> Dict[str, Any]:
    """Read back what the binary says it actually used, per movie."""
    js, ios, n = set(), set(), 0
    for lg in sorted(out_root.rglob("*.log")):
        raw = lg.read_bytes()
        n += 1
        m = EFFECTIVE_J.search(raw)
        if m:
            js.add(int(m.group(1)))
        m = EFFECTIVE_IO.search(raw)
        ios.add(int(m.group(1)) if m else None)
    return {"movies_with_logs": n,
            "reported_j": sorted(js),
            "reported_io_cap": sorted(x for x in ios if x is not None),
            "movies_without_io_cap_line": sum(1 for x in ios if x is None)}


def product_key(run: Dict[str, Any], results_dir: Optional[Path]) -> Dict[str, Any]:
    """Comparable fingerprint of one arm's output set."""
    payloads, headers, labels, others, stamped = {}, {}, {}, {}, {}
    unnormalised, unparseable = [], []
    out_root = (results_dir / run["tag"] / "out") if results_dir else None
    for p in run["products"]:
        path = p["path"]
        if path.endswith(TIMESTAMPED):
            stamped[path] = p["bytes"]
        elif p.get("mrc") and not p["mrc"].get("error"):
            payloads[path] = p["mrc"]["payload_sha256"]
            headers[path] = p["mrc"]["core_header_sha256"]
            f = out_root / path if out_root else None
            nl = normalized_mrc_labels(f) if f and f.is_file() else None
            if nl:
                labels[path] = nl
            else:
                unnormalised.append(path + " (labels)")
        elif path.endswith((".mrc", ".mrcs")):
            # Never fall through to a whole-file digest here. That digest includes the
            # timestamped label block, so it is guaranteed to differ and would report a
            # parse failure as an ordinary pixel mismatch.
            unparseable.append(f"{path}: {(p.get('mrc') or {}).get('error', 'not digested')}")
        else:
            # All remaining products are text that may embed the run's own output path.
            f = out_root / path if out_root else None
            if f is not None and f.is_file():
                others[path] = hashlib.sha256(normalized_bytes(f, out_root)).hexdigest()
            else:
                # Without the files we cannot normalise, and an un-normalised digest would
                # report a difference that is only the embedded path or timing. Record the
                # gap rather than scoring a comparison that cannot mean anything.
                unnormalised.append(path)
    return {"payloads": payloads, "core_headers": headers, "labels": labels,
            "others": others, "timestamped_bytes": stamped,
            "not_normalisable": unnormalised, "unparseable": unparseable}


def compare_products(ref: Dict[str, Any], test: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field in ("payloads", "core_headers", "labels", "others"):
        r, t = ref[field], test[field]
        missing = sorted(set(r) - set(t))
        extra = sorted(set(t) - set(r))
        differing = sorted(k for k in set(r) & set(t) if r[k] != t[k])
        out[field] = {"n_ref": len(r), "n_test": len(t), "missing": missing,
                      "extra": extra, "differing": differing,
                      "equal": not (missing or extra or differing)}
    rs, ts = ref["timestamped_bytes"], test["timestamped_bytes"]
    missing, extra = sorted(set(rs) - set(ts)), sorted(set(ts) - set(rs))
    # Presence gates the verdict; size does not. Ghostscript output here is nondeterministic
    # in length: the same arm re-run gave logfile.pdf of 104632 and 104634 bytes with every
    # other product bit-identical, and across --j the sizes scatter without order
    # (104640, 104640, 104640, 104777, 104639, 104640). Gating on size would fail arms for a
    # property of the PDF writer, which this project already tracks separately as the known
    # PDF differences. A lost PDF is still a lost product and still fails.
    resized = sorted(k for k in set(rs) & set(ts) if abs(rs[k] - ts[k]) > 64)
    out["timestamped"] = {
        "n_ref": len(rs), "n_test": len(ts), "missing": missing, "extra": extra,
        "size_differs_beyond_64B": resized,
        "equal": not (missing or extra),
        "note": "presence gates the verdict; content and size do not. Ghostscript embeds a "
                "generation date and its output length is nondeterministic here, which is "
                "the project's separately tracked PDF difference, not a result difference.",
    }
    out["not_normalisable"] = sorted(set(ref.get("not_normalisable", []))
                                     | set(test.get("not_normalisable", [])))
    out["unparseable"] = sorted(set(ref.get("unparseable", []))
                                | set(test.get("unparseable", [])))
    # [2.6] Two empty product sets trivially satisfy every set difference. Without this
    # guard, a series in which every arm crashed at startup reports every arm EQUAL.
    n_products = sum(len(ref[f]) for f in ("payloads", "core_headers", "others")) \
        + len(ref["timestamped_bytes"])
    if n_products == 0:
        out["verdict"] = "NO_PRODUCTS"
        return out
    out["verdict"] = "EQUAL" if all(out[f]["equal"] for f in
                                    ("payloads", "core_headers", "labels", "others",
                                     "timestamped")) else "DIFFERS"
    if out["unparseable"]:
        out["verdict"] = "UNPARSEABLE"      # not a pixel mismatch; do not report it as one
    elif out["not_normalisable"]:
        out["verdict"] += "+UNVERIFIED"
    return out


def fmt(x: Optional[float], nd: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", type=Path, required=True, help="series.json from the runner")
    ap.add_argument("--reference-arm", action="append", required=True,
                    help="arm id whose products define the same-backend baseline for its own "
                         "input set; repeat once per distinct input set")
    ap.add_argument("--results-dir", type=lambda x: Path(x).resolve(),
                    help="directory holding the per-run output trees, so .eps/.log can be "
                         "normalised before comparison instead of excluded")
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    data = json.loads(args.series.read_text())
    runs = [r for r in data["runs"] if r["rep"] != 0]        # rep 0 is the declared warm-up
    warmups = [r for r in data["runs"] if r["rep"] == 0]

    failed = [r["tag"] for r in runs if r["exit_code"] != 0]

    # ---------------------------------------------------- product equality, computed first
    # Each arm is scored against the reference that consumed the SAME input set. Scoring a
    # 4-movie screening arm against a 24-movie baseline would report 20 missing movies, which
    # is a property of the plan, not of the configuration under test.
    arm_input = {a["id"]: a["input_star"] for a in data.get("arms", [])} \
        if data.get("arms") else {}
    if not arm_input:
        arm_input = {r["arm_id"]: r["command"][r["command"].index("--i") + 1]
                     for r in data["runs"] if "--i" in r["command"]}

    refs: Dict[str, Dict[str, Any]] = {}
    for rid in args.reference_arm:
        rr = [r for r in runs if r["arm_id"] == rid and r["exit_code"] == 0
              and r.get("product_count", 0) > 0]
        if not rr:
            # Selecting from the unfiltered run list would allow the baseline to be the
            # warm-up this script has already declared non-comparable, or a run that died.
            print(f"ERROR: reference arm {rid} has no successful non-warm-up run with products")
            return 2
        refs[arm_input.get(rid, "?")] = {"tag": rr[0]["tag"],
                                         "key": product_key(rr[0], args.results_dir)}

    by_arm: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in runs:
        by_arm[r["arm_id"]].append(r)

    prod: Dict[str, Any] = {}
    unscored: List[str] = []
    for arm, rs in by_arm.items():
        iset = arm_input.get(arm, "?")
        if iset not in refs:
            unscored.append(f"{arm} (input {iset})")
            continue
        ref = refs[iset]["key"]
        # Compare every run, not one per arm: a product difference that appears in only one
        # repeat is exactly the kind that a one-run-per-arm check would miss.
        per_run = {r["tag"]: compare_products(ref, product_key(r, args.results_dir))
                   for r in rs}
        eff = {}
        if args.results_dir:
            for r in rs:
                o = args.results_dir / r["tag"] / "out"
                if o.is_dir():
                    got = effective_settings_from_logs(o)
                    want_j, want_io = r["effective"]["j"], r["effective"]["io_threads"]
                    got["requested_j"] = want_j
                    got["requested_effective_io"] = want_io
                    # The binary only prints the IO line when it actually clamps, so an
                    # uncapped arm correctly has no line and its effective IO equals j.
                    io_ok = (got["reported_io_cap"] == [want_io]
                             if want_io != want_j else not got["reported_io_cap"])
                    got["matches_request"] = (got["reported_j"] == [want_j]) and io_ok
                    eff[r["tag"]] = got
        verdicts = sorted({v["verdict"] for v in per_run.values()})
        prod[arm] = {"runs": per_run, "input_set": iset, "effective_settings_witness": eff,
                     "verdicts": verdicts,
                     "reference": refs[iset]["tag"],
                     "all_equal": all(v["verdict"] == "EQUAL" for v in per_run.values()),
                     "product_counts": sorted({r["product_count"] for r in rs})}

    print("=" * 78)
    print("PRODUCT EQUALITY, each arm vs the reference for its own input set")
    for iset, r in sorted(refs.items()):
        print(f"  input '{iset}' -> reference run {r['tag']}")
    if not args.results_dir:
        print("  WARNING: --results-dir not given, so .eps/.log cannot be normalised and are "
              "reported as UNVERIFIED rather than compared")
    print("=" * 78)
    n_bad = 0
    for arm in sorted(prod):
        v = prod[arm]
        flag = "/".join(v["verdicts"])
        if not v["all_equal"]:
            n_bad += 1
        wit = v.get("effective_settings_witness") or {}
        ok = all(w.get("matches_request") for w in wit.values()) if wit else None
        eff_flag = {True: "settings-confirmed", False: "SETTINGS-MISMATCH",
                    None: "settings-unchecked"}[ok]
        print(f"  {arm:<28} {flag:<8} products={v['product_counts']}  {eff_flag}")
        if ok is False:
            for tag, w in wit.items():
                if not w.get("matches_request"):
                    print(f"      {tag}: requested j={w['requested_j']} "
                          f"io={w['requested_effective_io']} but logs report "
                          f"j={w['reported_j']} io_cap={w['reported_io_cap']}")
        if not v["all_equal"]:
            for tag, c in v["runs"].items():
                if c["verdict"] == "EQUAL":
                    continue
                if c.get("unparseable"):
                    print(f"      {tag} COULD NOT PARSE: {c['unparseable'][:3]}")
                if c.get("not_normalisable"):
                    print(f"      {tag} NOT CHECKED (needs --results-dir): "
                          f"{c['not_normalisable'][:3]}")
                if c["verdict"] == "NO_PRODUCTS":
                    print(f"      {tag} produced NO PRODUCTS AT ALL")
                for f in ("payloads", "core_headers", "labels", "others", "timestamped"):
                    d = c[f]
                    if not d.get("equal", True):
                        print(f"      {tag} {f}: differing="
                              f"{(d.get('differing') or d.get('size_differs_beyond_64B'))[:4]} "
                              f"missing={d['missing'][:4]} extra={d['extra'][:4]}")
    print(f"\n  arms with differing products: {n_bad} of {len(prod)}")
    if unscored:
        print(f"  arms with no same-input reference, NOT scored: {unscored}")
    print(f"  non-zero exits: {failed if failed else 'none'}")
    if warmups:
        print(f"  declared warm-up runs excluded from tables: "
              f"{[w['tag'] + ' ' + str(w['wall_s']) + 's' for w in warmups]}")

    # ------------------------------------------------------------------- timing, second
    print("\n" + "=" * 78)
    print("WALL TIME BY ARM")
    print("=" * 78)
    print(f"  {'arm':<26} {'input set':<14} {'n':>2} {'median':>8} {'min':>8} {'max':>8} "
          f"{'spread%':>8} {'cpu_s':>8} {'RSS_MiB':>8} {'VRAM':>6}")
    print("  arms consuming different input sets are NOT comparable on time; the input-set\n"
          "  column exists so a 4-movie screening arm is not read against a 24-movie arm.")
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
        table[arm] = {"input_set": arm_input.get(arm, "?"), "n": len(w), "median_s": med, "min_s": min(w), "max_s": max(w),
                      "spread_pct": spread, "walls": w,
                      "median_cpu_s": statistics.median(cpu) if cpu else None,
                      "peak_rss_mib": max(rss) // 1024 if rss and max(rss) else None,
                      "peak_vram_mib_sampled": max(vram) if vram else None,
                      "effective": rs[0]["effective"]}
        t = table[arm]
        print(f"  {arm:<26} {str(arm_input.get(arm,'?'))[:14]:<14} {t['n']:>2} "
              f"{fmt(med):>8} {fmt(min(w)):>8} {fmt(max(w)):>8} {fmt(spread,1):>8} "
              f"{fmt(t['median_cpu_s'],1):>8} {str(t['peak_rss_mib']):>8} "
              f"{str(t['peak_vram_mib_sampled']):>6}")

    # ------------------------------------------- paired contrasts, with the positional split
    print("\n" + "=" * 78)
    print("PAIRED CONTRASTS  (two-arm pairs only; d = t_second_named - t_first_named)")
    print("=" * 78)
    pairs: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in runs:
        pairs[r["pair_index"]].append(r)

    contrasts: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    degenerate = 0
    for pidx, rs in pairs.items():
        if len(rs) != 2 or rs[0]["arm_id"] == rs[1]["arm_id"]:
            degenerate += 1
            continue
        a, b = sorted(rs, key=lambda r: r["arm_id"])
        key = f"{b['arm_id']} - {a['arm_id']}"
        first = min(rs, key=lambda r: r["order_in_pair"])["arm_id"]
        contrasts[key].append({"pair": pidx, "d": b["wall_s"] - a["wall_s"],
                               "first": first, "ta": a["wall_s"], "tb": b["wall_s"]})

    if not contrasts:
        print("  no two-arm pairs in this series (screening schedules are not paired)")
    for key, ds in sorted(contrasts.items()):
        b_name, a_name = key.split(" - ")
        d_all = [x["d"] for x in ds]
        # observed = E -/+ P, where P is the advantage to whichever arm ran second.
        d_a_first = [x["d"] for x in ds if x["first"] == a_name]
        d_b_first = [x["d"] for x in ds if x["first"] == b_name]
        n_b_faster = sum(1 for d in d_all if d < 0)
        print(f"\n  {key}")
        print(f"    n pairs               : {len(d_all)}")
        print(f"    per-pair d (s)        : {[round(d, 3) for d in d_all]}")
        print(f"    mean d                : {statistics.fmean(d_all):+.3f} s")
        if len(d_all) > 1:
            sd = statistics.stdev(d_all)
            sem = sd / len(d_all) ** 0.5
            print(f"    sd / sem              : {sd:.3f} / {sem:.3f} s")
            print(f"    mean d +/- 2 sem      : {statistics.fmean(d_all):+.3f} "
                  f"+/- {2 * sem:.3f} s")
            crosses = abs(statistics.fmean(d_all)) < 2 * sem
            print(f"    interval spans zero   : {'YES - no effect resolved at this n'
                                                 if crosses else 'no'}")
        print(f"    pairs where {b_name} faster: {n_b_faster}/{len(d_all)}"
              f"   (two-sided sign test needs {len(d_all)} >= 6 to reach even the 5% level)")
        if d_a_first and d_b_first:
            E = (statistics.fmean(d_a_first) + statistics.fmean(d_b_first)) / 2
            P = (statistics.fmean(d_b_first) - statistics.fmean(d_a_first)) / 2
            print(f"    order-split           : E = {E:+.3f} s, positional P = {P:+.3f} s "
                  f"(advantage to whichever arm ran second)")
        else:
            print("    order-split           : NOT AVAILABLE - every pair ran in the same "
                  "order, so effect and position are confounded")
    if degenerate:
        print(f"\n  {degenerate} pair group(s) skipped: not exactly two distinct arms")

    # ----------------------------------------------- schedule validation, then slot ratios
    print("\n" + "=" * 78)
    print("SCHEDULE VALIDATION AND POSITIONAL SLOT RATIOS")
    print("=" * 78)
    arms_by_slot: Dict[int, set] = defaultdict(set)
    for r in runs:
        arms_by_slot[r["order_in_pair"]].add(r["arm_id"])
    fixed = [o for o, a in arms_by_slot.items() if len(a) == 1 and len(arms_by_slot) > 1]
    if fixed:
        # Without this check the slot-ratio estimator below is vacuous: if each arm always
        # occupies the same slot, every ratio is that arm's own wall over its own median,
        # i.e. ~1.0 by construction, and the section reads as "no positional bias found"
        # no matter how large the real bias is.
        print(f"  WARNING: slots {sorted(fixed)} were always occupied by a single arm, so the "
              f"ratios below\n  cannot detect positional bias and must not be read as "
              f"evidence of its absence.")
    else:
        print("  every slot was occupied by more than one arm, so the ratios below are "
              "informative")
    by_order: Dict[int, List[float]] = defaultdict(list)
    for r in runs:
        med = table[r["arm_id"]]["median_s"]
        if med:
            by_order[r["order_in_pair"]].append(r["wall_s"] / med)
    for o in sorted(by_order):
        v = by_order[o]
        print(f"  slot {o:>2}: n={len(v):>2} arms={len(arms_by_slot[o]):>2} "
              f"mean ratio to arm median = {statistics.fmean(v):.4f}")

    # ------------------------------------------------------------------------ interference
    print("\n" + "=" * 78)
    print("INTERFERENCE (threads outside this run's subtree, sampled during the run)")
    print("=" * 78)
    for arm in sorted(by_arm):
        rs = by_arm[arm]
        nobs = sum(r["sampling"]["foreign_cpu_pct"].get("n", 0) for r in rs)
        if nobs == 0:
            # stats([]) has no "max" key, so a .get(...,0) default would render a sampler
            # that raised on every tick as an arm with no interference.
            print(f"  {arm:<28} NOT OBSERVED: the foreign sampler produced no samples")
            continue
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
             "paired_contrasts": {k: v for k, v in contrasts.items()},
             "positional": {str(k): statistics.fmean(v) for k, v in by_order.items()}},
            indent=2))
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
