#!/usr/bin/env python3
"""Two charts from arms24.json, deliberately NOT one.

An earlier version of this script drew a single bar whose LENGTH was the mean of two
UNPROFILED production runs, then painted kernel and memcpy rectangles measured in a
SEPARATELY PROFILED run on top of it, leaving the remainder shaded as "GPU idle
(host-only work)". Those are two different executions: for `main` the unprofiled wall
is 31.359 s while the profiled span is 38.705 s, so the residual was a cross-run
difference, not a measured idle interval. The untraced `compact` arm rendered as a
100% bar in the idle colour, drawing "unknown" as "zero GPU activity".

This version emits:
  arms24_wall.svg    unprofiled production wall only, every observation plotted.
  arms24_device.svg  device occupancy inside each arm's OWN profiled capture, with
                     the span as the denominator. Untraced arms are hatched unknown.

Nothing is subtracted across runs and nothing untraced is drawn as zero.
"""
import json, html, sys, os

if len(sys.argv) < 3:
    raise SystemExit("usage: mkarms24.py <out-prefix> <arms24.json>\n"
                     "  writes <prefix>_wall.svg and <prefix>_device.svg")
PREFIX = sys.argv[1]
if PREFIX.endswith(".svg"): PREFIX = PREFIX[:-4]
d = json.load(open(sys.argv[2]))
arms = d["arms"]
dirn = os.path.dirname(PREFIX)
if dirn: os.makedirs(dirn, exist_ok=True)

SURF, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
KERN, MCPY, IDLE, UNK = "#2a78d6", "#eb6834", "#e6e5e0", "#b9b7ae"

def T(x, y, s, sz=11, f=MUTED, a="start", w="normal"):
    s = html.escape(str(s))
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{sz}" fill="{f}" '
            f'text-anchor="{a}" font-weight="{w}">{s}</text>')

def frame(W, H, body, extra=""):
    return ("\n".join(
        [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="Helvetica Neue,Helvetica,Arial,sans-serif">',
         '<defs><pattern id="unk" width="7" height="7" patternUnits="userSpaceOnUse" '
         'patternTransform="rotate(45)"><rect width="7" height="7" fill="#f2f1ec"/>'
         f'<line x1="0" y1="0" x2="0" y2="7" stroke="{UNK}" stroke-width="2.4"/></pattern></defs>',
         f'<rect width="{W}" height="{H}" fill="{SURF}"/>'] + body + extra.split("\n") + ["</svg>"]))

# ---------------------------------------------------------------- chart 1: wall
W, L, Rm, TOP, ROWH, GAP = 1320, 240, 300, 120, 40, 24
PW = W - L - Rm
XMAX = max(max(a["walls"]) for a in arms) * 1.08
x = lambda s: L + PW * s / XMAX
H = TOP + len(arms) * (ROWH + GAP) + 108
o = [T(26, 42, "24-movie wall clock, unprofiled production runs", 19, INK, "start", "bold"),
     T(26, 64, "Every observation plotted. No profiled quantity appears on this chart.", 12, INK2)]
t = 0
while t <= XMAX:
    o.append(f'<line x1="{x(t):.1f}" y1="{TOP-10}" x2="{x(t):.1f}" y2="{H-92}" stroke="{AXIS}" '
             f'stroke-width="0.5" stroke-dasharray="2 4" opacity="0.7"/>')
    o.append(T(x(t), TOP-18, "%g" % t, 10.5, MUTED, "middle")); t += 5
o.append(T(L + PW/2, TOP-38, "seconds", 10.5, MUTED, "middle"))
y = TOP
for a in arms:
    ws = a["walls"]; mean = a["wall"]
    o.append(T(L-12, y+18, a["name"], 13, INK, "end", "bold" if "nvcomp" in a["name"] else "normal"))
    o.append(T(L-12, y+33, "n=%d: %s" % (len(ws), " / ".join("%.3f" % v for v in ws)), 10, MUTED, "end"))
    o.append(f'<rect x="{L}" y="{y}" width="{x(mean)-L:.1f}" height="{ROWH}" rx="3" fill="{IDLE}" '
             f'stroke="{AXIS}" stroke-width="0.6"/>')
    for v in ws:
        o.append(f'<line x1="{x(v):.1f}" y1="{y+5}" x2="{x(v):.1f}" y2="{y+ROWH-5}" '
                 f'stroke="{INK}" stroke-width="1.6" opacity="0.75"/>')
    o.append(T(x(mean)+12, y+25, "%.3f s mean" % mean, 14, INK, "start", "bold"))
    y += ROWH + GAP
o.append(f'<line x1="26" y1="{H-80}" x2="{W-26}" y2="{H-80}" stroke="{AXIS}"/>')
o.append(T(26, H-58, "Bar length is the arm mean; vertical rules are the individual runs. "
                     "Two observations per arm is a screen, not a confirmation.", 11, INK2))
o.append(T(26, H-40, "These walls were measured WITHOUT a profiler attached and are not comparable "
                     "with the profiled spans in the device chart.", 11, INK2))
open(PREFIX + "_wall.svg", "w").write(frame(W, H, o)); print("wrote", PREFIX + "_wall.svg")

# -------------------------------------------------------------- chart 2: device
traced = [a for a in arms if "span" in a]
XMAX = max(a["span"] for a in traced) * 1.08 if traced else 1.0
x = lambda s: L + PW * s / XMAX
H = TOP + len(arms) * (ROWH + GAP) + 132
o = [T(26, 42, "GPU occupancy inside each arm's own profiled capture", 19, INK, "start", "bold"),
     T(26, 64, "Denominator is that capture's traced span, not a production wall. "
               "Spans are inflated by CUPTI.", 12, INK2)]
for i, (c, lab) in enumerate([(KERN, "kernel"), (MCPY, "memcpy"), (IDLE, "remainder of span"),
                              ("url(#unk)", "not traced - unknown")]):
    o += [f'<rect x="{L+i*190}" y="{TOP-34}" width="13" height="13" fill="{c}" stroke="{AXIS}" stroke-width="0.5"/>',
          T(L+i*190+19, TOP-23, lab, 11, INK2)]
t = 0
while t <= XMAX:
    o.append(f'<line x1="{x(t):.1f}" y1="{TOP-10}" x2="{x(t):.1f}" y2="{H-116}" stroke="{AXIS}" '
             f'stroke-width="0.5" stroke-dasharray="2 4" opacity="0.7"/>')
    o.append(T(x(t), TOP-18, "%g" % t, 10.5, MUTED, "middle")); t += 5
y = TOP
for a in arms:
    o.append(T(L-12, y+18, a["name"], 13, INK, "end", "bold" if "nvcomp" in a["name"] else "normal"))
    if "span" not in a:
        o.append(T(L-12, y+33, "no capture", 10, MUTED, "end"))
        o.append(f'<rect x="{L}" y="{y}" width="{PW:.1f}" height="{ROWH}" rx="3" fill="url(#unk)" '
                 f'stroke="{AXIS}" stroke-width="0.6"/>')
        o.append(T(L + PW/2, y+25, "not traced - device activity unknown", 12, INK2, "middle", "bold"))
        y += ROWH + GAP; continue
    span, kern, mcpy = a["span"], a["kern"], a["mcpy"]
    o.append(T(L-12, y+33, "span %.3f s" % span, 10, MUTED, "end"))
    o.append(f'<rect x="{L}" y="{y}" width="{x(span)-L:.1f}" height="{ROWH}" rx="3" fill="{IDLE}" '
             f'stroke="{AXIS}" stroke-width="0.6"/>')
    kw, mw = PW*kern/XMAX, PW*mcpy/XMAX
    o.append(f'<rect x="{L}" y="{y}" width="{kw:.1f}" height="{ROWH}" rx="3" fill="{KERN}"/>')
    o.append(f'<rect x="{L+kw:.1f}" y="{y}" width="{mw:.1f}" height="{ROWH}" rx="3" fill="{MCPY}"/>')
    if kw > 30: o.append(T(L+7, y+25, "%.2f" % kern, 11, "#fff", "start", "bold"))
    if mw > 30: o.append(T(L+kw+7, y+25, "%.2f" % mcpy, 11, "#fff", "start", "bold"))
    o.append(T(x(span)+12, y+18, "device busy <= %.1f%% of span" % (100.0*(kern+mcpy)/span), 12, INK, "start", "bold"))
    o.append(T(x(span)+12, y+33, "%d launches, %.1f GB H2D" % (a["launches"], a["h2d_bytes"]/1e9), 10, MUTED))
    y += ROWH + GAP
o.append(f'<line x1="26" y1="{H-104}" x2="{W-26}" y2="{H-104}" stroke="{AXIS}"/>')
o.append(T(26, H-82, "Kernel and memcpy are unioned separately and may overlap each other, so busy time is AT MOST "
                     "their sum and the remainder is a LOWER bound on idle.", 11, INK2))
o.append(T(26, H-64, "The remainder is therefore shown only as remainder of span. Quantifying device inactivity needs a "
                     "union over kernel and memcpy together within one trace.", 11, INK2))
o.append(T(26, H-46, "An arm with no capture is hatched. Absence of a trace is not absence of GPU work.", 11, INK2))
open(PREFIX + "_device.svg", "w").write(frame(W, H, o)); print("wrote", PREFIX + "_device.svg")
