#!/usr/bin/env python3
"""Strict identity of two merged dataset trees (excluding _workers/ staging): same inventory, MRC bytes
[0:224]+[1024:], text products with the output root spelled away, and EPS text, and inventory of .pdf/.lst."""
import hashlib, re, sys
from pathlib import Path
a, b = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
def digest(root):
    d = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file(): continue
        rel = p.relative_to(root)
        if rel.parts[0] == "_workers": continue
        raw = p.read_bytes()
        raw = re.sub(rb"runs/ds_[A-Za-z0-9]+", b"runs/ds_X", raw)
        raw = re.sub(rb"workers/w[0-9]+", b"workers/wN", raw)
        raw = re.sub(rb"\.aggregate-[A-Za-z0-9_]+", b".aggregate-X", raw)
        if p.suffix == ".mrc": h = hashlib.sha256(raw[:224] + raw[1024:]).hexdigest()
        elif p.suffix in (".star", ".eps"): h = hashlib.sha256(raw.replace(str(root).encode(), b"<ROOT>")).hexdigest()
        elif p.suffix == ".log":
            lines = [l for l in raw.replace(str(root).encode(), b"<ROOT>").split(b"\n")
                     if not any(m in l for m in (b" ms", b"time", b"Kernel", b"~~(,_,", b"sec .", b"free device memory", b"device memory in use rose"))]
            h = hashlib.sha256(b"\n".join(lines)).hexdigest()
        else: h = "present"  # .pdf and .lst: scratch paths / Ghostscript metadata; inventory only
        d[str(rel)] = h
    return d
da, db = digest(a), digest(b)
diff = sorted(k for k in set(da) | set(db) if da.get(k) != db.get(k))
print(f"files A={len(da)} B={len(db)} mrc={sum(k.endswith('.mrc') for k in da)} differing={len(diff)}")
for k in diff[:20]: print("  DIFF", k, da.get(k, "-")[:12], db.get(k, "-")[:12])
sys.exit(1 if diff else 0)
