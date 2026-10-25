#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic control for compare_json.py (no scientific data, no NumPy).

usage: compare_json_control.py COMPARE_JSON_PY NEW_EMPTY_OUTDIR
Runs the comparator on two hand-written JSON documents with known differences and on an
identical pair, and checks every reported count. Exit 0 only if all expectations hold.
"""
import json
import subprocess
import sys
from pathlib import Path

CMP, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir()
retained = {"skip": {"x": 1}, "v": 1.0, "w": [1, 2.5, 3], "n": {"skip": 2.0, "t": "a", "flag": True},
            "only_a": 1, "list": [1, 2]}
reproduced = {"skip": {"x": 999}, "v": 1.0000005, "w": [1, 2.5, 3.25], "n": {"skip": 2.5, "t": "b", "flag": False},
              "only_b": 0, "list": [1, 2, 3]}
(OUT / "retained.json").write_text(json.dumps(retained))
(OUT / "reproduced.json").write_text(json.dumps(reproduced))


def run(a, b, out, *ignore):
    q = subprocess.run([sys.executable, "-I", "-B", str(CMP), str(OUT / a), str(OUT / b), str(OUT / out), *ignore],
                       capture_output=True, text=True, timeout=60)
    rep = json.loads((OUT / out).read_text()) if q.returncode == 0 else None
    return dict(exit=q.returncode, stderr=q.stderr[-2000:], report=rep)


res = dict(diff=run("retained.json", "reproduced.json", "diff.json", "skip"),
           identical=run("retained.json", "retained.json", "identical.json", "skip"),
           no_ignore=run("retained.json", "reproduced.json", "no_ignore.json"))
checks = {}
d, i, n = (res[k]["report"] for k in ("diff", "identical", "no_ignore"))
checks["all_exit_0"] = all(res[k]["exit"] == 0 for k in res)
if d and i and n:
    s = d["structural_or_text_differences"]
    # numeric leaves: v, w[0..2], n/skip (nested key of the same name is NOT ignored), list[0..1]
    checks["numeric_leaves_7"] = d["numeric_leaves"] == 7
    checks["max_abs_diff_0.5"] = d["max_abs_diff"] == 0.5
    checks["leaves_over_1e-6_is_2"] = d["leaves_over_1e-6"] == 2          # 5e-7 (v) stays below
    checks["largest_paths"] = [x["path"] for x in d["largest"][:2]] == ["/n/skip", "/w[2]"]
    checks["structural_5"] = len(s) == 5
    checks["structural_items"] = all(any(t in x for x in s) for t in (
        "/n/t: 'a' vs 'b'", "/n/flag: True vs False", "/only_a: only in retained", "/only_b: only in reproduced",
        "/list: length 2 vs 3"))
    checks["top_level_ignore_applied"] = d["ignored_top_level_keys"] == ["skip"] and not any("/skip/" in x for x in s)
    checks["without_ignore_skip_counted"] = n["numeric_leaves"] == 8 and n["max_abs_diff"] == 998.0
    # identical pair: only_a is present on both sides, so 8 numeric leaves (attempt01 wrongly expected 7)
    checks["identical_pair_clean"] = (i["numeric_leaves"] == 8 and i["max_abs_diff"] == 0.0 and i["leaves_over_1e-6"] == 0
                                      and i["structural_or_text_differences"] == [])
ok = bool(checks) and all(checks.values()) and len(checks) == 10
(OUT / "CONTROL.json").write_text(json.dumps(dict(state="PASS" if ok else "FAIL", checks=checks, runs=res), indent=1) + "\n")
print("PASS" if ok else "FAIL", json.dumps(checks))
raise SystemExit(0 if ok else 1)
