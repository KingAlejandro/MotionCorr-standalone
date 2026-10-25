#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Report numeric-leaf differences between a retained JSON result and a reproduction.

usage: compare_json.py RETAINED.json REPRODUCED.json OUT.json [IGNORED_TOP_LEVEL_KEY ...]
Report only (exit 0 when both parse); the protocol states how the numbers are read.
r3 (2026-10-25): r2 (sha256 85ef82f7…5a82) passed `leaves_over_1e-6` as a dict() keyword, a
SyntaxError; the output dict is now a literal with the same key names. No other change.
"""
import json
import sys
from pathlib import Path

a, b = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
ignore = set(sys.argv[4:])
diffs, struct = [], []


def walk(x, y, path):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            if not path and k in ignore:
                continue
            if k not in x or k not in y:
                struct.append(f"{path}/{k}: only in {'reproduced' if k not in x else 'retained'}")
            else:
                walk(x[k], y[k], f"{path}/{k}")
    elif isinstance(x, list) and isinstance(y, list):
        if len(x) != len(y):
            struct.append(f"{path}: length {len(x)} vs {len(y)}")
        for i, (u, v) in enumerate(zip(x, y)):
            walk(u, v, f"{path}[{i}]")
    elif isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool) and not isinstance(y, bool):
        diffs.append((abs(float(x) - float(y)), path))
    elif x != y:
        struct.append(f"{path}: {x!r} vs {y!r}")


walk(a, b, "")
diffs.sort(reverse=True)
out = {"numeric_leaves": len(diffs), "max_abs_diff": diffs[0][0] if diffs else 0.0,
       "leaves_over_1e-6": sum(d > 1e-6 for d, _ in diffs), "largest": [dict(path=p, abs_diff=d) for d, p in diffs[:20]],
       "structural_or_text_differences": struct, "ignored_top_level_keys": sorted(ignore)}
Path(sys.argv[3]).write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps({k: out[k] for k in ("numeric_leaves", "max_abs_diff", "leaves_over_1e-6")}), len(struct), "structural")
