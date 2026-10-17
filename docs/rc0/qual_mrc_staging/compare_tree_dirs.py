#!/usr/bin/env python3
"""Strict tree identity between two runs of the same case (identity.py), optionally deleting bulk MRC afterwards.

    compare_tree_dirs.py A_ROOT B_ROOT [--delete-mrc]      one pair of output trees
    compare_tree_dirs.py --pairs A_WORK B_WORK SUFFIX ...   every <case>/<arm> dir present in both work dirs
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "profiling"))
from lib import identity  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--glob", default="*-cpu/out", help="with --dirs: arm output dirs relative to A and B")
    ap.add_argument("--dirs", action="store_true", help="A and B are work dirs; compare every matching arm dir")
    ap.add_argument("--delete-mrc", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    pairs = [(a.a, a.b)]
    if a.dirs:
        pairs = [(str(p), str(Path(a.b) / p.relative_to(a.a))) for p in sorted(Path(a.a).glob(a.glob))
                 if (Path(a.b) / p.relative_to(a.a)).is_dir()]
    res = []
    for pa, pb in pairs:
        r = identity.compare_trees(pa, pb)
        res.append({"a": pa, "b": pb, "identical": r["identical"], "problems": r["problems"],
                    "compared": r["compared"], "mrc_compared": r["mrc_compared"],
                    "differences": r["differences"][:3]})
        print(("IDENTICAL " if r["identical"] else "DIFFERENT ") + "%s (files %d, mrc %d) %s" % (
            Path(pa).parent.name, r["compared"], r["mrc_compared"], r["problems"]), flush=True)
        if a.delete_mrc:
            for root in (pa, pb):
                for p in Path(root).rglob("*.mrc"):
                    p.unlink()
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))
    n_bad = sum(not r["identical"] for r in res)
    print("%d pairs, %d not identical" % (len(res), n_bad))
    return 1 if n_bad or not res else 0


if __name__ == "__main__":
    sys.exit(main())
