#!/usr/bin/env python3
"""Kit identity rule: MRC header 0-223 + bytes 1024.. (ext header + payload);
other files byte-identical after root normalisation; .log excluded; PDFs inventoried."""
import sys, os, struct
a, b = sys.argv[1], sys.argv[2]
def inv(r):
    out = {}
    for d, _, fs in os.walk(r):
        for f in fs:
            p = os.path.join(d, f); out[os.path.relpath(p, r)] = p
    return out
A, B = inv(a), inv(b)
bad = []; n_mrc = n_other = n_pdf = 0
if set(A) != set(B):
    bad.append(("inventory", sorted(set(A) ^ set(B))))
for k in sorted(set(A) & set(B)):
    if k.endswith(".log"): continue
    if k.endswith(".pdf"): n_pdf += 1; continue
    x, y = open(A[k], "rb").read(), open(B[k], "rb").read()
    if k.endswith(".mrc") or k.endswith(".mrcs"):
        n_mrc += 1
        if x[:224] != y[:224] or x[1024:] != y[1024:] or len(x) != len(y): bad.append(("mrc", k))
    else:
        n_other += 1
        if x.replace(a.encode(), b"@ROOT@") != y.replace(b.encode(), b"@ROOT@"): bad.append(("file", k))
print(f"{("IDENTICAL" if n_mrc else "NO-MRC") if not bad else "DIFFERENT"} mrc={n_mrc} other={n_other} pdf_inventoried={n_pdf} files={len(A)}/{len(B)}")
for x in bad[:20]: print("  ", x)
sys.exit(1 if bad or n_mrc == 0 else 0)
