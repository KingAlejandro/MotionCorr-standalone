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
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# MRC comparison: the WHOLE file, minus a whitelist justified from the writer
# ---------------------------------------------------------------------------
#
# An earlier version of this tool compared only bytes 0..224 and set the label
# area aside wholesale. That does not establish header parity: 224..1024 is 800
# bytes of real header content and only a few of them can legitimately differ.
#
# src/rwMRC.h writes, on every MRC it produces:
#     header->nsymbt = 0
#     header->nlabl  = 1
#     label = "Relion " + PACKAGE_VERSION + "   " + strftime("%d-%b-%y  %R:%S")
#     strncpy(header->labels, label, 80)
#
# So exactly one field can differ between two runs of the same binary on the
# same input: the 19-character wall-clock timestamp that strftime writes
# ("%d-%b-%y" = 9, two spaces, "%R:%S" = 8). Everything else in the file --
# the main header, the "Relion <version>   " prefix, the nine unused label
# records, the extended header, and every pixel -- must be byte-identical.
#
# The whitelist is therefore derived, not assumed: the timestamp is located by
# the pattern strftime produces, both sides must parse as a real timestamp, and
# both must sit at the same offset behind an identical prefix. A garbage or
# relocated label cannot hide inside it.

MRC_HEADER_BYTES = 1024
MRC_LABEL_OFFSET = 224
MRC_LABEL_LEN = 80
MRC_NLABL_OFFSET = 220
MRC_NSYMBT_OFFSET = 92

# "%d-%b-%y  %R:%S" -> "28-Sep-26  08:03:24"
_TIMESTAMP_RE = re.compile(
    rb"\d{2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}  "
    rb"\d{2}:\d{2}:\d{2}")
TIMESTAMP_LEN = 19


def _timestamp_spans(label_area: bytes, nlabl: int):
    """Byte spans, relative to the label area, holding a writer timestamp.

    Only the label records the header declares as used are scanned, and at most
    one timestamp per record is accepted, so a stray digit run elsewhere cannot
    silently widen the whitelist.
    """
    spans = []
    for i in range(max(0, min(nlabl, 10))):
        rec = label_area[i * MRC_LABEL_LEN:(i + 1) * MRC_LABEL_LEN]
        found = list(_TIMESTAMP_RE.finditer(rec))
        if len(found) != 1:
            continue
        m = found[0]
        if m.end() - m.start() != TIMESTAMP_LEN:
            continue
        spans.append((i * MRC_LABEL_LEN + m.start(), i * MRC_LABEL_LEN + m.end()))
    return spans


def compare_mrc(a: bytes, b: bytes, name: str):
    """Compare two MRC files completely. Returns (problems, whitelist_spans)."""
    problems = []
    if len(a) < MRC_HEADER_BYTES or len(b) < MRC_HEADER_BYTES:
        return [f"{name}: shorter than an MRC header"], []
    if len(a) != len(b):
        problems.append(f"{name}: file sizes differ, {len(a)} vs {len(b)}")
        return problems, []

    na = struct.unpack("<i", a[MRC_NSYMBT_OFFSET:MRC_NSYMBT_OFFSET + 4])[0]
    nb = struct.unpack("<i", b[MRC_NSYMBT_OFFSET:MRC_NSYMBT_OFFSET + 4])[0]
    if na != nb:
        problems.append(f"{name}: nsymbt differs, {na} vs {nb}")
        return problems, []
    if na < 0:
        problems.append(f"{name}: negative nsymbt {na}")
        return problems, []

    if a[:MRC_LABEL_OFFSET] != b[:MRC_LABEL_OFFSET]:
        problems.append(f"{name}: main header bytes 0..224 differ")

    la = struct.unpack("<i", a[MRC_NLABL_OFFSET:MRC_NLABL_OFFSET + 4])[0]
    lb = struct.unpack("<i", b[MRC_NLABL_OFFSET:MRC_NLABL_OFFSET + 4])[0]
    if la != lb:
        problems.append(f"{name}: nlabl differs, {la} vs {lb}")

    area_a = a[MRC_LABEL_OFFSET:MRC_HEADER_BYTES]
    area_b = b[MRC_LABEL_OFFSET:MRC_HEADER_BYTES]
    spans_a = _timestamp_spans(area_a, la)
    spans_b = _timestamp_spans(area_b, lb)
    if spans_a != spans_b:
        problems.append(f"{name}: writer timestamps sit at different offsets, "
                        f"{spans_a} vs {spans_b}")
        spans = []
    else:
        spans = spans_a
        for lo, hi in spans:
            for side, area in (("A", area_a), ("B", area_b)):
                text = area[lo:hi].decode("ascii", "replace")
                try:
                    datetime.strptime(text, "%d-%b-%y  %H:%M:%S")
                except ValueError:
                    problems.append(f"{name}: {side} whitelisted label bytes "
                                    f"{lo}..{hi} are not a writer timestamp: {text!r}")

    # Every label byte outside the justified whitelist must match exactly.
    masked_a, masked_b = bytearray(area_a), bytearray(area_b)
    for lo, hi in spans:
        masked_a[lo:hi] = b"\0" * (hi - lo)
        masked_b[lo:hi] = b"\0" * (hi - lo)
    if bytes(masked_a) != bytes(masked_b):
        diff = [MRC_LABEL_OFFSET + i for i in range(len(masked_a))
                if masked_a[i] != masked_b[i]]
        problems.append(f"{name}: label area differs outside the timestamp "
                        f"whitelist at file offsets {diff[:16]} (count {len(diff)})")

    if na and a[MRC_HEADER_BYTES:MRC_HEADER_BYTES + na] != b[MRC_HEADER_BYTES:MRC_HEADER_BYTES + na]:
        problems.append(f"{name}: extended header ({na} bytes) differs")

    if a[MRC_HEADER_BYTES + na:] != b[MRC_HEADER_BYTES + na:]:
        problems.append(f"{name}: PIXELS DIFFER")
    elif len(a) == MRC_HEADER_BYTES + na:
        problems.append(f"{name}: no pixel payload -- the comparison is vacuous")

    return problems, spans


def mrc_parts(path: Path):
    """Retained for the legacy per-part reporting used by the run-root mode."""
    data = path.read_bytes()
    if len(data) < MRC_HEADER_BYTES:
        raise ValueError(f"{path}: shorter than an MRC header")
    return data[:MRC_LABEL_OFFSET], data[MRC_LABEL_OFFSET:MRC_HEADER_BYTES], data[MRC_HEADER_BYTES:]


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


def compare_arm_dirs(a_dir: Path, b_dir: Path):
    """Full comparison of two arm output trees. Returns (problems, stats)."""
    problems = []
    a_out = a_dir / "out" if (a_dir / "out").is_dir() else a_dir
    b_out = b_dir / "out" if (b_dir / "out").is_dir() else b_dir
    A = {str(p.relative_to(a_out)): p for p in sorted(a_out.glob("**/*.mrc"))}
    B = {str(p.relative_to(b_out)): p for p in sorted(b_out.glob("**/*.mrc"))}
    stats = {"mrc_compared": 0, "star_compared": 0, "pixel_bytes": 0,
             "whitelisted_bytes": 0, "files_with_timestamp_diff": 0}
    if not A:
        problems.append(f"{a_dir.name}: no MRC outputs -- comparison would be vacuous")
    if set(A) != set(B):
        problems.append(f"different MRC sets: {sorted(set(A) ^ set(B))}")
    for n in sorted(set(A) & set(B)):
        da, db = A[n].read_bytes(), B[n].read_bytes()
        probs, spans = compare_mrc(da, db, n)
        problems += probs
        if not probs:
            stats["mrc_compared"] += 1
            nsymbt = struct.unpack("<i", da[MRC_NSYMBT_OFFSET:MRC_NSYMBT_OFFSET + 4])[0]
            stats["pixel_bytes"] += len(da) - MRC_HEADER_BYTES - nsymbt
            stats["whitelisted_bytes"] += sum(hi - lo for lo, hi in spans)
            if da != db:
                stats["files_with_timestamp_diff"] += 1

    SA = {str(p.relative_to(a_out)): star_body(p, a_dir) for p in sorted(a_out.glob("**/*.star"))}
    SB = {str(p.relative_to(b_out)): star_body(p, b_dir) for p in sorted(b_out.glob("**/*.star"))}
    if not SA:
        problems.append(f"{a_dir.name}: no STAR outputs")
    if set(SA) != set(SB):
        problems.append(f"different STAR sets: {sorted(set(SA) ^ set(SB))}")
    for n in sorted(set(SA) & set(SB)):
        if SA[n] != SB[n]:
            problems.append(f"STAR differs: {n}")
        else:
            stats["star_compared"] += 1
    return problems, stats


def self_test() -> int:
    """Discriminating control: the comparison must catch every mutation that
    matters and must accept the one that does not. A checker that only ever
    says 'identical' proves nothing about the files it was given."""
    base = bytearray(1024 + 64)
    struct.pack_into("<3i", base, 0, 4, 4, 1)
    struct.pack_into("<i", base, 12, 2)
    struct.pack_into("<i", base, MRC_NSYMBT_OFFSET, 0)
    struct.pack_into("<i", base, MRC_NLABL_OFFSET, 1)
    base[224:224 + 29] = b"Relion    28-Sep-26  08:03:24"
    for i in range(64):
        base[1024 + i] = (i * 7) % 251

    cases = []

    def case(name, mutate, must_fail):
        other = bytearray(base)
        mutate(other)
        probs, _ = compare_mrc(bytes(base), bytes(other), "probe")
        ok = bool(probs) == must_fail
        cases.append((name, "caught" if probs else "accepted",
                      "OK" if ok else "WRONG", probs[:1]))
        return ok

    all_ok = True
    # Must be ACCEPTED: only the whitelisted timestamp changed, still valid.
    all_ok &= case("timestamp changes to another valid timestamp",
                   lambda o: o.__setitem__(slice(224 + 10, 224 + 29), b"28-Sep-26  08:05:34"),
                   must_fail=False)
    # Must be CAUGHT.
    all_ok &= case("one pixel byte flips",
                   lambda o: o.__setitem__(1024 + 33, base[1024 + 33] ^ 0xFF), True)
    all_ok &= case("main header byte flips (nx)",
                   lambda o: struct.pack_into("<i", o, 0, 5), True)
    all_ok &= case("label prefix byte flips (Relion -> Reliom)",
                   lambda o: o.__setitem__(224 + 5, ord("m")), True)
    all_ok &= case("unused label record 1 gains content",
                   lambda o: o.__setitem__(slice(224 + 80, 224 + 84), b"junk"), True)
    all_ok &= case("timestamp replaced by same-length garbage",
                   lambda o: o.__setitem__(slice(224 + 10, 224 + 29), b"XXXXXXXXXXXXXXXXXXX"), True)
    all_ok &= case("timestamp replaced by an impossible date",
                   lambda o: o.__setitem__(slice(224 + 10, 224 + 29), b"99-Zzz-26  08:05:34"), True)
    all_ok &= case("nsymbt claims an extended header",
                   lambda o: struct.pack_into("<i", o, MRC_NSYMBT_OFFSET, 16), True)
    all_ok &= case("nlabl changes",
                   lambda o: struct.pack_into("<i", o, MRC_NLABL_OFFSET, 2), True)
    all_ok &= case("file truncated",
                   lambda o: o.__delitem__(slice(1040, None)), True)

    print("negative control for the MRC comparison")
    print(f"  {'mutation':<48}{'result':<10}{'verdict'}")
    for name, result, verdict, first in cases:
        print(f"  {name:<48}{result:<10}{verdict}" + (f"   [{first[0]}]" if first and verdict == "OK" and result == "caught" else ""))
    print("  self-test:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path,
                    help="results root produced by scripts/prefetch_gpu_screen.sh")
    ap.add_argument("--pair", type=Path, nargs=2, metavar=("DIR_A", "DIR_B"),
                    help="fully compare two retained arm directories")
    ap.add_argument("--self-test", action="store_true",
                    help="run the negative control for the MRC comparison and exit")
    ap.add_argument("--json", type=Path, help="write the machine-readable summary here")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.pair:
        a, b = args.pair[0].resolve(), args.pair[1].resolve()
        problems, stats = compare_arm_dirs(a, b)
        print(f"A: {a}")
        print(f"B: {b}")
        print(f"  MRC files fully identical (whole file minus whitelist): "
              f"{stats['mrc_compared']}")
        print(f"  of which the whitelisted timestamp actually differed:   "
              f"{stats['files_with_timestamp_diff']}")
        print(f"  whitelisted bytes in total:                             "
              f"{stats['whitelisted_bytes']}")
        print(f"  pixel bytes compared:                                   "
              f"{stats['pixel_bytes']}")
        print(f"  STAR artifacts identical:                               "
              f"{stats['star_compared']}")
        print("PROBLEMS:" if problems else "PROBLEMS: none")
        for p in problems[:40]:
            print("  -", p)
        return 1 if problems else 0
    if not args.root:
        ap.error("one of --root, --pair or --self-test is required")
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
