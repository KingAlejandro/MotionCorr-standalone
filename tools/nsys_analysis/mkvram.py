#!/usr/bin/env python3
import sys, json, html, sys
d = json.load(open(sys.argv[2]))
OUT = sys.argv[1]
SURF, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
AREA, LINE = "#2a78d6", "#2a78d6"
W, L, Rm, TOP, PH = 1480, 92, 150, 96, 250
PW = W - L - Rm
SPAN = d["span"]
GIB = 2**30
YMAX = 3.25
x = lambda ms: L + PW*ms/SPAN
y = lambda g: TOP + PH - PH*g/YMAX
H = TOP + PH + 108
o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
     f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
     f'<rect width="{W}" height="{H}" fill="{SURF}"/>']
T = lambda xx,yy,s,sz=11,f=MUTED,a="start",w="normal": (
    f'<text x="{xx:.1f}" y="{yy:.1f}" font-size="{sz}" fill="{f}" text-anchor="{a}" '
    f'font-weight="{w}">{html.escape(s)}</text>')
o.append(T(L, 30, "Device memory resident on the GPU, one movie", 17, INK, "start", "bold"))
o.append(T(L, 48, "Every cudaMalloc/cudaFree on the device, accumulated. "
                  "One movie holds ~3 GiB for most of its life and returns all of it at the end.",
           11.5, INK2))

# grid + y axis
for g in [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
    o.append(f'<line x1="{L}" y1="{y(g):.1f}" x2="{L+PW}" y2="{y(g):.1f}" stroke="{AXIS}" '
             f'stroke-width="{1 if g==0 else 0.5}" opacity="{1 if g==0 else 0.5}"/>')
    o.append(T(L-8, y(g)+3.5, f"{g:g} GiB", 10.5, MUTED, "end"))
t = 0
while t <= SPAN:
    o.append(f'<line x1="{x(t):.1f}" y1="{TOP}" x2="{x(t):.1f}" y2="{TOP+PH}" stroke="{AXIS}" '
             f'stroke-width="0.5" stroke-dasharray="2 4" opacity="0.5"/>')
    o.append(T(x(t), TOP+PH+16, f"{t:g}", 10, MUTED, "middle"))
    t += 250
o.append(T(L+PW/2, TOP+PH+34, "milliseconds from process start", 10.5, MUTED, "middle"))

# stage bands (alternating faint) + labels
for i, (nm, a, b) in enumerate(d["stages"]):
    if b-a < 14: continue
    o.append(f'<rect x="{x(a):.1f}" y="{TOP}" width="{x(b)-x(a):.1f}" height="{PH}" '
             f'fill="{AREA}" opacity="{0.05 if i%2==0 else 0.10}"/>')
    if b-a >= 40:
        o.append(f'<text x="{(x(a)+x(b))/2:.1f}" y="{TOP-6}" font-size="9.5" fill="{MUTED}" '
                 f'text-anchor="end" transform="rotate(-38 {(x(a)+x(b))/2:.1f} {TOP-6})">'
                 f'{html.escape(nm)}</text>')

# step area
pts = d["pts"]
path = [f'M {x(pts[0][0]):.2f} {y(0):.2f}']
py = 0.0
for ms_, by in pts:
    g = by/GIB
    path.append(f'L {x(ms_):.2f} {y(py):.2f} L {x(ms_):.2f} {y(g):.2f}')
    py = g
path.append(f'L {x(SPAN):.2f} {y(py):.2f} L {x(SPAN):.2f} {y(0):.2f} Z')
o.append(f'<path d="{" ".join(path)}" fill="{AREA}" fill-opacity="0.18" stroke="none"/>')
o.append(f'<path d="{" ".join(path[:-1])}" fill="none" stroke="{LINE}" stroke-width="1.6" '
         f'stroke-linejoin="round"/>')

# peak marker
pk = d["peak"]/GIB
o.append(f'<line x1="{L}" y1="{y(pk):.1f}" x2="{L+PW}" y2="{y(pk):.1f}" stroke="#e34948" '
         f'stroke-width="1.2" stroke-dasharray="5 4"/>')
o.append(T(L+PW+8, y(pk)+4, f"peak {pk:.2f} GiB", 11.5, "#e34948", "start", "bold"))
o.append(T(L+PW+8, y(pk)+19, f"at {d['peakt']:.0f} ms", 10.5, MUTED))
o.append(T(L+PW+8, y(0)+4, "0 — fully released", 10.5, MUTED))

o.append(T(L, H-18, "A100 80 GB: this run never exceeds 3.7% of the card. 436 allocations / 266 frees, "
                    "3.6 GiB of churn, and the whole reservation is torn down between movies.",
           11, INK2))
o.append('</svg>')
open(OUT, "w").write("\n".join(o))
print("wrote", OUT)
