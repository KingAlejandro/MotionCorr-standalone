#!/usr/bin/env python3
"""Device memory across a whole 24-movie job, main vs nvcomp."""
import json, html, sys
d = json.load(open(sys.argv[2])); OUT = sys.argv[1]
SURF, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
C_MAIN, C_NV = "#2a78d6", "#eb6834"
GIB = 2**30
W, L, Rm, TOP, PH = 1480, 96, 190, 112, 230
PW = W - L - Rm
SPAN = max(d["lanes"][k]["span"] for k in ("main", "nvcomp"))
YMAX = 3.4
x = lambda s: L + PW*s/SPAN
y = lambda g: TOP + PH - PH*g/YMAX
H = TOP + PH + 104
o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
     f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
     f'<rect width="{W}" height="{H}" fill="{SURF}"/>']
T = lambda xx,yy,s,sz=11,f=MUTED,a="start",w="normal": (
    f'<text x="{xx:.1f}" y="{yy:.1f}" font-size="{sz}" fill="{f}" text-anchor="{a}" '
    f'font-weight="{w}">{html.escape(s)}</text>')
o.append(T(L-80, 32, "Device memory across all 24 movies", 18, INK, "start", "bold"))
o.append(T(L-80, 52, "The whole ~3 GiB reservation is built and torn down once per movie — 24 complete "
                     "cycles, never pooled across the job.", 11.5, INK2))
for lab, col in (("main @1d7e13f", C_MAIN), ("cand --ingest nvcomp", C_NV)):
    xx = L-80 if "main" in lab else L+130
    o.append(f'<rect x="{xx}" y="66" width="12" height="12" rx="2" fill="{col}"/>')
    o.append(T(xx+17, 76.5, lab, 11, INK2))
for g in (0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
    o.append(f'<line x1="{L}" y1="{y(g):.1f}" x2="{L+PW}" y2="{y(g):.1f}" stroke="{AXIS}" '
             f'stroke-width="{1 if g==0 else 0.5}" opacity="{1 if g==0 else 0.5}"/>')
    o.append(T(L-8, y(g)+3.5, f"{g:g} GiB", 10.5, MUTED, "end"))
t = 0
while t <= SPAN:
    o.append(f'<line x1="{x(t):.1f}" y1="{TOP}" x2="{x(t):.1f}" y2="{TOP+PH}" stroke="{AXIS}" '
             f'stroke-width="0.5" stroke-dasharray="2 4" opacity="0.5"/>')
    o.append(T(x(t), TOP+PH+16, f"{t:g}", 10, MUTED, "middle")); t += 5
o.append(T(L+PW/2, TOP+PH+33, "seconds from process start", 10.5, MUTED, "middle"))
for key, col in (("main", C_MAIN), ("nvcomp", C_NV)):
    pts = d["vram"][key]
    path = []; py = 0.0
    path.append(f'M {x(pts[0][0]):.2f} {y(0):.2f}')
    for s_, by in pts:
        g = by/GIB
        path.append(f'L {x(s_):.2f} {y(py):.2f} L {x(s_):.2f} {y(g):.2f}')
        py = g
    end = d["lanes"][key]["span"]
    path.append(f'L {x(end):.2f} {y(py):.2f}')
    o.append(f'<path d="{" ".join(path)}" fill="none" stroke="{col}" stroke-width="1.3" '
             f'stroke-linejoin="round" opacity="0.92"/>')
    pk = max(p[1] for p in pts)/GIB
    o.append(f'<line x1="{L}" y1="{y(pk):.1f}" x2="{L+PW}" y2="{y(pk):.1f}" stroke="{col}" '
             f'stroke-width="1" stroke-dasharray="5 4" opacity="0.5"/>')
    o.append(T(L+PW+10, y(pk)+4 + (0 if key == "nvcomp" else 15),
               "peak %.2f GiB (%s)" % (pk, key), 11, col, "start", "bold"))
o.append(T(L+PW+10, y(0)+4, "0 — fully released", 10.5, MUTED))
o.append(T(L-80, H-56, "nvcomp peaks 0.15 GiB higher (3.13 vs 2.98) — it holds the compressed strips and the "
                       "inflate scratch — and finishes in 16.7 s instead of 38.7 s.", 11, INK2))
o.append(T(L-80, H-38, "Both run at under 4% of an 80 GB card. The sawtooth is the cost: session setup plus "
                       "teardown is a measured 283 ms per movie (median),", 11, INK2))
o.append(T(L-80, H-20, "7.0 s across the traced job \u2014 for a reservation that is the same size every time. "
                       "The unprofiled run is 19% shorter overall, so call it 5-7 s.", 11, INK))
o.append('</svg>')
open(OUT, "w").write("\n".join(o))
print("wrote", OUT, "H=", H)
