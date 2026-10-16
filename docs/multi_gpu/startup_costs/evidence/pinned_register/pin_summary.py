"""Medians of pin_probe output.  usage: pin_summary.py <probe-pin.jsonl>..."""
import collections, json, statistics as st, sys
for path in sys.argv[1:]:
    d = collections.defaultdict(list)
    for l in open(path):
        r = json.loads(l); d[r["method"]].append(r)
    print(path)
    for m, v in d.items():
        a = [x["acquire_ms"] for x in v]; r = [x["release_ms"] for x in v]
        print("  %-9s n=%2d acquire med %6.1f [%6.1f-%6.1f] release med %5.1f  huge_kb %s  compact_stall %d thp_fallback %d" % (
            m, len(v), st.median(a), min(a), max(a), st.median(r), sorted({x["anon_huge_kb"] for x in v}),
            sum(x.get("d_compact_stall", 0) for x in v), sum(x.get("d_thp_fault_fallback", 0) for x in v)))
