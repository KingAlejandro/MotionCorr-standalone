#!/usr/bin/env python3
"""Summarise a rotated multi-arm timing campaign.

Reads `<prefix>_<arm>_<round>.time` (GNU `time -v`) and the matching `.stdout`
(a -DTIMING=ON stage table) from one directory, and reports per-arm wall time,
per-round paired differences against a reference arm, and the stage table.

Round-paired, because the arms within a round ran back to back under the same
conditions; the arm order is rotated across rounds, so the positional bias
lands on each arm equally rather than on one.
"""
import argparse
import re
import statistics
from collections import defaultdict
from pathlib import Path

# The label itself contains colons ("(h:mm:ss or m:ss)"), so anchor on the
# end of the line rather than on the first colon.
WALL = re.compile(r"Elapsed \(wall clock\).*?(?:(\d+):)?(\d+):([\d.]+)\s*$", re.M)
RSS = re.compile(r"Maximum resident set size \(kbytes\):\s*(\d+)")
USER = re.compile(r"User time \(seconds\):\s*([\d.]+)")
SYS = re.compile(r"System time \(seconds\):\s*([\d.]+)")
STAGE = re.compile(r"^(.+?)\s*:\s*([\d.]+) sec \((\d+) microsec/operation\)$")


def parse_time(path: Path):
    text = path.read_text(errors="replace")
    m = WALL.search(text)
    if not m:
        return None
    h, mi, s = m.group(1) or 0, m.group(2), m.group(3)
    out = {"wall": int(h) * 3600 + int(mi) * 60 + float(s)}
    for key, rx in (("rss_kb", RSS), ("user", USER), ("sys", SYS)):
        found = rx.search(text)
        if found:
            out[key] = float(found.group(1))
    return out


def parse_stages(path: Path):
    stages = {}
    if not path.is_file():
        return stages
    for line in path.read_text(errors="replace").splitlines():
        m = STAGE.match(line.strip())
        if m:
            stages[m.group(1).strip()] = float(m.group(2))
    return stages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", type=Path)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--arms", nargs="+", required=True)
    ap.add_argument("--reference", required=True)
    args = ap.parse_args()

    runs = defaultdict(dict)   # arm -> round -> metrics
    stages = defaultdict(dict)
    for arm in args.arms:
        for path in sorted(args.directory.glob(f"{args.prefix}_{arm}_*.time")):
            rnd = path.stem.rsplit("_", 1)[1]
            parsed = parse_time(path)
            if parsed:
                runs[arm][rnd] = parsed
                stages[arm][rnd] = parse_stages(path.with_suffix(".stdout"))

    print(f"{'arm':8s} {'n':>3s} {'wall min':>9s} {'wall max':>9s} {'median':>9s} "
          f"{'user':>7s} {'sys':>7s} {'peak RSS MiB':>13s}")
    for arm in args.arms:
        walls = sorted(r["wall"] for r in runs[arm].values())
        if not walls:
            continue
        rss = max(r.get("rss_kb", 0) for r in runs[arm].values()) / 1024
        user = statistics.median(r.get("user", 0) for r in runs[arm].values())
        sysx = statistics.median(r.get("sys", 0) for r in runs[arm].values())
        print(f"{arm:8s} {len(walls):3d} {walls[0]:9.2f} {walls[-1]:9.2f} "
              f"{statistics.median(walls):9.2f} {user:7.1f} {sysx:7.1f} {rss:13.0f}")

    ref = args.reference
    for arm in args.arms:
        if arm == ref:
            continue
        rounds = sorted(set(runs[ref]) & set(runs[arm]), key=int)
        diffs = [runs[arm][r]["wall"] - runs[ref][r]["wall"] for r in rounds]
        if not diffs:
            continue
        better = sum(d < 0 for d in diffs)
        print(f"\npaired {arm} - {ref}: n={len(diffs)}  "
              f"per-round {[round(d, 2) for d in diffs]}")
        print(f"  median {statistics.median(diffs):+.2f} s "
              f"({100 * statistics.median(diffs) / statistics.median([runs[ref][r]['wall'] for r in rounds]):+.1f}%), "
              f"faster in {better}/{len(diffs)} rounds, "
              f"range {min(diffs):+.2f} to {max(diffs):+.2f} s")
        overlap = (max(runs[arm][r]['wall'] for r in rounds) >=
                   min(runs[ref][r]['wall'] for r in rounds))
        print(f"  arm ranges overlap: {overlap}")

    tags = []
    for arm in args.arms:
        for per_round in stages[arm].values():
            for tag in per_round:
                if tag not in tags:
                    tags.append(tag)
    if tags:
        print(f"\n--- median stage seconds ---\n{'stage':34s}" +
              "".join(f"{a:>10s}" for a in args.arms))
        for tag in tags:
            cells = ""
            for arm in args.arms:
                vals = [s[tag] for s in stages[arm].values() if tag in s]
                cells += f"{statistics.median(vals):10.3f}" if vals else f"{'-':>10s}"
            print(f"{tag:34s}{cells}")


if __name__ == "__main__":
    main()
