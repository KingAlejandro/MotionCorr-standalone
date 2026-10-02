#!/usr/bin/env python3
"""Charts for the input-backends evidence, in the house style of PR136.

Self-contained SVG, no plotting dependency, so the charts are reproducible from
the committed data on any machine. One time domain per chart, never mixed: a
chart of unprofiled production wall never carries a profiled interval, and a
chart of device intervals never carries a process wall.

Palette is PR136's own tokens; the four used categorically pass the six checks
of the dataviz validator at the light surface (worst adjacent CVD dE 20.0,
normal-vision 25.3). The green's sub-3:1 contrast is relieved by direct labels
on every mark, which this file always draws.
"""
import html, json, os, sys

INK, MUTED, SEC = "#15202b", "#72808d", "#3c4a57"
GRID, SURFACE, BAND = "#c9d2da", "#ffffff", "#eef1f4"
BLUE, RED, PURPLE, GREEN, AMBER = "#4b7bec", "#eb3b5a", "#8854d0", "#20bf6b", "#f7b731"
FONT = "Inter,Helvetica,Arial,sans-serif"

def esc(t):
    return html.escape(str(t), quote=True)

def txt(x, y, t, size=11, fill=INK, anchor="start", weight="normal"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}">{esc(t)}</text>')

def header(w, title, subs):
    o = [f'<rect width="{w}" height="100%" fill="{SURFACE}"/>',
         txt(16, 32, title, 17, INK, "start", "bold")]
    for i, s in enumerate(subs):
        o.append(txt(16, 54 + 15 * i, s, 10.5, MUTED))
    return o

def footer(w, y, notes):
    o = [f'<line x1="16" y1="{y}" x2="{w-16}" y2="{y}" stroke="{GRID}"/>']
    for i, n in enumerate(notes):
        o.append(txt(16, y + 20 + 16 * i, n, 11, SEC))
    return o

def svg(w, h, title, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}"><title>{esc(title)}</title>' + "".join(body) + "</svg>")


def stacked_stages(path, pairs, stages, colors, title, subs, notes, unit="ms",
                   label_w=250, rowh=30, width=1180):
    """Horizontal stacked bars, two arms per variant.

    pairs = [(variant_label, [(arm_label, {stage: value}), ...])]. The variant
    label is centred on its pair and the pair sits on a tinted band, so a reader
    cannot mistake which bar belongs to which input.
    """
    rows = [(v, a, vals) for v, arms in pairs for a, vals in arms]
    top = 60 + 15 * len(subs)
    h = top + 40 + rowh * len(rows) + 46 + 16 * len(notes)
    plot_x, plot_w = label_w, width - label_w - 150
    vmax = max(sum(r[2].get(s, 0) for s in stages) for r in rows) or 1.0
    b = header(width, title, subs)
    # axis
    ticks = 6
    for i in range(ticks + 1):
        v = vmax * i / ticks
        x = plot_x + plot_w * i / ticks
        b.append(f'<line x1="{x:.1f}" y1="{top+18}" x2="{x:.1f}" y2="{top+24+rowh*len(rows)}" '
                 f'stroke="{GRID}" stroke-width="0.5" stroke-dasharray="2 4" opacity="0.6"/>')
        b.append(txt(x, top + 12, f"{v:.0f}", 10.5, MUTED, "middle"))
    b.append(txt(plot_x + plot_w / 2, top - 4, unit + " (lower is better)", 10.5, MUTED, "middle"))
    # alternating band per variant, and the variant label centred on its pair
    i = 0
    for pi, (vlabel, arms) in enumerate(pairs):
        y0 = top + 30 + rowh * i - 14
        hgt = rowh * len(arms)
        if pi % 2 == 0:
            b.append(f'<rect x="16" y="{y0:.1f}" width="{width-32}" height="{hgt:.1f}" fill="{BAND}"/>')
        b.append(txt(label_w - 100, y0 + hgt / 2 + 4, vlabel, 12.5, INK, "end", "bold"))
        i += len(arms)
    # legend
    lx = plot_x
    for s in stages:
        b.append(f'<rect x="{lx}" y="{top+24+rowh*len(rows)+14}" width="10" height="10" rx="2" fill="{colors[s]}"/>')
        b.append(txt(lx + 15, top + 24 + rowh * len(rows) + 23, s, 11, SEC))
        lx += 20 + 7.1 * len(s)
    for i, (label, sub, vals) in enumerate(rows):
        y = top + 30 + rowh * i
        b.append(txt(label_w - 12, y + 4, sub, 11, SEC, "end"))
        x = plot_x
        total = 0.0
        for s in stages:
            v = vals.get(s, 0.0)
            if v <= 0:
                continue
            bw = plot_w * v / vmax
            # 2px surface gap between segments
            b.append(f'<rect x="{x:.1f}" y="{y-9}" width="{max(bw-2,0.8):.1f}" height="18" '
                     f'rx="3" fill="{colors[s]}"/>')
            if bw > 40:
                b.append(txt(x + bw / 2 - 1, y + 4, f"{v:.0f}", 10, "#ffffff", "middle", "bold"))
            x += bw
            total += v
        b.append(txt(x + 10, y + 4, f"{total:.0f} {unit}", 12.5, INK, "start", "bold"))
    b += footer(width, top + 24 + rowh * len(rows) + 40, notes)
    open(path, "w").write(svg(width, h, title, b))
    return path


def dot_rows(path, rows, title, subs, notes, unit="s", label_w=250, rowh=48,
             width=1180, highlight=None, lower_better=True):
    """PR136's arm chart: dots are observations, bar is min-max, rule is median."""
    top = 60 + 15 * len(subs)
    h = top + 40 + rowh * len(rows) + 46 + 16 * len(notes)
    plot_x, plot_w = label_w, width - label_w - 260
    allv = [v for r in rows for v in r[2]]
    lo, hi = min(allv), max(allv)
    span = (hi - lo) or 1.0
    lo, hi = lo - span * 0.08, hi + span * 0.08
    def X(v):
        return plot_x + plot_w * (v - lo) / (hi - lo)
    b = header(width, title, subs)
    for i in range(7):
        v = lo + (hi - lo) * i / 6
        b.append(f'<line x1="{X(v):.1f}" y1="{top+18}" x2="{X(v):.1f}" y2="{top+24+rowh*len(rows)}" '
                 f'stroke="{GRID}" stroke-width="0.5" stroke-dasharray="2 4" opacity="0.6"/>')
        b.append(txt(X(v), top + 12, f"{v:.2f}", 10.5, MUTED, "middle"))
    b.append(txt(plot_x + plot_w / 2, top - 4,
                 f"{unit} ({'lower' if lower_better else 'higher'} is better)", 10.5, MUTED, "middle"))
    for i, (label, sub, vals, note) in enumerate(rows):
        y = top + 30 + rowh * i
        sv = sorted(vals)
        med = sv[len(sv) // 2] if len(sv) % 2 else (sv[len(sv)//2-1] + sv[len(sv)//2]) / 2
        isb = highlight is not None and label in highlight
        b.append(txt(label_w - 12, y + 2, label, 12.5, INK, "end", "bold" if isb else "normal"))
        if sub:
            b.append(txt(label_w - 12, y + 16, sub, 9.5, MUTED, "end"))
        b.append(f'<line x1="{X(min(sv)):.1f}" y1="{y:.1f}" x2="{X(max(sv)):.1f}" y2="{y:.1f}" '
                 f'stroke="{GRID}" stroke-width="2"/>')
        for v in vals:
            b.append(f'<circle cx="{X(v):.1f}" cy="{y:.1f}" r="3.2" fill="{BLUE}" opacity="0.55"/>')
        b.append(f'<line x1="{X(med):.1f}" y1="{y-13:.1f}" x2="{X(med):.1f}" y2="{y+13:.1f}" '
                 f'stroke="{GREEN if isb else INK}" stroke-width="3"/>')
        b.append(txt(X(max(sv)) + 12, y + 4, f"{med:.3f} {unit}", 13, INK, "start", "bold"))
        if note:
            b.append(txt(X(max(sv)) + 12, y + 18, note, 10, SEC))
        if len(sv) == 1:
            b.append(txt(X(sv[0]), y - 17, "single observation", 9, MUTED, "middle"))
    b += footer(width, top + 24 + rowh * len(rows) + 20, notes)
    open(path, "w").write(svg(width, h, title, b))
    return path


def grouped_bars(path, groups, series, colors, title, subs, notes, unit="MiB",
                 width=1180, label_w=250, rowh=52):
    """Two bars per row (main, branch) with the delta called out."""
    top = 60 + 15 * len(subs)
    h = top + 40 + rowh * len(groups) + 46 + 16 * len(notes)
    plot_x, plot_w = label_w, width - label_w - 230
    vmax = max(v for _, vals in groups for v in vals.values()) or 1.0
    b = header(width, title, subs)
    for i in range(7):
        v = vmax * i / 6
        b.append(f'<line x1="{plot_x+plot_w*i/6:.1f}" y1="{top+18}" x2="{plot_x+plot_w*i/6:.1f}" '
                 f'y2="{top+24+rowh*len(groups)}" stroke="{GRID}" stroke-width="0.5" '
                 f'stroke-dasharray="2 4" opacity="0.6"/>')
        b.append(txt(plot_x + plot_w * i / 6, top + 12, f"{v:.0f}", 10.5, MUTED, "middle"))
    b.append(txt(plot_x + plot_w / 2, top - 4, unit + " (lower is better)", 10.5, MUTED, "middle"))
    lx = plot_x
    for s in series:
        b.append(f'<rect x="{lx}" y="{top+24+rowh*len(groups)+14}" width="10" height="10" rx="2" fill="{colors[s]}"/>')
        b.append(txt(lx + 15, top + 24 + rowh * len(groups) + 23, s, 11, SEC))
        lx += 20 + 7.1 * len(s)
    for i, (label, vals) in enumerate(groups):
        y = top + 26 + rowh * i
        b.append(txt(label_w - 12, y + 12, label, 12.5, INK, "end"))
        for j, s in enumerate(series):
            v = vals.get(s)
            if v is None:
                continue
            bw = plot_w * v / vmax
            yy = y + j * 13
            b.append(f'<rect x="{plot_x}" y="{yy}" width="{max(bw,1):.1f}" height="11" rx="3" fill="{colors[s]}"/>')
            b.append(txt(plot_x + bw + 8, yy + 9, f"{v:,.0f}", 11, INK))
        if len(series) == 2 and all(s in vals for s in series):
            a, c = vals[series[0]], vals[series[1]]
            if a:
                b.append(txt(width - 24, y + 16, f"{(c-a)/a*100:+.0f}%", 13, INK, "end", "bold"))
    b += footer(width, top + 24 + rowh * len(groups) + 40, notes)
    open(path, "w").write(svg(width, h, title, b))
    return path
