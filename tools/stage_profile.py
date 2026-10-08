#!/usr/bin/env python3
"""Summarise MotionCorr --profile output (docs/stage_profile.md).

    stage_profile.py run.jsonl                 per-stage table for one run
    stage_profile.py base.jsonl cand.jsonl     per-stage paired comparison
    stage_profile.py --check run.jsonl         validate exhaustiveness and exit

Standard library only. The first movie of each run carries one-off process and
CUDA warm-up; steady-state figures therefore exclude it, and the table also
reports it separately.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import OrderedDict, defaultdict
from typing import Dict, List


def load(path: str):
    movies, process = [], None
    with open(path) as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{n}: invalid JSON: {e}")
            if rec.get("type") == "movie":
                movies.append(rec)
            elif rec.get("type") == "process":
                process = rec
    if not movies:
        raise SystemExit(f"{path}: no movie records")
    return movies, process


def check(movies, tol_ms: float = 0.5) -> List[str]:
    """Stages must tile each movie: their wall sum equals the movie wall."""
    problems = []
    for m in movies:
        s = sum(st["wall_ms"] for st in m["stages"])
        if abs(s - m["wall_ms"]) > tol_ms:
            problems.append(f"movie {m['index']}: stages sum {s:.3f} ms != movie {m['wall_ms']:.3f} ms")
    return problems


def per_stage(movies, skip_first: bool) -> "OrderedDict[str, Dict[str, List[float]]]":
    use = movies[1:] if skip_first and len(movies) > 1 else movies
    table: "OrderedDict[str, Dict[str, List[float]]]" = OrderedDict()
    for m in use:
        for st in m["stages"]:
            row = table.setdefault(st["name"], defaultdict(list))
            for k in ("wall_ms", "cpu_ms", "minflt", "vcsw", "ivcsw"):
                row[k].append(st.get(k, 0))
    # Movies that skipped a stage contribute zero, so sums stay comparable.
    for row in table.values():
        for k in row:
            row[k] += [0] * (len(use) - len(row[k]))
    return table


def summary(path: str):
    movies, process = load(path)
    problems = check(movies)
    n = len(movies)
    steady = movies[1:] if n > 1 else movies
    t = per_stage(movies, skip_first=True)
    total = sum(m["wall_ms"] for m in steady)
    print(f"{path}: {n} movies; first movie {movies[0]['wall_ms']:.0f} ms; "
          f"steady {total / len(steady):.1f} ms/movie")
    print(f"{'stage':28s} {'med ms':>8s} {'sum ms':>9s} {'share':>6s} {'cpu%':>5s} "
          f"{'minflt/mv':>10s} {'blk sw':>7s}")
    for name, row in sorted(t.items(), key=lambda kv: -sum(kv[1]["wall_ms"])):
        w = sum(row["wall_ms"])
        c = sum(row["cpu_ms"])
        print(f"{name:28s} {statistics.median(row['wall_ms']):8.2f} {w:9.1f} "
              f"{100 * w / total:5.1f}% {100 * c / w if w else 0:4.0f}% "
              f"{statistics.median(row['minflt']):10.0f} {statistics.median(row['vcsw']):7.0f}")
    subs: Dict[str, List[float]] = defaultdict(list)
    for m in steady:
        for st in m.get("sub", []):
            subs[st["name"]].append(st["wall_ms"])
    if subs:
        print("\nsub-stages (steady, summed over movies):")
        for name, v in sorted(subs.items(), key=lambda kv: -sum(kv[1]))[:20]:
            print(f"  {name:48s} {sum(v):9.1f} ms")
    if process:
        print(f"\nprocess: run wall {process['run_wall_ms']:.0f} ms, main-thread CPU "
              f"{process['main_cpu_ms']:.0f} ms, process CPU {process['process_cpu_ms']:.0f} ms, "
              f"peak RSS {process['peak_rss_kb'] / 1024:.0f} MiB, minor faults {process['process_minflt']}")
        for th in process.get("threads", []):
            print(f"  {th['name']:36s} n={th['n']:4d} wall {th['wall_ms']:9.1f} ms "
                  f"cpu {th['cpu_ms']:9.1f} ms minflt {th['minflt']}")
        in_movies = sum(m["wall_ms"] for m in movies)
        print(f"  outside movie loop: {process['run_wall_ms'] - in_movies:.0f} ms")
    if problems:
        print("\nWARNING: non-exhaustive stages:\n  " + "\n  ".join(problems))


def compare(base_path: str, cand_path: str):
    b, _ = load(base_path)
    c, _ = load(cand_path)
    tb, tc = per_stage(b, True), per_stage(c, True)
    nb, nc = max(len(b) - 1, 1), max(len(c) - 1, 1)
    print(f"{'stage':28s} {'base ms/mv':>11s} {'cand ms/mv':>11s} {'delta':>9s} "
          f"{'base flt':>9s} {'cand flt':>9s}")
    names = list(tb) + [k for k in tc if k not in tb]
    tot_b = tot_c = 0.0
    for name in names:
        wb = sum(tb.get(name, {}).get("wall_ms", [0])) / nb
        wc = sum(tc.get(name, {}).get("wall_ms", [0])) / nc
        fb = sum(tb.get(name, {}).get("minflt", [0])) / nb
        fc = sum(tc.get(name, {}).get("minflt", [0])) / nc
        tot_b += wb
        tot_c += wc
        print(f"{name:28s} {wb:11.2f} {wc:11.2f} {wc - wb:+9.2f} {fb:9.0f} {fc:9.0f}")
    print(f"{'TOTAL steady':28s} {tot_b:11.2f} {tot_c:11.2f} {tot_c - tot_b:+9.2f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="validate exhaustiveness only")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    if a.check:
        bad = 0
        for p in a.files:
            movies, process = load(p)
            problems = check(movies)
            if process is None:
                problems.append("missing process record")
            for pr in problems:
                print(f"{p}: {pr}")
            bad += len(problems)
        print("OK" if not bad else f"{bad} problem(s)")
        return 1 if bad else 0
    if len(a.files) == 1:
        summary(a.files[0])
    elif len(a.files) == 2:
        compare(*a.files)
    else:
        ap.error("give one file to summarise or two to compare")
    return 0


if __name__ == "__main__":
    sys.exit(main())
