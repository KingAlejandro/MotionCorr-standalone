#!/usr/bin/env python3
"""Provenance helpers for W-MRC-Q (audit R-QA1 follow-up).

  hash    --work DIR --out FILE     sha256 of every input file under DIR/<section>/<arm>/data/ (what motioncorr read)
  regen   --work DIR --out FILE     regenerate each matrix/options fixture with synth_mrc_matrix.py in a fresh
                                    directory and compare its sha256 with the one on disk
  outputs --root DIR [--root ...] --out FILE
                                    sha256 of every *.mrc product still on disk under DIR/**/out/ (products
                                    deleted after comparison cannot be listed)
  wscheck --work DIR --out FILE     re-run the compressed-vs-plain comparisons on the retained products with and
                                    without whitespace collapsing in the text files
Run with the same python/numpy as the original runs (/home/alex/mc-env, numpy 2.5.3).
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import synth_mrc_matrix as sm  # noqa: E402


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_hash(a):
    work = Path(a.work)
    rows = []
    for p in sorted(work.glob("*/*/data/*")):
        rows.append("%s  %d  %s" % (sha(p), p.stat().st_size, p.relative_to(work)))
    Path(a.out).write_text("\n".join(rows) + "\n")
    print("%d input files hashed, %d distinct digests" % (len(rows), len({r.split()[0] for r in rows})))


def _arm_key(name):
    for suffix in ("-float", "-auto", "-compact", "-pinned", "-cpu"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def cmd_regen(a):
    work = Path(a.work)
    res, tmp = [], Path(tempfile.mkdtemp(prefix="mrcq-regen-", dir=os.environ.get("TMPDIR")))
    seen = set()
    todo = []
    for case in sm.cases():
        todo.append(("matrix", case["name"], case))
    for mode in (0, 1):
        for name in sm.OPTION_SETS:
            side = 768 if name == "ps_group4" else 192
            todo.append(("options", "o-m%d-%s" % (mode, name), dict(mode=mode, nx=side, ny=side, nz=12)))
    for section, label, case in todo:
        writer, _ = sm.make_writer(case)
        out = tmp / (label + ".mrcs")
        writer(out)
        regen = sha(out)
        out.unlink()
        arms = sorted(p for p in (work / section).glob("*/data/movie.mrcs") if _arm_key(p.parent.parent.name) == label)
        disk = {sha(p) for p in arms}
        res.append({"section": section, "case": label, "regenerated": regen, "on_disk": sorted(disk),
                    "arms": len(arms), "match": disk == {regen}})
        if case.get("gain"):
            g = tmp / "gain.mrc"
            sm.write_gain(g, case["nx"], case["ny"])
            gd = {sha(p) for p in (work / section).glob("*/data/gain.mrc")
                  if _arm_key(p.parent.parent.name) == label}
            res[-1]["gain_regenerated"] = sha(g)
            res[-1]["gain_on_disk"] = sorted(gd)
            res[-1]["gain_match"] = gd == {sha(g)}
            g.unlink()
        seen.add(label)
    for mode in (1, 0, 6, 2):  # raw sources compressed in section 3
        writer, _ = sm.make_writer(dict(mode=mode, nx=128, ny=128, nz=8))
        out = tmp / "s.mrc"
        writer(out)
        disk = work / "compressed" / ("src_m%d.mrc" % mode)
        res.append({"section": "compressed", "case": "src_m%d.mrc" % mode, "regenerated": sha(out),
                    "on_disk": [sha(disk)], "arms": 1, "match": sha(out) == sha(disk)})
        out.unlink()
    Path(a.out).write_text(json.dumps(res, indent=1))
    ok = sum(r["match"] and r.get("gain_match", True) for r in res)
    print("%d fixtures regenerated, %d match the on-disk bytes" % (len(res), ok))
    for r in res:
        if not (r["match"] and r.get("gain_match", True)):
            print("MISMATCH", r["section"], r["case"], r["arms"])


def cmd_outputs(a):
    rows = []
    for root in a.root:
        for p in sorted(Path(root).rglob("*.mrc")):
            if "/out/" in str(p):
                rows.append("%s  %d  %s" % (sha(p), p.stat().st_size, os.path.relpath(p, Path(root).parent)))
    Path(a.out).write_text("\n".join(rows) + "\n")
    print("%d retained MRC products hashed" % len(rows))


def cmd_wscheck(a):
    work = Path(a.work) / "compressed"
    res = []
    arms = [(m, "c-m%d-%s-native-%s" % (m, c, i)) for m in (1, 0, 6, 2) for c in ("xz", "zst") for i in ("auto", "float")]
    arms += [(1, "c-m1-bz2-pbzip2-shim-%s" % i) for i in ("auto", "float")]
    for mode, armname in arms:
        ref = {"out": str(work / ("ref-m%d" % mode) / "out")}
        ref["mrc_products"] = [os.path.relpath(p, ref["out"]) for p in Path(ref["out"]).rglob("*.mrc")]
        arm = work / armname
        cur = {"out": str(arm / "out")}
        cur["mrc_products"] = [os.path.relpath(p, cur["out"]) for p in Path(cur["out"]).rglob("*.mrc")]
        strict = sm.compare_named(ref, cur, collapse_ws=False)
        loose = sm.compare_named(ref, cur, collapse_ws=True)
        res.append({"arm": arm.name, "identical_with_ws_collapse": loose["identical"],
                    "identical_without_ws_collapse": strict["identical"],
                    "files_differing_without_collapse": sorted({d["file"] for d in strict["differences"]}),
                    "problems_without_collapse": strict["problems"]})
    # Controls, on bytes in memory (the retained trees are not touched): what the whitespace collapse can and
    # cannot hide in the per-movie STAR of the c-m1-xz-native-auto arm against the plain reference.
    import re
    ref_root, arm_root = str(work / "ref-m1" / "out"), str(work / "c-m1-xz-native-auto" / "out")
    ref_star = (Path(ref_root) / "movie.star").read_bytes()
    arm_star = (Path(arm_root) / "movie_mrc.star").read_bytes()
    controls = {}
    for name, edit in (("unmodified", lambda t: t),
                       ("whitespace-only change (one extra space)", lambda t: t.replace(b"  ", b"   ", 1)),
                       ("one digit changed in a shift value", lambda t: re.sub(rb"(\d)(\s*\n)", lambda m: b"7" + m.group(2), t, 1))):
        edited = edit(arm_star)
        controls[name] = {"bytes_changed": edited != arm_star,
                          "identical_with_ws_collapse": sm._norm(ref_star, ref_root, True) == sm._norm(edited, arm_root, True),
                          "identical_without_ws_collapse": sm._norm(ref_star, ref_root, False) == sm._norm(edited, arm_root, False)}
    Path(a.out).write_text(json.dumps({"pairs": res, "controls": controls}, indent=1))
    print(json.dumps(controls))
    print("%d pairs; identical with collapse %d; without collapse %d" % (
        len(res), sum(r["identical_with_ws_collapse"] for r in res), sum(r["identical_without_ws_collapse"] for r in res)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("hash", "regen", "wscheck"):
        p = sub.add_parser(name)
        p.add_argument("--work", required=True)
        p.add_argument("--out", required=True)
    p = sub.add_parser("outputs")
    p.add_argument("--root", action="append", required=True)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    {"hash": cmd_hash, "regen": cmd_regen, "outputs": cmd_outputs, "wscheck": cmd_wscheck}[a.cmd](a)


if __name__ == "__main__":
    main()
