#!/usr/bin/env python3
"""24-movie arm comparison: measured wall, split into GPU kernel / GPU transfer /
host-only, with PCIe bytes alongside. Same colour meaning as every other chart
in this set: blue = GPU kernel, orange = GPU transfer, neutral = GPU idle."""
import json, html, sys
d = json.load(open(sys.argv[2]))
OUT = sys.argv[1]
SURF, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
KERN, MCPY, IDLE = "#2a78d6", "#eb6834", "#e6e5e0"
W, L, Rm, TOP = 1480, 206, 330, 128
PW = W - L - Rm
arms = d["arms"]
XMAX = 34.0
x = lambda s: L + PW*s/XMAX
ROWH, GAP = 40, 26
H = TOP + len(arms)*(ROWH+GAP) + 112
o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
     f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
     f'<rect width="{W}" height="{H}" fill="{SURF}"/>']
T = lambda xx,yy,s,sz=11,f=MUTED,a="start",w="normal": (
    f'<text x="{xx:.1f}" y="{yy:.1f}" font-size="{sz}" fill="{f}" text-anchor="{a}" '
    f'font-weight="{w}">{html.escape(s)}</text>')
o.append(T(L-190, 32, "24 movies on one A100: what the ingest path is worth", 18, INK, "start", "bold"))
o.append(T(L-190, 52, "Mean of 2 unprofiled runs each, same host, same 8-CPU mask, same 24 movies. "
                      "Bars split by what the GPU was doing.", 11.5, INK2))
o.append(T(L-190, 69, "The three candidate arms are the SAME binary with --ingest forced, so the "
                      "differences between them are the ingest path alone.", 11.5, INK2))
lx = L-190
for lab, col in (("GPU kernel", KERN), ("GPU transfer", MCPY), ("GPU idle (host-only work)", IDLE)):
    o.append(f'<rect x="{lx}" y="86" width="12" height="12" rx="2" fill="{col}" stroke="{AXIS}" stroke-width="0.6"/>')
    o.append(T(lx+17, 96.5, lab, 11, INK2)); lx += 36 + len(lab)*6.1
t = 0
while t <= XMAX:
    o.append(f'<line x1="{x(t):.1f}" y1="{TOP-14}" x2="{x(t):.1f}" y2="{TOP+len(arms)*(ROWH+GAP)-GAP+6}" '
             f'stroke="{AXIS}" stroke-width="0.5" stroke-dasharray="2 4" opacity="0.6"/>')
    o.append(T(x(t), TOP-20, f"{t:g}", 10.5, MUTED, "middle"))
    t += 5
o.append(T(L+PW/2, TOP-38, "wall-clock seconds for all 24 movies", 10.5, MUTED, "middle"))

y = TOP
base = arms[0]["wall"]
for a in arms:
    nm = a["name"]; wall = a["wall"]
    o.append(T(L-10, y+18, nm, 12.5, INK, "end", "bold" if "nvcomp" in nm else "normal"))
    o.append(T(L-10, y+33, "%.1f / %.1f s" % tuple(a["walls"]), 10, MUTED, "end"))
    o.append(f'<rect x="{L}" y="{y}" width="{x(wall)-L:.1f}" height="{ROWH}" rx="3" '
             f'fill="{IDLE}" stroke="{AXIS}" stroke-width="0.6"/>')
    if "kern" in a:
        # scale traced device time onto the unprofiled wall (device work is
        # instrument-invariant; the span is not)
        kw = PW*a["kern"]/XMAX; mw = PW*a["mcpy"]/XMAX
        o.append(f'<rect x="{L}" y="{y}" width="{kw:.1f}" height="{ROWH}" rx="3" fill="{KERN}"/>')
        o.append(f'<rect x="{L+kw+1.5:.1f}" y="{y}" width="{mw:.1f}" height="{ROWH}" rx="3" fill="{MCPY}"/>')
        o.append(T(L+6, y+25, "%.1f" % a["kern"], 11, "#fff", "start", "bold"))
        if mw > 26: o.append(T(L+kw+7, y+25, "%.1f" % a["mcpy"], 11, "#fff", "start", "bold"))
    o.append(T(x(wall)+10, y+18, "%.1f s" % wall, 14, INK, "start", "bold"))
    if a is not arms[0]:
        o.append(T(x(wall)+10, y+33, "%.2fx faster than main" % (base/wall), 10.5, INK2))
    if "h2d_bytes" in a and a["h2d_bytes"]:
        o.append(T(W-16, y+18, "%.1f GB over PCIe" % (a["h2d_bytes"]/1e9), 11.5,
                   INK if "nvcomp" in nm else INK2, "end", "bold" if "nvcomp" in nm else "normal"))
        o.append(T(W-16, y+33, "%d kernel launches" % a["launches"], 10, MUTED, "end"))
    else:
        o.append(T(W-16, y+18, "not traced", 10.5, MUTED, "end"))
    y += ROWH + GAP

o.append(f'<line x1="{L-190}" y1="{H-74}" x2="{W-16}" y2="{H-74}" stroke="{AXIS}" stroke-width="1"/>')
o.append(T(L-190, H-54,
  "nvcomp wins twice. It moves Deflate decode onto the GPU (+0.59 s of inflate_kernel, 24 launches — one per movie),",
  11.5, INK2))
o.append(T(L-190, H-38,
  "and because the compressed strips go over PCIe instead of decompressed floats, H2D drops 34.2 GB → 4.6 GB (7.4x).",
  11.5, INK2))
o.append(T(L-190, H-22,
  "Net: +0.59 s of GPU kernel buys −8.6 s of host decode and −2.4 s of transfer. CPU samples fall 93,399 → 21,685.",
  11.5, INK))
o.append('</svg>')
open(OUT, "w").write("\n".join(o))
print("wrote", OUT)
