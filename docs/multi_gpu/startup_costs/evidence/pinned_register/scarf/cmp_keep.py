"""cmp_trees.py's rule on the kept SCARF merged trees, with each arm's own run root
(/tmp/warmab/warm_<arm>), binary path (build-<arm>), the random
.aggregate-XXXXXX staging suffix and the worker pid normalised, since the trees
were copied out of their run directories."""
import os, re, sys
a, b = "keep/base", (sys.argv[1] if len(sys.argv) > 1 else "keep/cand")
def inv(r):
    return {os.path.relpath(os.path.join(d, f), r): os.path.join(d, f) for d, _, fs in os.walk(r) for f in fs}
def norm(x, arm):
    x = x.replace(f"/tmp/warmab/warm_{arm}".encode(), b"@ROOT@").replace(f"build-{arm}".encode(), b"build-@ARM@")
    x = re.sub(rb'"pid": \d+', b'"pid": @PID@', x)
    return re.sub(rb"\.aggregate-[A-Za-z0-9_]{6}", b".aggregate-@RND@", x)
A, B = inv(a), inv(b)
bad = []; n_mrc = n_other = n_pdf = 0
if set(A) != set(B): bad.append(("inventory", sorted(set(A) ^ set(B))))
for k in sorted(set(A) & set(B)):
    if k.endswith(".log"): continue
    if k.endswith(".pdf"): n_pdf += 1; continue
    x, y = open(A[k], "rb").read(), open(B[k], "rb").read()
    if k.endswith((".mrc", ".mrcs")):
        n_mrc += 1
        if x[:224] != y[:224] or x[1024:] != y[1024:] or len(x) != len(y): bad.append(("mrc", k))
    else:
        n_other += 1
        if norm(x, "base") != norm(y, "cand").replace(b.encode(), b"keep/cand"): bad.append(("file", k))
print(("IDENTICAL" if not bad else "DIFFERENT") + f" mrc={n_mrc} other={n_other} pdf_inventoried={n_pdf} files={len(A)}/{len(B)}")
for x in bad[:20]: print("  ", x)
