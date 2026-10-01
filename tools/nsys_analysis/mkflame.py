#!/usr/bin/env python3
"""Minimal self-contained flame graph renderer (folded stacks -> SVG)."""
import sys, collections, html

folded, out, title = sys.argv[1], sys.argv[2], sys.argv[3]
inverted = len(sys.argv) > 4 and sys.argv[4] == "icicle"

root = {"c": 0, "k": {}}
total = 0
for ln in open(folded):
    ln = ln.rstrip("\n")
    if not ln: continue
    st, n = ln.rsplit(" ", 1); n = int(n); total += n
    node = root; node["c"] += n
    for f in st.split(";"):
        node = node["k"].setdefault(f, {"c": 0, "k": {}})
        node["c"] += n

W, PAD, H, FS = 1600, 10, 17, 11
rows = []
def walk(node, name, depth, x):
    rows.append((depth, x, node["c"], name))
    cx = x
    for k in sorted(node["k"], key=lambda k: -node["k"][k]["c"]):
        walk(node["k"][k], k, depth+1, cx); cx += node["k"][k]["c"]
walk(root, "all", 0, 0)
maxd = max(r[0] for r in rows) + 1
HGT = maxd*H + 3*PAD + 40

def color(name, depth):
    if name.startswith("["):
        base = (120, 120, 140)                      # unresolved / module-only
        if "kernel.kallsyms" in name: base = (110, 90, 150)
        elif "libdeflate" in name:    base = (200, 90, 60)
        elif "libcuda" in name or "cudart" in name or "cufft" in name: base = (60, 140, 90)
        elif "libgomp" in name:       base = (190, 150, 50)
        elif "libgs" in name:         base = (150, 80, 130)
    elif name.startswith(("cuda", "cu")) and name[:4] in ("cuda", "cuMe", "cuLa", "cuMo"):
        base = (60, 160, 100)
    elif "TIFF" in name or "deflate" in name: base = (210, 100, 60)
    elif "MotioncorrRunner" in name or "CudaMovieSession" in name or "Image<" in name:
        base = (70, 110, 180)
    else:
        base = (150, 110, 70)
    j = (hash(name) % 28) - 14
    return "#%02x%02x%02x" % tuple(max(0, min(255, v+j)) for v in base)

o = []
o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{HGT}" '
         f'viewBox="0 0 {W} {HGT}" font-family="Helvetica,Arial,sans-serif">')
o.append(f'<rect width="{W}" height="{HGT}" fill="#ffffff"/>')
o.append(f'<text x="{W//2}" y="22" text-anchor="middle" font-size="15" '
         f'font-weight="bold" fill="#222">{html.escape(title)}</text>')
o.append(f'<text x="{W//2}" y="38" text-anchor="middle" font-size="11" fill="#666">'
         f'{total} wall-clock CPU samples &#183; width = share of CPU time</text>')
sx = (W - 2*PAD) / float(total)
for depth, x, c, name in rows:
    if c*sx < 0.35: continue
    px, pw = PAD + x*sx, max(c*sx, 0.35)
    py = (3*PAD + 24 + depth*H) if inverted else (HGT - PAD - (depth+1)*H)
    pct = 100.0*c/total
    o.append(f'<g><title>{html.escape(name)} &#8212; {c} samples ({pct:.2f}%)</title>'
             f'<rect x="{px:.2f}" y="{py}" width="{pw:.2f}" height="{H-1}" '
             f'fill="{color(name,depth)}" stroke="#fff" stroke-width="0.4" rx="1"/>')
    if pw > 36:
        maxch = int((pw-6)/6.0)
        t = name if len(name) <= maxch else name[:max(0, maxch-1)] + "…"
        o.append(f'<text x="{px+3:.2f}" y="{py+H-5}" font-size="{FS}" fill="#fff">'
                 f'{html.escape(t)}</text>')
    o.append('</g>')
o.append('</svg>')
open(out, "w").write("\n".join(o))
print(f"{out}: {total} samples, {len(rows)} boxes, depth {maxd}")
