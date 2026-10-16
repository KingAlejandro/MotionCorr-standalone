#!/usr/bin/env python3
"""Per-run retry accounting from the per-movie logs: patches, retried (two completion
lines in the patch block), and retries that converged."""
import json, re, sys
from pathlib import Path
out = Path(sys.argv[1])
res = {"movies": {}, "patches": 0, "retried": 0, "retry_converged": 0, "warnings": 0}
for log in sorted((out / "Movies").glob("*.log")):
    text = log.read_text()
    res["warnings"] += text.count("WARNING:")
    blocks = re.split(r"(?m)^Patch \(", text)[1:]
    m = {"patches": len(blocks), "retried": 0, "retry_converged": 0}
    for b in blocks:
        done = re.findall(r"\[CUDA Patch Alignment\] completed; converged=(yes|no)", b)
        if len(done) >= 2:
            m["retried"] += 1
            if done[-1] == "yes":
                m["retry_converged"] += 1
    res["movies"][log.name] = m
    for k in ("patches", "retried", "retry_converged"):
        res[k] += m[k]
print(json.dumps(res))
