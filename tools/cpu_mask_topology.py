#!/usr/bin/env python3
"""Derive CPU-mask topology from a retained `lscpu -p` witness.

Why this exists: the sbatch manifest computed "distinct physical cores" and
"NUMA nodes spanned" with an awk one-liner that split the mask on commas only.
Given an explicit list like `0,1,2,3,32,33` that works; given a Linux range
list like `0-7,32-39` -- which is exactly what `Cpus_allowed_list` and
`taskset -c` use -- it matches nothing and silently reports zero. The #94
cpu16 manifest therefore recorded `distinct_physical_cores: 0` and an empty
`numa_nodes_spanned` for a mask that really covered 16 CPUs.

A reported zero should have been impossible for a run that was executing, so
the failure was visible; a subtler mask could have produced a plausible wrong
number instead. Hence the range-mask control in --self-test.

This derives the answer from the retained `lscpu -p=CPU,NODE,SOCKET,CORE`
witness and the retained mask string. It makes no locality claim: a mask that
sits on one NUMA node says where the threads may run, not where their memory
is, and memory policy has to be read separately.
"""
import argparse
import sys
from pathlib import Path


def expand_mask(spec: str):
    """Expand a Linux CPU list ('0-7,32-39' or '0,1,2') into a sorted list."""
    cpus = set()
    for part in spec.strip().split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            lo, hi = int(lo), int(hi)
            if hi < lo:
                raise ValueError(f"descending range {part!r}")
            cpus.update(range(lo, hi + 1))
        else:
            cpus.add(int(part))
    return sorted(cpus)


def load_lscpu(path: Path):
    """{cpu: (node, socket, core)} from an `lscpu -p=CPU,NODE,SOCKET,CORE` dump."""
    table = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        f = line.split(",")
        if len(f) < 4:
            continue
        try:
            table[int(f[0])] = (int(f[1]), int(f[2]), int(f[3]))
        except ValueError:
            continue
    return table


def describe(spec: str, table: dict):
    cpus = expand_mask(spec)
    known = [c for c in cpus if c in table]
    missing = [c for c in cpus if c not in table]
    cores = sorted({(table[c][1], table[c][2]) for c in known})
    nodes = sorted({table[c][0] for c in known})
    siblings = {}
    for c in known:
        siblings.setdefault((table[c][1], table[c][2]), []).append(c)
    full_pairs = sum(1 for v in siblings.values() if len(v) > 1)
    return {
        "mask": spec,
        "logical_cpus": len(cpus),
        "logical_cpus_in_witness": len(known),
        "cpus_missing_from_witness": missing,
        "distinct_physical_cores": len(cores),
        "numa_nodes_spanned": nodes,
        "cores_with_both_smt_siblings_in_mask": full_pairs,
    }


def self_test() -> int:
    """Control: the parser must handle range lists, and the OLD comma-only
    logic must demonstrably fail on them. Without the second half this test
    would pass just as happily against the bug it exists to catch."""
    # Synthetic NPS-style witness: 64 CPUs, 8 nodes, SMT sibling = cpu + 32.
    table = {}
    for c in range(64):
        core = c % 32
        table[c] = (core // 4, 0, core)

    def comma_only(spec):                      # the old, broken helper
        want = set()
        for p in spec.split(","):
            try:
                want.add(int(p))
            except ValueError:
                pass
        return len({table[c][2] for c in want if c in table})

    ok = True
    checks = []

    def check(name, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        checks.append((name, got, want, "OK" if good else "WRONG"))

    check("expand '0-7,32-39'", expand_mask("0-7,32-39"),
          [0, 1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37, 38, 39])
    check("expand '0,1,2,3,32,33,34,35'", expand_mask("0,1,2,3,32,33,34,35"),
          [0, 1, 2, 3, 32, 33, 34, 35])
    check("expand '0'", expand_mask("0"), [0])
    check("expand '0-63' length", len(expand_mask("0-63")), 64)

    d = describe("0-7,32-39", table)
    check("range mask: logical cpus", d["logical_cpus"], 16)
    check("range mask: physical cores", d["distinct_physical_cores"], 8)
    check("range mask: numa nodes", d["numa_nodes_spanned"], [0, 1])
    check("range mask: full SMT pairs", d["cores_with_both_smt_siblings_in_mask"], 8)

    d8 = describe("0,1,2,3,32,33,34,35", table)
    check("list mask: physical cores", d8["distinct_physical_cores"], 4)
    check("list mask: numa nodes", d8["numa_nodes_spanned"], [0])

    d1 = describe("0", table)
    check("single cpu: physical cores", d1["distinct_physical_cores"], 1)

    # The discriminating half: the old helper must get the range mask wrong
    # and the explicit list right, which is exactly the observed failure.
    check("OLD comma-only helper on a RANGE mask (must be 0)", comma_only("0-7,32-39"), 0)
    check("OLD comma-only helper on an EXPLICIT list (was fine)",
          comma_only("0,1,2,3,32,33,34,35"), 4)

    print("cpu mask topology self-test")
    print(f"  {'check':<52}{'got':<28}{'want':<28}verdict")
    for name, got, want, verdict in checks:
        print(f"  {name:<52}{str(got):<28}{str(want):<28}{verdict}")
    print("  self-test:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lscpu", type=Path, help="retained `lscpu -p=CPU,NODE,SOCKET,CORE` dump")
    ap.add_argument("--mask", action="append", default=[],
                    help="CPU mask as recorded, e.g. '0-7,32-39'. Repeatable.")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.lscpu or not args.mask:
        ap.error("--lscpu and at least one --mask are required")
    table = load_lscpu(args.lscpu)
    print(f"witness: {args.lscpu}  ({len(table)} CPUs)")
    for spec in args.mask:
        d = describe(spec, table)
        print(f"\nmask {spec!r}")
        for k in ("logical_cpus", "distinct_physical_cores", "numa_nodes_spanned",
                  "cores_with_both_smt_siblings_in_mask", "cpus_missing_from_witness"):
            print(f"  {k:<38}{d[k]}")
        print("  NOTE: a mask says where threads MAY run. It is not a memory-locality")
        print("        claim; read the recorded numactl policy for that.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
