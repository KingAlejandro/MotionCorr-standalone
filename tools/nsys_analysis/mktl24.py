#!/usr/bin/env python3
"""24-movie GPU device lanes, main vs nvcomp, on one shared time axis,
plus the per-movie wall series underneath."""
import json, html, sys
d = json.load(open(sys.argv[2])); OUT = sys.argv[1]
SURF, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
KERN, MCPY, IDLE = "#2a78d6", "#eb6834", "#e6e5e0"
W, L, Rm, TOP = 1480, 150, 120, 118
PW = W - L - Rm
SPAN = max(v["span"] for v in d["lanes"].values())
x = lambda s: L + PW*s/SPAN
LANES = [("main @1d7e13f", "main"), ("cand --ingest float", "float"), ("cand --ingest nvcomp", "nvcomp")]
LH, LGAP = 40, 46
PLOT_Y = TOP + len(LANES)*(LH+LGAP) + 18
PLOT_H = 130
H = PLOT_Y + PLOT_H + 76
o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
     f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
     f'<rect width="{W}" height="{H}" fill="{SURF}"/>']
T = lambda xx,yy,s,sz=11,f=MUTED,a="start",w="normal": (
    f'<text x="{xx:.1f}" y="{yy:.1f}" font-size="{sz}" fill="{f}" text-anchor="{a}" '
    f'font-weight="{w}">{html.escape(s)}</text>')
o.append(T(L-140, 32, "24 movies, one A100: the GPU timeline for each ingest path", 18, INK, "start", "bold"))
o.append(T(L-140, 52, "Every kernel and every transfer the device executed, on one shared clock. "
                      "Each lane is one complete 24-movie job.", 11.5, INK2))
lx = L-140
for lab, col in (("GPU kernel", KERN), ("GPU transfer", MCPY), ("GPU idle", IDLE)):
    o.append(f'<rect x="{lx}" y="68" width="12" height="12" rx="2" fill="{col}" stroke="{AXIS}" stroke-width="0.6"/>')
    o.append(T(lx+17, 78.5, lab, 11, INK2)); lx += 34 + len(lab)*6.1
t = 0
while t <= SPAN:
    o.append(f'<line x1="{x(t):.1f}" y1="{TOP-14}" x2="{x(t):.1f}" y2="{PLOT_Y+PLOT_H}" stroke="{AXIS}" '
             f'stroke-width="0.5" stroke-dasharray="2 4" opacity="0.55"/>')
    o.append(T(x(t), TOP-20, f"{t:g}", 10.5, MUTED, "middle"))
    t += 5
o.append(T(L+PW/2, TOP-38, "seconds from process start (traced run; CUPTI inflates all lanes alike)", 10.5, MUTED, "middle"))

y = TOP
for label, key in LANES:
    lane = d["lanes"][key]
    o.append(T(L-10, y+19, label, 12.5, INK, "end", "bold" if key == "nvcomp" else "normal"))
    o.append(T(L-10, y+34, "span %.1f s" % lane["span"], 10, MUTED, "end"))
    o.append(f'<rect x="{L}" y="{y}" width="{x(lane["span"])-L:.1f}" height="{LH}" fill="{IDLE}" '
             f'stroke="{AXIS}" stroke-width="0.6" rx="2"/>')
    ck = [0.0]*int(PW); cm = [0.0]*int(PW)
    for arr, cols in ((lane["kernel"], ck), (lane["memcpy"], cm)):
        for a, b in arr:
            pa, pb = PW*a/SPAN, PW*b/SPAN
            i0, i1 = int(pa), min(int(pb), len(cols)-1)
            for i in range(i0, i1+1): cols[i] += min(pb, i+1) - max(pa, i)
    for i in range(int(PW)):
        tot = ck[i]+cm[i]
        if tot <= 0.002: continue
        kh, mh = LH*min(ck[i], 1.0), LH*min(cm[i], 1.0)
        if tot > 1: s = 1.0/tot; kh, mh = LH*ck[i]*s, LH*cm[i]*s
        yy = y + LH
        if mh > 0: yy -= mh; o.append(f'<rect x="{L+i}" y="{yy:.2f}" width="1.05" height="{mh:.2f}" fill="{MCPY}"/>')
        if kh > 0: yy -= kh; o.append(f'<rect x="{L+i}" y="{yy:.2f}" width="1.05" height="{kh:.2f}" fill="{KERN}"/>')
    busy = sum(b-a for a, b in lane["kernel"]) + sum(b-a for a, b in lane["memcpy"])
    o.append(T(x(lane["span"])+10, y+19, "%.0f%% busy" % (100*busy/lane["span"]), 12, INK, "start", "bold"))
    o.append(T(x(lane["span"])+10, y+34, "%.0f%% idle" % (100-100*busy/lane["span"]), 10, MUTED))
    y += LH + LGAP

# per-movie wall series
pm_main, pm_nv = d["permovie"]["main"], d["permovie"]["nvcomp"]
ymax = max(max(pm_main), max(pm_nv))*1.12
py = lambda v: PLOT_Y + PLOT_H - PLOT_H*v/ymax
o.append(T(L-10, PLOT_Y+12, "per-movie", 12, INK, "end", "bold"))
o.append(T(L-10, PLOT_Y+27, "wall (traced)", 10, MUTED, "end"))
for g in (0, 0.5, 1.0, 1.5):
    if g > ymax: continue
    o.append(f'<line x1="{L}" y1="{py(g):.1f}" x2="{L+PW}" y2="{py(g):.1f}" stroke="{AXIS}" '
             f'stroke-width="{1 if g==0 else 0.5}" opacity="{1 if g==0 else 0.5}"/>')
    o.append(T(L-8, py(g)+3.5, "%.1f s" % g, 10, MUTED, "end"))
BW = PW/24.0
for i in range(24):
    bx = L + i*BW
    for vals, col, off in ((pm_main, KERN, 0.10), (pm_nv, MCPY, 0.52)):
        v = vals[i]
        o.append(f'<rect x="{bx+BW*off:.1f}" y="{py(v):.1f}" width="{BW*0.36:.1f}" '
                 f'height="{PLOT_Y+PLOT_H-py(v):.1f}" fill="{col}" rx="1.5"/>')
    if i % 4 == 0: o.append(T(bx+BW/2, PLOT_Y+PLOT_H+15, str(i+1), 9.5, MUTED, "middle"))
o.append(T(L+PW/2, PLOT_Y+PLOT_H+32, "movie index", 10.5, MUTED, "middle"))
o.append(f'<rect x="{L+PW-200}" y="{PLOT_Y+4}" width="10" height="10" rx="2" fill="{KERN}"/>')
o.append(T(L+PW-186, PLOT_Y+13, "main", 10.5, INK2))
o.append(f'<rect x="{L+PW-130}" y="{PLOT_Y+4}" width="10" height="10" rx="2" fill="{MCPY}"/>')
o.append(T(L+PW-116, PLOT_Y+13, "nvcomp", 10.5, INK2))
o.append(T(L-140, H-40,
  "Movie 1 costs ~0.2 s more than the rest in both arms — SM clock ramps from 210 MHz "
  "(persistence mode is off) and the page cache is cold.", 11, INK2))
o.append(T(L-140, H-22,
  "The nvcomp lane is not just shorter: it is denser. Same work, less wall, and the device "
  "is doing a larger share of it.", 11, INK2))
o.append('</svg>')
open(OUT, "w").write("\n".join(o))
print("wrote", OUT, "H=", H)
