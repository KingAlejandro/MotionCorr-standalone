#!/usr/bin/env python3
"""Compare the serial and prefetch arms of a paired #94 screening run.

Two separate questions, deliberately answered separately:

1. Are the arms EXACTLY the same product? Every corrected MRC payload, every
   normalized MRC header field and every STAR artifact is compared literally.
   A timing result from arms that do not agree here is meaningless, so this is
   reported first and a failure is not softened into a tolerance.

2. Is either arm faster? Reported as a PAIRED difference with the arm order
   kept, because the positional bias -- the advantage to whichever arm runs
   second, largely input page-cache warming -- is a property of the workload
   and has measured ~20 ms for a TIFF-read/MRC-write change on this host. The
   same pairs also yield that bias for free via observed = E +/- P.

No verdict is emitted. n=3 paired blocks is a screen: a two-sided sign test at
n=3 has eight possible outcomes and cannot reach any conventional level, so
this tool prints the effect, the spread and the bias and stops. Promoting the
change needs #26's confirmation protocol, and a null result is a valid answer.
"""
import argparse
import json
import re
import statistics
import struct
import sys
from pathlib import Path

# Bytes 208..224 of an MRC header hold MAP/machine stamp; 224.. is the label
# area, which carries a wall-clock timestamp and therefore cannot be compared.
MRC_LABEL_OFFSET = 224
MRC_HEADER_BYTES = 1024


def mrc_parts(path: Path):
    """(normalized header, pixel payload). The label area is excluded and
    reported separately so 'headers match' is not silently weakened."""
    data = path.read_bytes()
    if len(data) < MRC_HEADER_BYTES:
        raise ValueError(f"{path}: shorter than an MRC header")
    header = data[:MRC_LABEL_OFFSET]
    labels = data[MRC_LABEL_OFFSET:MRC_HEADER_BYTES]
    return header, labels, data[MRC_HEADER_BYTES:]


def star_body(path: Path, root: Path) -> str:
    """STAR text with comments dropped and the run directory normalized. Every
    numeric field is compared literally."""
    text = "\n".join(l.rstrip() for l in path.read_text(errors="replace").splitlines()
                     if not l.strip().startswith("#"))
    return text.replace(str(root) + "/", "OUT/").replace(root.name + "/", "OUT/")


def collect(run_dir: Path):
    out = run_dir / "out"
    mrcs, stars = {}, {}
    for p in sorted(out.glob("**/*.mrc")):
        mrcs[str(p.relative_to(out))] = mrc_parts(p)
    for p in sorted(out.glob("**/*.star")):
        stars[str(p.relative_to(out))] = star_body(p, run_dir)
    return mrcs, stars


def parse_run(run_dir: Path) -> dict:
    info = {}
    text = (run_dir / "run.txt").read_text()
    for line in text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            info.setdefault(k.strip(), v.strip())
    info["prefetch_lines"] = [l.strip() for l in text.splitlines()
                              if l.strip().startswith("prefetch:")]
    return info


def compare_products(a_dir: Path, b_dir: Path, problems: list) -> dict:
    a_mrc, a_star = collect(a_dir)
    b_mrc, b_star = collect(b_dir)
    tag = f"{a_dir.name} vs {b_dir.name}"

    if not a_mrc:
        problems.append(f"{tag}: no corrected MRCs at all -- the comparison is vacuous")
        return {"mrc": 0, "star": 0}
    if set(a_mrc) != set(b_mrc):
        problems.append(f"{tag}: different MRC sets\n  {sorted(set(a_mrc) ^ set(b_mrc))}")
    if set(a_star) != set(b_star):
        problems.append(f"{tag}: different STAR sets\n  {sorted(set(a_star) ^ set(b_star))}")

    for name in sorted(set(a_mrc) & set(b_mrc)):
        ah, al, ap = a_mrc[name]
        bh, bl, bp = b_mrc[name]
        if len(ap) == 0:
            problems.append(f"{tag}: {name} has no pixels")
        if ap != bp:
            problems.append(f"{tag}: PIXELS DIFFER for {name}")
        if ah != bh:
            problems.append(f"{tag}: normalized header differs for {name}")
        if al != bl:
            # Expected: the label area carries a wall-clock timestamp.
            pass
    for name in sorted(set(a_star) & set(b_star)):
        if a_star[name] != b_star[name]:
            diff = [f"      serial:   {x}\n      prefetch: {y}"
                    for x, y in zip(a_star[name].splitlines(), b_star[name].splitlines())
                    if x != y]
            problems.append(f"{tag}: STAR differs for {name}\n" + "\n".join(diff[:6]))
    return {"mrc": len(a_mrc), "star": len(a_star)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True,
                    help="results root produced by scripts/prefetch_gpu_screen.sh")
    ap.add_argument("--json", type=Path, help="write the machine-readable summary here")
    args = ap.parse_args()
    root = args.root.resolve()

    runs = {}
    for d in sorted(root.glob("pair*_*_*")):
        m = re.match(r"pair(\d+)_(first|second)_(serial|prefetch)$", d.name)
        if not m:
            continue
        runs[(int(m.group(1)), m.group(3))] = (d, m.group(2))
    pairs = sorted({p for p, _ in runs})
    if not pairs:
        sys.exit(f"no runs found under {root}")

    problems, notes = [], []
    counts = {}
    for p in pairs:
        if (p, "serial") not in runs or (p, "prefetch") not in runs:
            problems.append(f"pair {p} is incomplete")
            continue
        s_dir, s_pos = runs[(p, "serial")]
        f_dir, f_pos = runs[(p, "prefetch")]
        for d in (s_dir, f_dir):
            rc = parse_run(d).get("exit_code")
            if rc != "0":
                problems.append(f"{d.name}: exit code {rc}")
        counts[p] = compare_products(s_dir, f_dir, problems)

    # Cross-pair: every serial run must also equal every other serial run, or
    # the workload itself is nondeterministic and no arm comparison is valid.
    serial_dirs = [runs[(p, "serial")][0] for p in pairs if (p, "serial") in runs]
    for d in serial_dirs[1:]:
        compare_products(serial_dirs[0], d, problems)

    print("=== 1. exact same-backend product comparison ===")
    if problems:
        print(f"  {len(problems)} problem(s):")
        for pr in problems:
            print("   -", pr)
        print("\n  Timing below is NOT interpretable while the arms disagree.")
    else:
        total_mrc = sum(c["mrc"] for c in counts.values())
        total_star = sum(c["star"] for c in counts.values())
        print(f"  identical across {len(pairs)} pairs: {total_mrc} MRC payloads and "
              f"normalized headers, {total_star} STAR artifacts, and every serial run "
              f"matches every other serial run")
        print("  (MRC label area excluded: it carries a wall-clock timestamp)")

    print("\n=== 2. paired timing, arm order retained ===")
    deltas, positional = [], []
    rows = []
    for p in pairs:
        if (p, "serial") not in runs or (p, "prefetch") not in runs:
            continue
        s_dir, s_pos = runs[(p, "serial")]
        f_dir, f_pos = runs[(p, "prefetch")]
        s = float(parse_run(s_dir)["wall_seconds"])
        f = float(parse_run(f_dir)["wall_seconds"])
        deltas.append(s - f)                      # positive = prefetch faster
        # observed = E +/- P: the sign of the positional term flips with order.
        positional.append((s - f) if s_pos == "second" else (f - s))
        rows.append((p, s_pos, s, f, s - f))
    for p, s_pos, s, f, d in rows:
        print(f"  pair {p}: serial ran {s_pos:<6} serial={s:.3f}s prefetch={f:.3f}s "
              f"delta={d:+.3f}s")
    if deltas:
        print(f"  mean delta (positive = prefetch faster): {statistics.fmean(deltas):+.3f} s")
        if len(deltas) > 1:
            print(f"  sd of delta: {statistics.stdev(deltas):.3f} s")
        wins = sum(1 for d in deltas if d > 0)
        print(f"  prefetch faster in {wins}/{len(deltas)} pairs")
        print(f"  positional bias estimate (advantage to the arm running second): "
              f"{statistics.fmean(positional):+.3f} s")
        print(f"\n  n={len(deltas)} paired blocks is a SCREEN. A two-sided sign test at "
              f"n={len(deltas)} cannot reach a conventional level, so no verdict is "
              f"emitted here.")

    print("\n=== 3. prefetch accounting (prefetch arm) ===")
    for p in pairs:
        if (p, "prefetch") not in runs:
            continue
        info = parse_run(runs[(p, "prefetch")][0])
        print(f"  pair {p}: max_rss_kb={info.get('max_rss_kb')} "
              f"peak_vram_mib={info.get('peak_vram_mib')} "
              f"foreign_load(mean max n)={info.get('foreign_load_mean_max_n')}")
        for line in info["prefetch_lines"]:
            print("     ", line)

    if args.json:
        args.json.write_text(json.dumps({
            "root": str(root),
            "pairs": [{"pair": p, "serial_position": sp, "serial_s": s,
                       "prefetch_s": f, "delta_s": d} for p, sp, s, f, d in rows],
            "problems": problems,
        }, indent=2) + "\n")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
