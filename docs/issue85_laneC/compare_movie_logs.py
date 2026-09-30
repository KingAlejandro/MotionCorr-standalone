import re, sys, pathlib
base, cand, label = sys.argv[1], sys.argv[2], sys.argv[3]
STAGING = "Staging this movie as native unsigned 16-bit"
# Drop the added diagnostic line and every line carrying a measured duration or a
# VRAM figure; what remains must be identical if the change is purely representational.
TIMING = re.compile(r"(\d+\.\d+\s*(ms|s|MiB)\b)|Full movie wall time|transfer time|execution time|alignment time|memory allocated|VRAM")
def norm(p, root):
    out = []
    for line in pathlib.Path(p).read_text(errors="replace").splitlines():
        if STAGING in line: continue
        if TIMING.search(line): continue
        out.append(line.replace(root, "<OUT>"))
    return out
bl = sorted(pathlib.Path(base).rglob("*.log")); cl = sorted(pathlib.Path(cand).rglob("*.log"))
assert len(bl) == len(cl) == 24, f"{len(bl)} vs {len(cl)}"
bad = []
for b, c in zip(bl, cl):
    if norm(b, base) != norm(c, cand):
        d = [(i, x, y) for i, (x, y) in enumerate(zip(norm(b, base), norm(c, cand))) if x != y]
        bad.append((b.name, d[:2]))
print(f"{label}: {len(bl)} logs compared, {len(bad)} differ after dropping the added line and all timing/VRAM lines")
for name, d in bad[:5]:
    print("   ", name, d)
