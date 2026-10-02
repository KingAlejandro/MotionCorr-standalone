#!/usr/bin/env python3
"""Charts for the worker-pool ablation.

One time domain per chart. Unprofiled wall clock and profiled intervals are
never drawn together, and no residual is called idle unless it was measured as
a union inside one trace.
"""
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

# Validated categorical slots 1-3 (light surface #fcfcfb): worst all-pairs
# CVD dE 9.2, normal-vision dE 24.0. Aqua is below 3:1 on this surface, so
# every chart that uses it carries direct labels (the relief rule).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2de"
ARMS = ["A0", "A1", "B", "C", "D", "E"]
LABEL = {
    "A0": "A0  PR130 head",
    "A1": "A1  + pool & lease, nothing enabled",
    "B":  "B   + device gain",
    "C":  "C   + whole-frame plans",
    "D":  "D   + patch plan",
    "E":  "E   + reconstruction plan",
}


def style(ax, grid_axis="x"):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK2, length=0, labelsize=9)


def fig(w, h):
    f = plt.figure(figsize=(w, h), facecolor=SURFACE, dpi=160)
    return f


def chart_wall(camp, out):
    """Dot plot, not bars: the x-axis is truncated (the differences are small
    relative to 11 s), and a bar on a truncated axis misrepresents ratios."""
    f = fig(9.6, 4.2)
    ax = f.add_subplot(111)
    style(ax)
    med = [camp["arms"][a]["median_wall_s"] for a in ARMS]
    base = med[0]
    ax.axvline(base, color=ORANGE, lw=1.8, ls=(0, (4, 3)), zorder=2)
    for i, a in enumerate(ARMS):
        walls = camp["arms"][a]["walls"]
        ax.plot([min(walls), max(walls)], [i, i], color="#c9c8c3", lw=2,
                solid_capstyle="round", zorder=3)
        ax.plot(walls, [i] * len(walls), "o", ms=5, color=BLUE, alpha=0.40,
                markeredgewidth=0, zorder=4)
        ax.plot([med[i]], [i], "o", ms=11, color=BLUE, zorder=5,
                markeredgecolor=SURFACE, markeredgewidth=2)
    for i, (a, m) in enumerate(zip(ARMS, med)):
        d = m - base
        txt = f"{m:.3f} s" if i == 0 else f"{m:.3f} s      {d:+.3f} s"
        ax.annotate(txt, (1.005, i), xycoords=("axes fraction", "data"),
                    va="center", fontsize=9.5, color=INK,
                    fontweight="bold" if a == "E" else "normal",
                    annotation_clip=False)
    ax.set_yticks(list(range(len(ARMS))))
    ax.set_yticklabels([LABEL[a] for a in ARMS], fontsize=9.5, color=INK)
    ax.set_ylim(len(ARMS) - 0.4, -0.75)
    ax.set_xlim(9.85, 11.25)
    ax.set_xlabel("complete-process wall clock, 24 movies (s)  —  lower is better",
                  fontsize=9, color=INK2)
    ax.annotate("A0 median", (base, -0.68), xytext=(-5, 0),
                textcoords="offset points", ha="right", va="center",
                fontsize=8.5, color=ORANGE)
    ax.annotate("8 raw walls", (min(camp["arms"]["E"]["walls"]), 5),
                xytext=(-6, -16), textcoords="offset points", ha="right",
                fontsize=8.5, color=INK2)
    f.suptitle("Each mechanism, measured on its own", x=0.012, ha="left",
               fontsize=13, color=INK, fontweight="bold", y=0.985)
    ax.set_title("8 interleaved rounds per arm; large dot is the median, "
                 "line spans the 8 raw walls",
                 loc="left", fontsize=9.5, color=INK2, pad=10)
    f.tight_layout(rect=(0, 0, 0.80, 0.93))
    f.savefig(out, facecolor=SURFACE)
    plt.close(f)


def lower_envelope(series, bins=240):
    """Per-bin minimum of the running total. The floor is a trough, and a
    sawtooth drawn at full scale hides troughs behind its own peaks."""
    if not series:
        return [], []
    t0, t1 = series[0][0], series[-1][0]
    width = (t1 - t0) / bins if t1 > t0 else 1.0
    lo = [None] * bins
    for t, v in series:
        b = min(bins - 1, int((t - t0) / width))
        lo[b] = v if lo[b] is None else min(lo[b], v)
    xs, ys, last = [], [], None
    for b in range(bins):
        if lo[b] is None:
            if last is None:
                continue
            lo[b] = last
        last = lo[b]
        xs.append(t0 + b * width)
        ys.append(lo[b])
    return xs, ys


def chart_vram(series, out):
    f = fig(10.4, 8.4)
    axes = f.subplots(len(ARMS), 2, sharex=True,
                      gridspec_kw={"width_ratios": [2.0, 1.0], "wspace": 0.26})
    for row, a in enumerate(ARMS):
        t = [p[0] for p in series[a]["series"]]
        v = [p[1] for p in series[a]["series"]]
        floor, peak = series[a]["floor_mib"], series[a]["peak_mib"]

        ax = axes[row][0]
        style(ax, grid_axis="y")
        ax.fill_between(t, v, color=BLUE, alpha=0.18, lw=0, zorder=2)
        ax.plot(t, v, color=BLUE, lw=0.9, zorder=3)
        ax.axhline(floor, color=ORANGE, lw=1.4, zorder=4)
        ax.set_ylim(0, 3700)
        ax.yaxis.set_major_locator(MultipleLocator(1500))
        ax.set_title(LABEL[a], loc="left", fontsize=9.5, color=INK,
                     fontweight="bold", pad=4)
        ax.annotate(f"peak {peak:.1f} MiB", (1.0, 1.02), xycoords="axes fraction",
                    va="bottom", ha="right", fontsize=8.5, color=INK2)

        ax = axes[row][1]
        style(ax, grid_axis="y")
        ex, ey = lower_envelope(series[a]["series"])
        ax.fill_between(ex, ey, color=BLUE, alpha=0.25, lw=0, zorder=2)
        ax.plot(ex, ey, color=BLUE, lw=1.4, zorder=3)
        ax.axhline(floor, color=ORANGE, lw=1.6, zorder=4)
        ax.set_ylim(0, 620)
        ax.yaxis.set_major_locator(MultipleLocator(300))
        ax.set_title(f"floor {floor:.1f} MiB", loc="right", fontsize=9,
                     color=ORANGE, fontweight="bold", pad=4)
    axes[0][1].set_title("lower envelope", loc="left", fontsize=8.5, color=INK2, pad=4)
    for col in (0, 1):
        axes[-1][col].set_xlabel("time within the profiled run (s)", fontsize=9, color=INK2)
    axes[len(ARMS) // 2][0].set_ylabel("live device bytes (MiB)", fontsize=9, color=INK2)
    f.suptitle("The peak barely moves. The floor is what rises.", x=0.010,
               ha="left", fontsize=13, color=INK, fontweight="bold", y=0.995)
    f.text(0.010, 0.957, "running total of CUDA allocations minus frees, from each arm's "
           "own --cuda-memory-usage capture; right column is the per-bin minimum",
           fontsize=9.5, color=INK2, ha="left")
    f.tight_layout(rect=(0, 0, 1, 0.94), h_pad=1.6)
    f.savefig(out, facecolor=SURFACE)
    plt.close(f)


def chart_floor(summary, out):
    steps = [
        ("A0 to A1", "pool present, nothing enabled", 0.0),
        ("A1 to B", "device gain  nx*ny*4", 56955920 / 1048576),
        ("B to C", "FFT work area + inverse tile", 113973248 / 1048576),
        ("C to D", "patch R2C plan workspace", 54710784 / 1048576),
        ("D to E", "DW C2R plan workspace", 56986624 / 1048576),
    ]
    order = ["A0", "A1", "B", "C", "D", "E"]
    measured = [summary[order[i + 1]]["floor_mib"] - summary[order[i]]["floor_mib"]
                for i in range(5)]
    f = fig(9.4, 4.0)
    ax = f.add_subplot(111)
    style(ax)
    y = list(range(len(steps)))
    h = 0.30
    gap = 0.02  # 2px-equivalent surface gap between adjacent fills
    ax.barh([i - h / 2 - gap for i in y], measured, height=h, color=BLUE,
            zorder=3, label="measured step in the floor")
    ax.barh([i + h / 2 + gap for i in y], [s[2] for s in steps], height=h,
            color=AQUA, zorder=3, label="size of the buffer the pool reports retaining")
    for i, (m, s) in enumerate(zip(measured, steps)):
        ax.annotate(f"{m:.1f}", (m, i - h / 2 - gap), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK)
        ax.annotate(f"{s[2]:.2f}", (s[2], i + h / 2 + gap), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{s[0]}\n{s[1]}" for s in steps], fontsize=9, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 128)
    ax.set_xlabel("MiB", fontsize=9, color=INK2)
    leg = ax.legend(loc="lower left", bbox_to_anchor=(0.0, -0.40), ncol=2,
                    frameon=False, fontsize=9)
    for t in leg.get_texts():
        t.set_color(INK2)
    f.suptitle("Every step in the floor is one named buffer", x=0.012, ha="left",
               fontsize=13, color=INK, fontweight="bold", y=0.98)
    ax.set_title("profiler allocation events vs the pool's own accounting — independent paths",
                 loc="left", fontsize=9.5, color=INK2, pad=10)
    f.tight_layout(rect=(0, 0, 1, 0.93))
    f.savefig(out, facecolor=SURFACE)
    plt.close(f)


def chart_gpu(series, summary, out):
    f = fig(9.6, 7.8)
    axes = f.subplots(len(ARMS), 1, sharex=True, sharey=True)
    for ax, a in zip(axes, ARMS):
        style(ax, grid_axis="y")
        occ = series[a]["occupancy"]
        x = [i * series[a]["bin_width_s"] for i in range(len(occ))]
        ax.fill_between(x, [o * 100 for o in occ], color=BLUE, alpha=0.9, lw=0, zorder=3)
        ax.set_title(f"{LABEL[a]}        mean {summary[a]['mean_occupancy_pct']:.1f}%"
                     f"    kernel union {summary[a]['kernel_union_s']:.3f} s"
                     f"    copy union {summary[a]['copy_union_s']:.3f} s",
                     loc="left", fontsize=8.8, color=INK, pad=4)
        ax.set_ylim(0, 105)
        ax.yaxis.set_major_locator(MultipleLocator(50))
    axes[-1].set_xlabel("time within the profiled run (s)", fontsize=9, color=INK2)
    axes[len(ARMS) // 2].set_ylabel("% of bin executing a kernel or a copy", fontsize=9, color=INK2)
    f.suptitle("The same GPU work, compressed — not more work per unit time", x=0.010,
               ha="left", fontsize=13, color=INK, fontweight="bold", y=0.995)
    f.text(0.010, 0.950, "900 bins per run; single captures with CUPTI inflation, "
           "so read the direction, not the decimals", fontsize=9.5, color=INK2, ha="left")
    f.tight_layout(rect=(0, 0, 1, 0.94), h_pad=1.5)
    f.savefig(out, facecolor=SURFACE)
    plt.close(f)


def chart_churn(summary, out):
    f = fig(9.4, 3.6)
    ax = f.add_subplot(111)
    style(ax, grid_axis="y")
    x = list(range(len(ARMS)))
    allocs = [summary[a]["allocs"] for a in ARMS]
    frees = [summary[a]["frees"] for a in ARMS]
    w = 0.34
    gap = 0.02
    ax.bar([i - w / 2 - gap for i in x], allocs, width=w, color=BLUE, zorder=3,
           label="cudaMalloc / cuFFT internal allocations")
    ax.bar([i + w / 2 + gap for i in x], frees, width=w, color=ORANGE, zorder=3,
           label="frees")
    for i, (a, fr) in enumerate(zip(allocs, frees)):
        ax.annotate(f"{a:,}", (i - w / 2 - gap, a), xytext=(0, 4),
                    textcoords="offset points", ha="center", fontsize=8.5, color=INK)
        ax.annotate(f"{fr:,}", (i + w / 2 + gap, fr), xytext=(0, 4),
                    textcoords="offset points", ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels(ARMS, fontsize=10, color=INK)
    ax.set_ylim(0, 3600)
    ax.set_ylabel("allocation events,\nwhole 24-movie run", fontsize=9, color=INK2)
    leg = ax.legend(loc="upper right", frameon=False, fontsize=9)
    for t in leg.get_texts():
        t.set_color(INK2)
    f.suptitle("Most of the churn the plan pools remove is cuFFT's own", x=0.012,
               ha="left", fontsize=13, color=INK, fontweight="bold", y=0.98)
    ax.set_title("the pools retain 4 buffers, but each avoided plan build also avoids "
                 "cuFFT's internal allocations",
                 loc="left", fontsize=9.5, color=INK2, pad=10)
    f.tight_layout(rect=(0, 0, 1, 0.93))
    f.savefig(out, facecolor=SURFACE)
    plt.close(f)


def main():
    root = Path(sys.argv[1])
    outdir = root / "charts"
    outdir.mkdir(exist_ok=True)
    summary = json.loads((root / "profile-summary.json").read_text())
    series = json.loads((root / "profile-series.json").read_text())
    for a in ARMS:
        series[a]["floor_mib"] = summary[a]["floor_mib"]
        series[a]["peak_mib"] = summary[a]["peak_mib"]
    camp = json.loads((root / "campaign3-summary.json").read_text())
    chart_wall(camp, outdir / "arms.png")
    chart_vram(series, outdir / "vram-arms.png")
    chart_floor(summary, outdir / "floor-steps.png")
    chart_gpu(series, summary, outdir / "gpu-profile.png")
    chart_churn(summary, outdir / "alloc-churn.png")
    print("wrote", sorted(p.name for p in outdir.glob("*.png")))


if __name__ == "__main__":
    main()
