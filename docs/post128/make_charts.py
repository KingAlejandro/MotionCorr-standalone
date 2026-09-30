#!/usr/bin/env python3
"""Render the multi-GPU timing campaign as SVG figures and an HTML dashboard.

Reads the status.json files the launcher already writes, so no number is
retyped between the measurement and the figure. Pure stdlib: the validation
hosts have no numpy or matplotlib.

Palette and mark specs follow the project data-viz guidance. The categorical
slots (#2a78d6/#eb6834/#1baf7a) and the ordinal blue ramp were both checked
with its validator in light and dark. Aqua sits below 3:1 on the light
surface, so every chart that uses it ships direct labels and a table view,
which is the documented relief.
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

L = {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
     "grid": "#e1e0d9", "axis": "#c3c2b7",
     "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a",
     "ord": ["#86b6ef", "#5598e7", "#2a78d6", "#184f95"]}
D = {"surface": "#1a1a19", "ink": "#ffffff", "ink2": "#c3c2b7", "muted": "#898781",
     "grid": "#2c2c2a", "axis": "#383835",
     "s1": "#3987e5", "s2": "#d95926", "s3": "#199e70",
     "ord": ["#9ec5f4", "#6da7ec", "#3987e5", "#184f95"]}
FONT = 'system-ui,-apple-system,"Segoe UI",sans-serif'
GAP = 2.0          # surface gap between touching fills
CAP = 24.0         # max bar thickness
R = 4.0            # rounded data-end


def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nice_ticks(hi, n=5):
    if hi <= 0:
        return [0], 1
    raw = hi / n
    mag = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 0.1
    for m in (1, 2, 2.5, 5, 10):
        if mag * m >= raw:
            step = mag * m
            break
    else:
        step = mag * 10
    top = step * (int(hi / step) + 1)
    k, out = 0, []
    while k * step <= top + 1e-9:
        out.append(round(k * step, 6))
        k += 1
    return out, top


def top_round_rect(x, y, w, h, r):
    """Rounded data-end, square at the baseline (columns grow upward)."""
    if h <= 0:
        return ""
    r = min(r, h, w / 2)
    return (f'<path d="M{x:.2f},{y+h:.2f} L{x:.2f},{y+r:.2f} Q{x:.2f},{y:.2f} {x+r:.2f},{y:.2f} '
            f'L{x+w-r:.2f},{y:.2f} Q{x+w:.2f},{y:.2f} {x+w:.2f},{y+r:.2f} '
            f'L{x+w:.2f},{y+h:.2f} Z"/>')


def right_round_rect(x, y, w, h, r):
    if w <= 0:
        return ""
    r = min(r, w, h / 2)
    return (f'<path d="M{x:.2f},{y:.2f} L{x+w-r:.2f},{y:.2f} Q{x+w:.2f},{y:.2f} {x+w:.2f},{y+r:.2f} '
            f'L{x+w:.2f},{y+h-r:.2f} Q{x+w:.2f},{y+h:.2f} {x+w-r:.2f},{y+h:.2f} '
            f'L{x:.2f},{y+h:.2f} Z"/>')


class Svg:
    def __init__(self, w, h, C, title, subtitle=""):
        self.w, self.h, self.C = w, h, C
        self.o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
                  f'width="{w}" height="{h}" font-family=\'{FONT}\' '
                  f'role="img" aria-label="{esc(title)}">',
                  f'<rect width="{w}" height="{h}" fill="{C["surface"]}"/>']
        self.text(24, 30, title, 15, C["ink"], weight=600)
        if subtitle:
            self.text(24, 50, subtitle, 12, C["ink2"])

    def text(self, x, y, s, size=11, fill=None, anchor="start", weight=400, tabular=False):
        extra = ' font-variant-numeric="tabular-nums"' if tabular else ""
        self.o.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
                      f'fill="{fill or self.C["muted"]}" text-anchor="{anchor}" '
                      f'font-weight="{weight}"{extra}>{esc(s)}</text>')

    def line(self, x1, y1, x2, y2, stroke, w=1, cap="butt"):
        self.o.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                      f'stroke="{stroke}" stroke-width="{w}" stroke-linecap="{cap}"/>')

    def path(self, d, stroke=None, fill="none", w=2, dash=None):
        s = f'<path d="{d}" fill="{fill}"'
        if stroke:
            s += (f' stroke="{stroke}" stroke-width="{w}" stroke-linejoin="round" '
                  f'stroke-linecap="round"')
            if dash:
                s += f' stroke-dasharray="{dash}"'
        self.o.append(s + "/>")

    def shape(self, d, fill):
        self.o.append(d.replace("<path ", f'<path fill="{fill}" '))

    def dot(self, x, y, fill, r=4.5):
        # 2px surface ring, so overlapping markers stay legible
        self.o.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r+2:.2f}" fill="{self.C["surface"]}"/>')
        self.o.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="{fill}"/>')

    def legend(self, x, y, items):
        for lab, col in items:
            self.o.append(f'<rect x="{x:.1f}" y="{y-8:.1f}" width="10" height="10" rx="2" fill="{col}"/>')
            self.text(x + 16, y, lab, 11, self.C["ink2"])
            x += 20 + 7.0 * len(lab)

    def done(self):
        return "\n".join(self.o) + "\n</svg>\n"


def axes(s, X0, Y0, W, H, ticks, top, xlabels, ylab):
    C = s.C
    for t in ticks:
        y = Y0 + H - (t / top) * H
        s.line(X0, y, X0 + W, y, C["grid"], 1)
        s.text(X0 - 8, y + 3.5, f"{t:g}", 10, C["muted"], "end", tabular=True)
    s.line(X0, Y0 + H, X0 + W, Y0 + H, C["axis"], 1)
    s.text(X0 - 8, Y0 - 16, ylab, 10, C["muted"], "end")
    band = W / len(xlabels)
    for i, lab in enumerate(xlabels):
        s.text(X0 + band * (i + 0.5), Y0 + H + 18, lab, 11, C["ink2"], "middle")


def chart_attribution(data, C):
    """Stacked columns: where the wall time goes at each GPU count."""
    gs = sorted(data)
    W, H, X0, Y0 = 430, 210, 56, 76
    s = Svg(620, 340, C, "Where the wall time goes",
            "24 movies, median of 7 interleaved repeats. Setup and tail are the worst worker in each run.")
    hi = max(d["setup"] + d["produce"] + d["tail"] for d in data.values())
    ideal = data[gs[0]]["total"] / max(gs)
    ticks, top = nice_ticks(max(hi, ideal))
    axes(s, X0, Y0, W, H, ticks, top, [f"{g} GPU" for g in gs], "seconds")
    band = W / len(gs)
    bw = min(CAP, band * 0.5)
    for i, g in enumerate(gs):
        d = data[g]
        cx = X0 + band * (i + 0.5) - bw / 2
        acc = 0.0
        for key, col in (("setup", C["s1"]), ("produce", C["s2"]), ("tail", C["s3"])):
            v = d[key]
            if v <= 0:
                continue
            y0 = Y0 + H - ((acc + v) / top) * H
            hgt = (v / top) * H - (GAP if acc > 0 else 0)
            top_r = R if key == "tail" else 0.0
            s.shape(top_round_rect(cx, y0, bw, max(hgt, 0.6), top_r), col)
            acc += v
        s.text(cx + bw / 2, Y0 + H - (acc / top) * H - 8,
               f"{acc:.2f}s", 11, C["ink"], "middle", 600, tabular=True)
    # perfect-scaling reference: a hairline, labelled, not a competing series
    yi = Y0 + H - (ideal / top) * H
    s.line(X0, yi, X0 + W, yi, C["muted"], 1)
    # In the right margin, not over the plot: at 3 and 4 GPUs this line crosses
    # the bars, and a label anchored inside collided with them.
    s.text(X0 + W + 8, yi - 2, "perfect", 10, C["muted"], "start")
    s.text(X0 + W + 8, yi + 10, f"scaling {ideal:.2f}s", 10, C["muted"], "start")
    s.legend(X0, Y0 + H + 44, [("setup", C["s1"]), ("per-movie work", C["s2"]), ("aggregate tail", C["s3"])])
    return s.done()


def chart_speedup(data, C):
    gs = sorted(data)
    W, H, X0, Y0 = 420, 200, 56, 76
    s = Svg(520, 320, C, "Speedup against GPU count",
            "Measured against perfect linear scaling.")
    ticks, top = nice_ticks(max(gs))
    axes(s, X0, Y0, W, H, ticks, top, [str(g) for g in gs], "x faster")
    band = W / len(gs)
    xs = [X0 + band * (i + 0.5) for i in range(len(gs))]
    base = data[gs[0]]["total"]
    meas = [base / data[g]["total"] for g in gs]
    s.path("M" + " L".join(f"{x:.2f},{Y0+H-(g/top)*H:.2f}" for x, g in zip(xs, gs)),
           C["muted"], w=1.5, dash="1 4")
    s.text(xs[-1], Y0 + H - (gs[-1] / top) * H - 10, "ideal", 10, C["muted"], "end")
    s.path("M" + " L".join(f"{x:.2f},{Y0+H-(v/top)*H:.2f}" for x, v in zip(xs, meas)), C["s1"], w=2)
    for x, v in zip(xs, meas):
        s.dot(x, Y0 + H - (v / top) * H, C["s1"])
    s.text(xs[-1] - 6, Y0 + H - (meas[-1] / top) * H + 16,
           f"x{meas[-1]:.2f}", 12, C["ink"], "end", 600, tabular=True)
    s.text(X0 + W / 2, Y0 + H + 40, "GPUs", 11, C["ink2"], "middle")
    return s.done()


def chart_sweep(sweep, C):
    """Wall against movie count: intercept is the fixed cost, slope the marginal."""
    gs = sorted(sweep)
    W, H, X0, Y0 = 420, 200, 56, 86
    s = Svg(560, 330, C, "Fixed cost and marginal cost",
            "Wall against movie count. The intercept is the per-run fixed cost; the slope is cost per movie.")
    allv = [v for d in sweep.values() for v in d.values()]
    ticks, top = nice_ticks(max(allv))
    ks = sorted({k for d in sweep.values() for k in d})
    axes(s, X0, Y0, W, H, ticks, top, [str(k) for k in ks], "seconds")
    band = W / len(ks)
    xs = {k: X0 + band * (i + 0.5) for i, k in enumerate(ks)}
    fits = []
    for gi, g in enumerate(gs):
        col = C["ord"][min(gi, len(C["ord"]) - 1)]
        pts = [(xs[k], Y0 + H - (sweep[g][k] / top) * H) for k in ks if k in sweep[g]]
        s.path("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts), col, w=2)
        for x, y in pts:
            s.dot(x, y, col, 4)
        kk = [k for k in ks if k in sweep[g]]
        mx = sum(kk) / len(kk); my = sum(sweep[g][k] for k in kk) / len(kk)
        slope = sum((k - mx) * (sweep[g][k] - my) for k in kk) / sum((k - mx) ** 2 for k in kk)
        icpt = my - slope * mx
        fits.append((g, icpt, slope, col))
        # short direct label at the line end; the fitted numbers go in the
        # annotation block, because the full string overflowed the surface.
        s.text(pts[-1][0] + 8, pts[-1][1] + 4, f"{g} GPU", 10, C["ink2"], "start", 600)
    # Upper-left is empty on this chart (every series rises to the right).
    s.text(X0 + 14, Y0 + 16, "fitted", 10, C["muted"], "start")
    for j, (g, icpt, slope, col) in enumerate(fits):
        yy = Y0 + 32 + 14 * j
        s.o.append(f'<rect x="{X0+14:.1f}" y="{yy-8:.1f}" width="9" height="9" rx="2" fill="{col}"/>')
        s.text(X0 + 29, yy, f"{g} GPU  fixed {icpt:.2f}s  +{slope*1000:.0f} ms/movie",
               10, C["ink2"], "start", tabular=True)
    s.text(X0 + W / 2, Y0 + H + 40, "movies", 11, C["ink2"], "middle")
    return s.done()


def chart_timeline(workers, C, gpus):
    """Per-worker Gantt: does concurrent setup stagger the workers or not?"""
    W, H, X0, Y0 = 420, 22 * len(workers) + 10, 74, 84
    s = Svg(560, Y0 + H + 86, C, f"Per-worker timeline at {gpus} GPUs",
            "Each worker's own wall, split at its first and last product.")
    hi = max(w["setup"] + w["produce"] + w["tail"] for w in workers)
    ticks, top = nice_ticks(hi)
    for t in ticks:
        x = X0 + (t / top) * W
        s.line(x, Y0, x, Y0 + H, C["grid"], 1)
        s.text(x, Y0 + H + 16, f"{t:g}", 10, C["muted"], "middle", tabular=True)
    s.line(X0, Y0, X0, Y0 + H, C["axis"], 1)
    bh = min(CAP, 14)
    for i, w in enumerate(workers):
        y = Y0 + 22 * i + (22 - bh) / 2
        s.text(X0 - 10, y + bh - 3, f"w{w['index']}", 11, C["ink2"], "end")
        acc = 0.0
        for key, col in (("setup", C["s1"]), ("produce", C["s2"]), ("tail", C["s3"])):
            v = w[key]
            if v <= 0:
                continue
            x0 = X0 + (acc / top) * W + (GAP if acc > 0 else 0)
            ww = (v / top) * W - (GAP if acc > 0 else 0)
            s.shape(right_round_rect(x0, y, max(ww, 0.6), bh, R if key == "tail" else 0.0), col)
            acc += v
        s.text(X0 + (acc / top) * W + 8, y + bh - 3, f"{acc:.2f}s", 10, C["ink"], "start", 600, tabular=True)
    s.text(X0 + W / 2, Y0 + H + 36, "seconds from worker launch", 11, C["ink2"], "middle")
    s.legend(X0, Y0 + H + 62, [("setup", C["s1"]), ("per-movie work", C["s2"]), ("aggregate tail", C["s3"])])
    return s.done()


def main(argv):
    src = Path(argv[1]) if len(argv) > 1 else Path("status")
    outdir = Path(argv[2]) if len(argv) > 2 else Path("figures")
    outdir.mkdir(parents=True, exist_ok=True)

    scale, sweep, tl = {}, {}, {}
    for f in sorted(src.glob("*.json")):
        tag, g, rep = f.stem.rsplit("_", 2)
        g = int(g[1:])
        s = json.loads(f.read_text())
        ws = s["workers"]
        rec = {
            "total": max(w["wall_seconds"] for w in ws),
            "setup": max((w["phases"]["setup_seconds"] or 0) for w in ws),
            "produce": max((w["phases"]["produce_seconds"] or 0) for w in ws),
            "tail": max((w["phases"]["tail_seconds"] or 0) for w in ws),
            "spread": s["phase_rollup"]["first_product_spread"],
        }
        if tag == "scale":
            scale.setdefault(g, []).append(rec)
            tl.setdefault(g, []).append([
                {"index": w["index"], "setup": w["phases"]["setup_seconds"] or 0,
                 "produce": w["phases"]["produce_seconds"] or 0,
                 "tail": w["phases"]["tail_seconds"] or 0} for w in ws])
        elif tag.startswith("sweep"):
            sweep.setdefault(g, {}).setdefault(int(tag[5:]), []).append(rec["total"])

    agg = {g: {k: st.median([r[k] for r in v]) for k in ("total", "setup", "produce", "tail", "spread")}
           for g, v in scale.items()}
    swg = {g: {k: st.median(v) for k, v in d.items()} for g, d in sweep.items()}
    # representative timeline: the run whose total is the median for that arm
    big = max(agg) if agg else None
    tls = None
    if big is not None and tl.get(big):
        runs = tl[big]
        tot = [max(w["setup"] + w["produce"] + w["tail"] for w in r) for r in runs]
        tls = runs[sorted(range(len(runs)), key=lambda i: tot[i])[len(runs) // 2]]

    figs = {}
    for mode, C in (("light", L), ("dark", D)):
        if agg:
            figs[f"attribution-{mode}.svg"] = chart_attribution(agg, C)
            figs[f"speedup-{mode}.svg"] = chart_speedup(agg, C)
        if swg:
            figs[f"sweep-{mode}.svg"] = chart_sweep(swg, C)
        if tls:
            figs[f"timeline-{mode}.svg"] = chart_timeline(tls, C, big)
    for name, body in figs.items():
        (outdir / name).write_text(body)

    rows = "".join(
        f"<tr><td>{g}</td><td>{d['total']:.2f}</td><td>{agg[min(agg)]['total']/d['total']:.2f}</td>"
        f"<td>{agg[min(agg)]['total']/d['total']/g*100:.0f}%</td><td>{d['setup']:.2f}</td>"
        f"<td>{d['produce']:.2f}</td><td>{d['tail']:.2f}</td><td>{d['spread']:.3f}</td></tr>"
        for g, d in sorted(agg.items()))
    names = [n[:-10] for n in figs if n.endswith("-light.svg")]
    blocks = "".join(
        f'<figure><img class="lt" src="{n}-light.svg" alt="{n}">'
        f'<img class="dk" src="{n}-dark.svg" alt="{n}"></figure>' for n in names)
    (outdir / "index.html").write_text(f"""<!doctype html><meta charset="utf-8">
<title>MotionCorr multi-GPU timing</title>
<style>
 body{{font-family:{FONT};background:#f9f9f7;color:#0b0b0b;margin:0;padding:32px}}
 figure{{margin:0 0 24px;background:{L['surface']};border:1px solid rgba(11,11,11,.10);
   border-radius:10px;padding:8px;display:inline-block}}
 img{{display:block;max-width:100%}} .dk{{display:none}}
 table{{border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;
   background:{L['surface']};border:1px solid rgba(11,11,11,.10);border-radius:10px}}
 th,td{{padding:7px 14px;text-align:right;border-bottom:1px solid {L['grid']}}}
 th:first-child,td:first-child{{text-align:left}} th{{color:{L['ink2']};font-weight:600}}
 caption{{text-align:left;padding:10px 14px;color:{L['ink2']};font-size:12px}}
 @media (prefers-color-scheme:dark){{
   body{{background:#0d0d0d;color:#fff}} .lt{{display:none}} .dk{{display:block}}
   figure,table{{background:{D['surface']};border-color:rgba(255,255,255,.10)}}
   th{{color:{D['ink2']}}} td,th{{border-color:{D['grid']}}} caption{{color:{D['ink2']}}}}}
</style>
<h1 style="font-size:17px">MotionCorr static multi-GPU timing</h1>
{blocks}
<table><caption>Table view — every plotted value, medians across repeats.
first-product spread is the stagger between workers reaching their first product.</caption>
<tr><th>GPUs</th><th>wall s</th><th>speedup</th><th>eff.</th><th>setup s</th>
<th>produce s</th><th>tail s</th><th>spread s</th></tr>{rows}</table>
""")
    print(f"wrote {len(figs)} SVG + index.html to {outdir}")
    for g, d in sorted(agg.items()):
        print(f"  {g} GPU: wall {d['total']:.2f}s setup {d['setup']:.2f} produce {d['produce']:.2f} "
              f"tail {d['tail']:.2f} spread {d['spread']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
