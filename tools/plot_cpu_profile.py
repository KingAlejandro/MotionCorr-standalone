#!/usr/bin/env python3
"""Generate high-quality profiling charts for MotionCorr CPU & memory baseline."""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

def generate_plots(json_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(json_path) as f:
        data = json.load(f)

    cases = data["cases"]
    
    # -------------------------------------------------------------
    # FIGURE 1: Stage Runtime Breakdown Across Configurations
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6), sharey=True)
    plt.subplots_adjust(wspace=0.15)

    categories = [
        ("dose weighting", "#e74c3c", "Dose Weighting"),
        ("global iFFT", "#e67e22", "Global Inverse FFT"),
        ("global FFT", "#f1c40f", "Global Forward FFT"),
        ("prepare patch", "#3498db", "Prepare Patch (Clip & FFT)"),
        ("real space interpolation", "#9b59b6", "Real Space Interpolation"),
        ("read movie", "#1abc9c", "Read Movie (Disk I/O)"),
        ("patch alignment", "#34495e", "Patch Alignment"),
        ("global alignment", "#7f8c8d", "Global Alignment"),
        ("other", "#bdc3c7", "Other Preprocessing"),
    ]

    def get_stage_breakdown(case_id):
        cdata = cases[case_id]
        total = cdata["wall_time_stats"]["mean"]
        stats = cdata["stage_time_stats"]
        breakdown = {}
        accounted = 0.0
        for tag, color, label in categories:
            if tag == "other":
                continue
            val = stats.get(tag, {}).get("mean", 0.0)
            breakdown[tag] = val
            accounted += val
        breakdown["other"] = max(0.0, total - accounted)
        return total, breakdown

    case_order = ["patch5x5_j1", "patch5x5_j4", "global_j1", "global_j4"]
    case_labels = [
        "5x5 Patch\n(1 thread)",
        "5x5 Patch\n(4 threads)",
        "Global-only\n(1 thread)",
        "Global-only\n(4 threads)"
    ]

    # Subplot 1: Absolute Wall Time (Seconds)
    y_pos = np.arange(len(case_order))
    bar_height = 0.55

    for idx, cid in enumerate(case_order):
        total, bd = get_stage_breakdown(cid)
        left = 0.0
        for tag, color, label in categories:
            val = bd.get(tag, 0.0)
            if val > 0.01:
                ax1.barh(y_pos[idx], val, left=left, height=bar_height, color=color, edgecolor="white", linewidth=0.7)
                if val >= 2.5:
                    pct = val / total * 100
                    ax1.text(left + val / 2, y_pos[idx], f"{val:.1f}s\n({pct:.0f}%)",
                             va="center", ha="center", fontsize=8, color="white" if tag != "global FFT" else "black", fontweight="bold")
                left += val
        ax1.text(total + 0.8, y_pos[idx], f"Total: {total:.1f}s", va="center", ha="left", fontsize=9, fontweight="bold")

    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(case_labels, fontsize=10, fontweight="bold")
    ax1.invert_yaxis()
    ax1.set_xlabel("Wall Clock Time (Seconds)", fontsize=11, fontweight="bold")
    ax1.set_title("Absolute Stage Runtime Breakdown", fontsize=12, fontweight="bold")
    ax1.grid(axis="x", linestyle="--", alpha=0.5)
    ax1.set_xlim(0, 75)

    # Subplot 2: Relative Normalized Percentage (100%)
    for idx, cid in enumerate(case_order):
        total, bd = get_stage_breakdown(cid)
        left = 0.0
        for tag, color, label in categories:
            val = bd.get(tag, 0.0)
            pct = (val / total * 100) if total > 0 else 0
            if pct > 0.5:
                ax2.barh(y_pos[idx], pct, left=left, height=bar_height, color=color, edgecolor="white", linewidth=0.7)
                if pct >= 5.0:
                    ax2.text(left + pct / 2, y_pos[idx], f"{pct:.0f}%",
                             va="center", ha="center", fontsize=8, color="white" if tag != "global FFT" else "black", fontweight="bold")
                left += pct

    ax2.set_xlabel("Percentage of Total Runtime (%)", fontsize=11, fontweight="bold")
    ax2.set_title("Relative Stage Percentage", fontsize=12, fontweight="bold")
    ax2.grid(axis="x", linestyle="--", alpha=0.5)
    ax2.set_xlim(0, 100)

    # Custom unified legend
    handles = [plt.Rectangle((0, 0), 1, 1, color=col) for _, col, _ in categories]
    labels = [lbl for _, _, lbl in categories]
    fig.legend(handles, labels, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.08), fontsize=9, frameon=True)

    fig.suptitle("MotionCorr CPU Time Profiling Baseline (4-gpu-vm, AMD EPYC 7452)", fontsize=14, fontweight="bold", y=0.98)
    fig.savefig(output_dir / "stage_breakdown.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[+] Wrote {output_dir / 'stage_breakdown.png'}")

    # -------------------------------------------------------------
    # FIGURE 2: Multi-Threading Scaling & Patch Alignment Overhead
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Panel A: Scaling & Efficiency
    configs = ["Global Alignment", "5x5 Patch Alignment"]
    t1_vals = [cases["global_j1"]["wall_time_stats"]["mean"], cases["patch5x5_j1"]["wall_time_stats"]["mean"]]
    t4_vals = [cases["global_j4"]["wall_time_stats"]["mean"], cases["patch5x5_j4"]["wall_time_stats"]["mean"]]
    speedup_vals = [t1 / t4 for t1, t4 in zip(t1_vals, t4_vals)]
    efficiency_vals = [sp / 4 * 100 for sp in speedup_vals]

    x = np.arange(len(configs))
    w = 0.35

    rects1 = ax1.bar(x - w/2, t1_vals, w, label="1 Thread (-j 1)", color="#3498db")
    rects2 = ax1.bar(x + w/2, t4_vals, w, label="4 Threads (-j 4)", color="#2ecc71")

    for i in range(len(configs)):
        ax1.text(x[i] - w/2, t1_vals[i] + 1.0, f"{t1_vals[i]:.1f}s", ha="center", fontsize=9, fontweight="bold")
        ax1.text(x[i] + w/2, t4_vals[i] + 1.0, f"{t4_vals[i]:.1f}s\n({speedup_vals[i]:.2f}x)", ha="center", fontsize=9, fontweight="bold")

    ax1.set_ylabel("Wall Clock Time (Seconds)", fontsize=11, fontweight="bold")
    ax1.set_title("Multi-Threading Speedup (-j 1 vs -j 4)", fontsize=12, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(configs, fontsize=10, fontweight="bold")
    ax1.set_ylim(0, 80)
    ax1.legend(loc="upper right", frameon=True)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)

    # Annotate efficiency
    ax1.text(x[0] + w/2, 45, f"Speedup: {speedup_vals[0]:.2f}x\nEfficiency: {efficiency_vals[0]:.1f}%",
             ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#ecf0f1", ec="#bdc3c7"))
    ax1.text(x[1] + w/2, 55, f"Speedup: {speedup_vals[1]:.2f}x\nEfficiency: {efficiency_vals[1]:.1f}%",
             ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#ecf0f1", ec="#bdc3c7"))

    # Panel B: Patch Overhead Breakdown (Single Thread)
    p_total = cases["patch5x5_j1"]["wall_time_stats"]["mean"]
    g_total = cases["global_j1"]["wall_time_stats"]["mean"]
    overhead_total = p_total - g_total

    stages_patch = cases["patch5x5_j1"]["stage_time_stats"]
    stages_global = cases["global_j1"]["stage_time_stats"]

    prep_patch = stages_patch.get("prepare patch", {}).get("mean", 0.0)
    interp_diff = stages_patch.get("real space interpolation", {}).get("mean", 0.0) - stages_global.get("real space interpolation", {}).get("mean", 0.0)
    align_diff = stages_patch.get("patch alignment", {}).get("mean", 0.0)
    other_diff = max(0.0, overhead_total - (prep_patch + interp_diff + align_diff))

    overhead_items = [
        ("Prepare Patch\n(Window & FFT)", prep_patch, "#3498db"),
        ("Real-Space\nInterpolation", interp_diff, "#9b59b6"),
        ("Patch Alignment\n(CCF & Splines)", align_diff, "#34495e"),
        ("FFT/DW\nVariance", other_diff, "#bdc3c7"),
    ]

    labels = [it[0] for it in overhead_items]
    vals = [it[1] for it in overhead_items]
    colors = [it[2] for it in overhead_items]

    bars = ax2.bar(labels, vals, color=colors, width=0.55, edgecolor="black", linewidth=0.5)
    for bar in bars:
        h = bar.get_height()
        pct = h / overhead_total * 100
        ax2.text(bar.get_x() + bar.get_width()/2, h + 0.15, f"{h:.2f}s\n({pct:.0f}%)", ha="center", fontsize=9, fontweight="bold")

    ax2.set_ylabel("Overhead Time (Seconds)", fontsize=11, fontweight="bold")
    ax2.set_title(f"5x5 Patch Alignment Overhead (+{overhead_total:.2f}s total, +22.2%)", fontsize=12, fontweight="bold")
    ax2.set_ylim(0, 8.5)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)

    fig.suptitle("Scaling Efficiency & Algorithmic Overhead (4-gpu-vm)", fontsize=14, fontweight="bold", y=1.02)
    fig.savefig(output_dir / "scaling_and_overhead.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[+] Wrote {output_dir / 'scaling_and_overhead.png'}")

    # -------------------------------------------------------------
    # FIGURE 3: Memory Profile & Peak RSS Allocation Hotspots
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Panel A: Measured Peak RSS
    rss_cases = ["global_j1", "global_j4", "patch5x5_j1", "patch5x5_j4"]
    rss_labels = ["Global (j=1)", "Global (j=4)", "5x5 Patch (j=1)", "5x5 Patch (j=4)"]
    rss_vals = [cases[c]["peak_rss_stats_gib"]["mean"] for c in rss_cases]

    bars = ax1.bar(rss_labels, rss_vals, color=["#2980b9", "#27ae60", "#2980b9", "#27ae60"], width=0.5)
    for bar in bars:
        h = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2, h + 0.05, f"{h:.2f} GiB", ha="center", fontsize=9, fontweight="bold")

    ax1.set_ylabel("Peak Resident Set Size (GiB)", fontsize=11, fontweight="bold")
    ax1.set_title("Measured Peak RSS Across Configurations", fontsize=12, fontweight="bold")
    ax1.set_ylim(0, 3.5)
    ax1.grid(axis="y", linestyle="--", alpha=0.5)
    ax1.axhline(2.73, color="#e74c3c", linestyle=":", label="Single-Thread Baseline (2.73 GiB)")
    ax1.legend(loc="upper left")

    # Panel B: Memory Component Attribution
    mem_components = [
        ("Real Frames Stack\n(Iframes, 24x 57MB)", 1.368, "#3498db"),
        ("Fourier Frames Stack\n(Fframes, 24x 57MB)", 1.369, "#e67e22"),
        ("Gain Ref & Worker\nScratch (Single-thread)", 0.057 + 0.010, "#95a5a6"),
        ("OpenMP Thread\nPrivate Buffers (j=4)", 0.210, "#2ecc71"),
    ]

    labels = [m[0] for m in mem_components]
    sizes = [m[1] for m in mem_components]
    colors = [m[2] for m in mem_components]

    # Stacked bar showing accumulation to Peak RSS
    bottom = 0.0
    for i in range(3):
        ax2.bar("Single-Thread (j=1)\nPeak: 2.73 GiB", sizes[i], bottom=bottom, color=colors[i], width=0.45, edgecolor="white")
        ax2.text(0, bottom + sizes[i]/2, f"{sizes[i]:.2f} GiB", ha="center", va="center", color="white" if i < 2 else "black", fontweight="bold", fontsize=9)
        bottom += sizes[i]

    bottom = 0.0
    for i in range(4):
        ax2.bar("Multi-Thread (j=4)\nPeak: 2.95 GiB", sizes[i], bottom=bottom, color=colors[i], width=0.45, edgecolor="white")
        ax2.text(1, bottom + sizes[i]/2, f"{sizes[i]:.2f} GiB", ha="center", va="center", color="white" if i < 2 else "black", fontweight="bold", fontsize=9)
        bottom += sizes[i]

    ax2.set_ylabel("Resident Memory Allocation (GiB)", fontsize=11, fontweight="bold")
    ax2.set_title("Peak Memory Component Attribution", fontsize=12, fontweight="bold")
    ax2.set_ylim(0, 3.5)
    ax2.grid(axis="y", linestyle="--", alpha=0.5)

    # Custom legend
    handles = [plt.Rectangle((0, 0), 1, 1, color=col) for col in colors]
    ax2.legend(handles, labels, loc="upper left", fontsize=8, frameon=True)

    fig.suptitle("Peak Memory (RSS) Profile & Allocation Breakdown", fontsize=14, fontweight="bold", y=1.02)
    fig.savefig(output_dir / "memory_profile.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[+] Wrote {output_dir / 'memory_profile.png'}")

if __name__ == "__main__":
    json_file = Path("docs/cpu_profiling_results_4gpus.json")
    out_dir = Path("docs/figures")
    generate_plots(json_file, out_dir)
