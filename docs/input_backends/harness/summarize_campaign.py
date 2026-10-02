#!/usr/bin/env python3
"""Turn the campaign log's RESULT lines into the route and performance matrices.

Paired statistics only: every repeat runs both arms on the same variant with the
arm order alternating between repeats, so the per-pair difference removes the
drift a shared host contributes and the order label recovers the positional
bias separately.
"""
import argparse, json, re, statistics, sys
from collections import defaultdict

RESULT = re.compile(r"^RESULT (.*)$")
PAIR = re.compile(r"^PAIR rep=(\d+) order=(\S+)")
ORACLE = re.compile(r"^ORACLE variant=(\S+) (.*)$")


def parse(path):
    runs, oracles, meta = [], {}, {}
    rep, order = None, None
    phase = "p1"
    for line in open(path):
        line = line.rstrip("\n")
        if "PHASE3" in line:
            phase = "p3"
        elif "PHASE2" in line:
            phase = "p2"
        for key in ("SETTLE", "TARGET", "BINARIES"):
            if key in line:
                meta[key] = line.split(key, 1)[1].strip()
        m = PAIR.match(line)
        if m:
            rep, order = int(m.group(1)), m.group(2)
            continue
        m = ORACLE.match(line)
        if m:
            oracles[m.group(1)] = m.group(2)
            continue
        m = RESULT.match(line)
        if m:
            d = dict(kv.split("=", 1) for kv in m.group(1).split() if "=" in kv)
            d["phase"], d["rep"], d["order"] = phase, rep, order
            runs.append(d)
    return runs, oracles, meta


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    runs, oracles, meta = parse(a.log)

    print("## Campaign identity")
    for k, v in meta.items():
        print(f"- {k}: {v}")

    print("\n## Routes and single-pass resources (phase 1)")
    print(f"{'variant':<22}{'arm':<6}{'rc':<4}{'route':<28}{'elapsed_s':>10}{'rss_MiB':>10}{'cpu_s':>9}{'prods':>7}")
    for r in [r for r in runs if r["phase"] == "p1"]:
        rss = fnum(r.get("rss_kb"))
        cpu = (fnum(r.get("user_s")) or 0) + (fnum(r.get("sys_s")) or 0)
        print(f"{r['variant']:<22}{r['arm']:<6}{r['rc']:<4}"
              f"{r.get('routes','?')[:27]:<28}{fnum(r['elapsed']):>10.2f}"
              f"{(rss/1024 if rss else 0):>10.0f}{cpu:>9.1f}{r.get('products','?'):>7}")

    if oracles:
        print("\n## Decoded-sample oracle (phase 2)")
        for v, s in oracles.items():
            print(f"- {v}: {s}")

    print("\n## Paired timed series (phase 3)")
    timed = [r for r in runs if r["phase"] == "p3"]
    by = defaultdict(dict)
    for r in timed:
        by[(r["variant"], r["rep"])][r["arm"]] = r
    summary = {}
    print(f"{'variant':<22}{'n':>3}{'base_med':>10}{'cand_med':>10}{'delta_med':>11}{'delta_range':>20}{'cand_wins':>11}")
    for variant in dict.fromkeys(r["variant"] for r in timed):
        pairs = [(v["base"], v["cand"]) for k, v in sorted(by.items())
                 if k[0] == variant and "base" in v and "cand" in v]
        if not pairs:
            continue
        b = [fnum(p[0]["elapsed"]) for p in pairs]
        c = [fnum(p[1]["elapsed"]) for p in pairs]
        d = [x - y for x, y in zip(b, c)]          # positive = candidate faster
        wins = sum(1 for x in d if x > 0)
        print(f"{variant:<22}{len(d):>3}{statistics.median(b):>10.2f}{statistics.median(c):>10.2f}"
              f"{statistics.median(d):>+11.2f}"
              f"{f'{min(d):+.2f} .. {max(d):+.2f}':>20}{f'{wins}/{len(d)}':>11}")
        summary[variant] = dict(n=len(d), base=b, cand=c, delta=d,
                                base_median=statistics.median(b),
                                cand_median=statistics.median(c),
                                delta_median=statistics.median(d),
                                candidate_faster_pairs=wins)
        # Positional bias: the advantage to whichever arm ran second.
        second = [fnum(p[1]["elapsed"]) - fnum(p[0]["elapsed"])
                  for p in pairs if p[0].get("order", "").startswith("base")]
        first = [fnum(p[0]["elapsed"]) - fnum(p[1]["elapsed"])
                 for p in pairs if p[0].get("order", "").startswith("cand")]
        if second and first:
            summary[variant]["order_split"] = dict(base_first=second, cand_first=first)

    if a.json:
        json.dump(dict(meta=meta, phase1=[r for r in runs if r["phase"] == "p1"],
                       oracles=oracles, paired=summary), open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
