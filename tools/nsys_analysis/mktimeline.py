#!/usr/bin/env python3
import sys, json, html, sys

d = json.load(open(sys.argv[2]))
OUT = sys.argv[1]
MS = lambda ns: ns/1e6
SPAN = MS(d["t1"])

# --- design tokens (validated default palette) -----------------------------
SURF, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
KERN, MCPY, IDLE = "#2a78d6", "#eb6834", "#e6e5e0"

W, L, Rm = 1480, 196, 150
PW = W - L - Rm
x = lambda ms: L + PW*ms/SPAN

rows = d["stages"]
ROWH, GAP = 21, 4
TOP = 108
LANE_Y = TOP + len(rows)*(ROWH+GAP) + 34
H = LANE_Y + 150

o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
     f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
     f'<rect width="{W}" height="{H}" fill="{SURF}"/>']
T = lambda xx,yy,s,sz=11,f=MUTED,anc="start",w="normal": (
    f'<text x="{xx:.1f}" y="{yy:.1f}" font-size="{sz}" fill="{f}" text-anchor="{anc}" '
    f'font-weight="{w}">{html.escape(s)}</text>')

o.append(T(L, 30, "MotionCorr — one movie, one A100: where the wall clock goes", 17, INK, "start", "bold"))
o.append(T(L, 48, "Pipeline stages (NVTX) against actual GPU device activity. "
                  "Bar fill = time the GPU was executing; hollow = GPU idle.", 11.5, INK2))

# legend
lx = L
for lab, col in (("GPU kernel", KERN), ("GPU memcpy", MCPY), ("GPU idle (host-only)", IDLE)):
    o.append(f'<rect x="{lx}" y="62" width="11" height="11" rx="2" fill="{col}" '
             f'stroke="{AXIS}" stroke-width="0.6"/>')
    o.append(T(lx+16, 71.5, lab, 11, INK2)); lx += 34 + len(lab)*6.1

# time axis
step = 250
o.append(f'<line x1="{L}" y1="{TOP-12}" x2="{L+PW}" y2="{TOP-12}" stroke="{AXIS}" stroke-width="1"/>')
t = 0
while t <= SPAN:
    o.append(f'<line x1="{x(t):.1f}" y1="{TOP-12}" x2="{x(t):.1f}" y2="{LANE_Y+58}" '
             f'stroke="{AXIS}" stroke-width="0.5" stroke-dasharray="2 4" opacity="0.55"/>')
    o.append(T(x(t), TOP-18, f"{t:g}", 10, MUTED, "middle"))
    t += step
o.append(T(L+PW/2, TOP-34, "milliseconds from process start", 10.5, MUTED, "middle"))

# movie window
m0, m1 = MS(d["movie"][0]), MS(d["movie"][1])
o.append(f'<rect x="{x(m0):.1f}" y="{TOP-8}" width="{x(m1)-x(m0):.1f}" height="{LANE_Y+62-TOP}" '
         f'fill="#2a78d6" opacity="0.035"/>')

# ---- stage rows -----------------------------------------------------------
y = TOP
for s in rows:
    wall, k, m = s["wall"], s["kern"], s["mcpy"]
    x0, x1 = x(MS(s["start"])), x(MS(s["end"]))
    o.append(T(L-8, y+14.5, s["name"] + (f"  ×{s['n']}" if s["n"] > 1 else ""), 11.5, INK, "end"))
    o.append(f'<rect x="{x0:.1f}" y="{y}" width="{max(x1-x0,1.2):.1f}" height="{ROWH}" rx="2" '
             f'fill="{IDLE}" stroke="{AXIS}" stroke-width="0.5"/>')
    # GPU-busy fill, proportional, drawn from the left of the stage span
    span_px = max(x1-x0, 1.2)
    kw = span_px*k/wall if wall else 0
    mw = span_px*m/wall if wall else 0
    if kw > 0.3:
        o.append(f'<rect x="{x0:.1f}" y="{y}" width="{kw:.1f}" height="{ROWH}" rx="2" fill="{KERN}"/>')
    if mw > 0.3:
        o.append(f'<rect x="{x0+kw+ (1.4 if kw>0.3 else 0):.1f}" y="{y}" width="{max(mw-1.4,0.4):.1f}" '
                 f'height="{ROWH}" rx="2" fill="{MCPY}"/>')
    gpupct = 100.0*(k+m)/wall if wall else 0
    o.append(T(x1+8, y+14.5, f"{MS(wall):.0f} ms", 11, INK))
    o.append(T(x1+62, y+14.5, f"{gpupct:.0f}% GPU", 10.5,
               INK2 if gpupct >= 40 else MUTED))
    y += ROWH + GAP

# ---- GPU device lane ------------------------------------------------------
o.append(T(L-8, LANE_Y+16, "GPU device", 12, INK, "end", "bold"))
o.append(T(L-8, LANE_Y+30, "(actual execution)", 9.5, MUTED, "end"))
o.append(f'<rect x="{L}" y="{LANE_Y}" width="{PW}" height="26" fill="{IDLE}" '
         f'stroke="{AXIS}" stroke-width="0.6" rx="2"/>')
# rasterise to pixel columns so sub-pixel activity still shows
cols_k = [0.0]*int(PW); cols_m = [0.0]*int(PW)
for arr, cols in ((d["kernel"], cols_k), (d["memcpy"], cols_m)):
    for a, b in arr:
        pa, pb = PW*MS(a)/SPAN, PW*MS(b)/SPAN
        i0, i1 = int(pa), min(int(pb), len(cols)-1)
        for i in range(i0, i1+1):
            cols[i] += min(pb, i+1) - max(pa, i)
for i in range(int(PW)):
    tot = cols_k[i] + cols_m[i]
    if tot <= 0.002: continue
    kh = 26*min(cols_k[i], 1.0); mh = 26*min(cols_m[i], 1.0)
    if cols_k[i] + cols_m[i] > 1:
        s = 1.0/(cols_k[i]+cols_m[i]); kh, mh = 26*cols_k[i]*s, 26*cols_m[i]*s
    yy = LANE_Y + 26
    if mh > 0: yy -= mh; o.append(f'<rect x="{L+i}" y="{yy:.2f}" width="1.05" height="{mh:.2f}" fill="{MCPY}"/>')
    if kh > 0: yy -= kh; o.append(f'<rect x="{L+i}" y="{yy:.2f}" width="1.05" height="{kh:.2f}" fill="{KERN}"/>')

# ---- callouts -------------------------------------------------------------
ann = [(0, m0, "process + CUDA init"),
       (MS(d["stages"][1]["end"]), MS(d["stages"][2]["start"]), "CudaMovieSession::initialize\n3 GB cudaMalloc + cuFFT plans\n(7 OpenMP workers spin)"),
       (MS(d["stages"][-1]["end"]), m1, "session teardown\ncudaFree 3 GB (blocked in poll)"),
       (m1, SPAN, "logfile.pdf via ghostscript\n4 × system() — once per JOB")]
ay = LANE_Y + 46
for a, b, lab in ann:
    xa, xb = x(a), x(b)
    if xb-xa < 3: continue
    o.append(f'<path d="M{xa:.1f} {ay} L{xa:.1f} {ay+6} L{xb:.1f} {ay+6} L{xb:.1f} {ay}" '
             f'fill="none" stroke="{MUTED}" stroke-width="1"/>')
    for j, line in enumerate(lab.split("\n")):
        o.append(T((xa+xb)/2, ay+20+j*11.5, line, 9.8,
                   INK2 if j == 0 else MUTED, "middle", "bold" if j == 0 else "normal"))

o.append(T(L, H-16,
           f"GPU busy {MS(d['tot_kern']+d['tot_mcpy']):.0f} ms of {SPAN:.0f} ms traced "
           f"({100*(d['tot_kern']+d['tot_mcpy'])/d['t1']:.0f}%) · kernels {MS(d['tot_kern']):.0f} ms, "
           f"transfers {MS(d['tot_mcpy']):.0f} ms · no kernel/copy overlap anywhere in the run",
           11, INK2))
o.append('</svg>')
open(OUT, "w").write("\n".join(o))
print("wrote", OUT)
