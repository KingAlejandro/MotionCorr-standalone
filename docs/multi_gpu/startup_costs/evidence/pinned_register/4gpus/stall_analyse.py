"""Summarise stall_ab.sh output: where each run's time went, THP/compaction counters,
and paired differences against main.  usage: stall_analyse.py <outdir>"""
import json, re, statistics as st, sys, collections
from math import comb

R = sys.argv[1]
med = st.median
ING = "session and device ingest/device ingest/ingest setup"

def kv(path):
    d = {}
    for tok in open(path).read().split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            d[k] = int(v)
    return d

def own_cpu_s(path):
    t = open(path).read()
    u = float(re.search(r"User time \(seconds\): ([\d.]+)", t).group(1))
    s = float(re.search(r"System time \(seconds\): ([\d.]+)", t).group(1))
    return u + s

def sign_p(d):
    n = len(d); w = sum(x < 0 for x in d); k = min(w, n - w)
    return w, n, min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)

rows = {}
for r in (json.loads(l) for l in open(f"{R}/runs.jsonl")):
    tag = r["tag"]
    if tag.startswith("warm"):
        continue
    rd, n, arm = tag.split("_", 2)
    L = [json.loads(l) for l in open(f"{R}/{tag}/profile.jsonl")]
    mv = [x for x in L if x["type"] == "movie"]; pr = [x for x in L if x["type"] == "process"][0]
    walls = [m["wall_ms"] for m in mv]
    steady = med(walls[1:])
    b, a = kv(f"{R}/{tag}/vm_before.txt"), kv(f"{R}/{tag}/vm_after.txt")
    wall_s = r["proc_wall_ms"] / 1e3
    rows[(rd, n, arm)] = dict(
        rc=r["rc"], nmrc=r["n_mrc"], proc=r["proc_wall_ms"], run=pr["run_wall_ms"],
        outside=r["proc_wall_ms"] - pr["run_wall_ms"], first=walls[0],
        ingest_setup=next((s["wall_ms"] for s in mv[0]["sub"] if s["name"] == ING), float("nan")),
        excess=sum(w - steady for w in walls[1:]), steady=steady,
        worst=max(range(1, len(walls)), key=lambda i: walls[i]), worst_ms=max(walls[1:]),
        foreign=(r["lane_busy_jiffies"] / 100 - own_cpu_s(f"{R}/{tag}/time.txt")) / wall_s,
        blocks=b.get("free_2m_blocks", -1),
        **{"d_" + k: a[k] - b[k] for k in a if k in b})

arms = sorted({k[2] for k in rows}, key=lambda a: (a != "main", a))
VM = ["d_compact_stall", "d_compact_fail", "d_thp_fault_alloc", "d_thp_fault_fallback", "d_allocstall_normal"]
for n in ("n24", "n96"):
    rounds = sorted({k[0] for k in rows if k[1] == n}, key=lambda s: int(s[1:]))
    if not rounds:
        continue
    print(f"\n== {n}: per run (ms unless stated; excess = sum over movies 2.. of wall - steady median)")
    print("%-5s %-5s %7s %7s %7s %6s %6s %7s %5s %6s %6s %8s " % (
        "round", "arm", "proc", "run", "outside", "first", "ingset", "excess", "worst", "frgn", "blocks", "") +
        " ".join("%9s" % v[2:][-9:] for v in VM))
    for rd in rounds:
        for arm in arms:
            x = rows.get((rd, n, arm))
            if not x:
                continue
            print("%-5s %-5s %7d %7.0f %7.0f %6.0f %6.1f %7.0f %5d %6.2f %6d %8s " % (
                rd, arm, x["proc"], x["run"], x["outside"], x["first"], x["ingest_setup"], x["excess"],
                x["worst"], x["foreign"], x["blocks"], "") + " ".join("%9d" % x.get(v, -1) for v in VM))
    print(f"\n== {n}: medians")
    for arm in arms:
        v = [rows[(rd, n, arm)] for rd in rounds if (rd, n, arm) in rows]
        print("  %-5s n=%2d proc %7.0f run %7.0f outside %5.0f first %5.0f ingest_setup %5.1f (max %5.1f) excess %6.0f"
              " compact_stall %s thp_fallback %s rc=%s mrc=%s" % (
                  arm, len(v), med(x["proc"] for x in v), med(x["run"] for x in v), med(x["outside"] for x in v),
                  med(x["first"] for x in v), med(x["ingest_setup"] for x in v), max(x["ingest_setup"] for x in v),
                  med(x["excess"] for x in v), [x["d_compact_stall"] for x in v], [x["d_thp_fault_fallback"] for x in v],
                  {x["rc"] for x in v}, {x["nmrc"] for x in v}))
    print(f"\n== {n}: arm minus main, paired by round (negative = arm faster)")
    for arm in arms:
        if arm == "main":
            continue
        for m in ("proc", "run", "outside", "first", "ingest_setup", "excess"):
            d = [rows[(rd, n, arm)][m] - rows[(rd, n, "main")][m] for rd in rounds
                 if (rd, n, arm) in rows and (rd, n, "main") in rows]
            w, nn, p = sign_p(d)
            print("  %-3s %-13s median %8.1f  arm<main %2d/%-2d p=%.3f  [%s]" % (
                arm, m, med(d), w, nn, p, ", ".join("%.0f" % x for x in d)))
    # slow runs: process wall more than 0.5 s above the arm's median for this size
    print(f"\n== {n}: slow runs (proc > arm median + 500 ms)")
    for arm in arms:
        v = {rd: rows[(rd, n, arm)] for rd in rounds if (rd, n, arm) in rows}
        m0 = med(x["proc"] for x in v.values())
        for rd, x in v.items():
            if x["proc"] > m0 + 500:
                print("  %-5s %-5s proc +%5.0f: ingest_setup %5.1f, mid-run excess %6.0f (worst movie %d, %4.0f ms),"
                      " outside %5.0f, foreign %.2f cores, compact_stall +%d, thp_fallback +%d" % (
                          rd, arm, x["proc"] - m0, x["ingest_setup"], x["excess"], x["worst"], x["worst_ms"],
                          x["outside"], x["foreign"], x["d_compact_stall"], x["d_thp_fault_fallback"]))
