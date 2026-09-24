#!/usr/bin/env python3
"""
MotionCorr Agentic Workflow Diagram Generator
Renders a publication-quality 16:9 widescreen diagram for presentation slides.
"""

import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.lines as mlines


def render_workflow_diagram(out_png: Path, out_svg: Path = None):
    # 16:9 Aspect Ratio (16 x 9 inches at 200 dpi = 3200 x 1800 px)
    fig, ax = plt.subplots(figsize=(16, 9), dpi=200)
    fig.patch.set_facecolor('#0f172a')  # Dark Slate 900
    ax.set_facecolor('#0f172a')
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis('off')

    # Color Palette (Tailwind / Slate / Cyan / Emerald / Indigo / Amber)
    bg_box = '#1e293b'       # Slate 800
    card_bg = '#334155'      # Slate 700
    border_blue = '#38bdf8'  # Sky 400
    border_indigo = '#818cf8'# Indigo 400
    border_emerald = '#34d399'# Emerald 400
    border_amber = '#fbbf24' # Amber 400
    border_rose = '#f43f5e'  # Rose 500
    text_white = '#f8fafc'
    text_muted = '#94a3b8'
    text_cyan = '#38bdf8'
    text_emerald = '#34d399'
    text_amber = '#fbbf24'

    # --- Header Banner ---
    title_box = patches.FancyBboxPatch((0.6, 8.0), 14.8, 0.75, boxstyle="round,pad=0.08,rounding_size=0.15",
                                      facecolor='#1e293b', edgecolor='#38bdf8', linewidth=1.5)
    ax.add_patch(title_box)
    ax.text(8.0, 8.48, "MotionCorr: Multi-Agent Engineering Architecture & Lifecycle",
            ha='center', va='center', fontsize=17, fontweight='bold', color=text_white)
    ax.text(8.0, 8.18, "Autonomous Dialectic Specification  •  Dual Verification Gates  •  Bit-Exact Scientific Parity",
            ha='center', va='center', fontsize=11, color=text_cyan)

    # 5 Phase Columns Layout parameters
    col_w = 2.75
    col_gap = 0.28
    left_start = 0.6
    phase_y = 7.7
    col_h = 5.9

    phases = [
        ("Phase 1: Dialectic Loop", "Pre-Code Specification", border_blue, [
            ("GitHub Issue / Task", "Parser extracts scope & acceptance criteria", '#475569', text_white),
            ("Architecture Agent", "Generator: drafts ADR & math formulation", '#1e1b4b', border_indigo),
            ("Spec Conformance Agent", "Critic: audits scope & forward completeness", '#1e1b4b', border_indigo),
            ("refine_specification.py", "Iterative dialectic loop (Rounds 1-3)", '#0f172a', text_amber),
            ("Certified Specification", "Certified ADR & strict file whitelist", '#064e3b', border_emerald)
        ]),
        ("Phase 2: Implementation", "Scope-Bounded Coding", border_indigo, [
            ("Implementation Agent", "Executes changes strictly within whitelist", '#1e1b4b', border_indigo),
            ("C++17 & CUDA Kernels", "Modular MotionCorr modernization", '#475569', text_white),
            ("SIMD FFT Alignment", "Aligned FFTW plan reuse & memory layout", '#475569', text_white),
            ("Unit Test Fixtures", "Deterministic multi-thread test suites", '#475569', text_white),
            ("Scope Isolation", "Zero collateral side effects allowed", '#064e3b', border_emerald)
        ]),
        ("Phase 3: Verification", "Dual Multi-Agent Gates", border_amber, [
            ("Review Agent", "Audits thread safety, OpenMP & allocations", '#1e1b4b', border_indigo),
            ("Spec Compliance Agent", "Reverse scope check & completeness audit", '#1e1b4b', border_indigo),
            ("Testing Agent", "CMake build, Sanitizers & out-of-source test", '#1e1b4b', border_indigo),
            ("Exact Parity Gate", "Image RMSE = 0.0  •  Shift Δ = 0.0 px", '#064e3b', border_emerald),
            ("Dual Gate Verdict", "READY_TO_MERGE  &  SPEC_CONFORMANCE_PASSED", '#0f172a', text_amber)
        ]),
        ("Phase 4: Compliance", "Hygiene & Attribution", border_emerald, [
            ("License Compliance", "GPL-2.0 & OSI open-source verification", '#1e1b4b', border_indigo),
            ("Hygiene & Cleanup", "Safely purges review dumps & caches", '#1e1b4b', border_indigo),
            ("ai-git-commit Skill", "Automated conventional commits & trailers", '#0f172a', text_cyan),
            ("Git Blame Attribution", "Co-author provenance & issue tracking", '#475569', text_white),
            ("Clean Git Branch", "Merged into branch (dev_milan)", '#064e3b', border_emerald)
        ]),
        ("Phase 5: Telemetry", "Benchmarking & Plots", border_blue, [
            ("CPU Profiling Suite", "Stage timing breakdown & peak RSS memory", '#475569', text_white),
            ("Visualization Agent", "Autonomous generator for plotting tools", '#1e1b4b', border_indigo),
            ("Standalone Plotters", "Decoupled scripts in tools/plots/", '#475569', text_white),
            ("Speedup & Drift Charts", "10-thread speedup: 4.1x (60s -> 14.8s)", '#064e3b', border_emerald),
            ("Timestamped Deliverables", "SVG & PNG exports in plots/YYYYMMDD/", '#0f172a', text_cyan)
        ])
    ]

    for idx, (p_title, p_sub, p_color, cards) in enumerate(phases):
        x = left_start + idx * (col_w + col_gap)
        
        # Column Outer Box
        outer_box = patches.FancyBboxPatch((x, phase_y - col_h), col_w, col_h,
                                           boxstyle="round,pad=0.06,rounding_size=0.12",
                                           facecolor=bg_box, edgecolor=p_color, linewidth=1.5)
        ax.add_patch(outer_box)
        
        # Column Header Pill
        header_pill = patches.FancyBboxPatch((x + 0.1, phase_y - 0.7), col_w - 0.2, 0.6,
                                             boxstyle="round,pad=0.04,rounding_size=0.08",
                                             facecolor='#0f172a', edgecolor=p_color, linewidth=1.0)
        ax.add_patch(header_pill)
        ax.text(x + col_w / 2, phase_y - 0.32, p_title, ha='center', va='center',
                fontsize=10.5, fontweight='bold', color=text_white)
        ax.text(x + col_w / 2, phase_y - 0.52, p_sub, ha='center', va='center',
                fontsize=8.5, color=text_cyan)

        # Draw Cards Inside Column
        card_y_start = phase_y - 0.85
        card_h = 0.88
        card_spacing = 0.98

        for c_idx, (c_header, c_desc, c_bg, c_border) in enumerate(cards):
            cy = card_y_start - c_idx * card_spacing - card_h
            
            c_patch = patches.FancyBboxPatch((x + 0.15, cy), col_w - 0.3, card_h,
                                             boxstyle="round,pad=0.04,rounding_size=0.08",
                                             facecolor=c_bg, edgecolor=c_border, linewidth=1.0)
            ax.add_patch(c_patch)
            
            # Card text
            ax.text(x + 0.25, cy + card_h - 0.25, c_header, ha='left', va='center',
                    fontsize=9.5, fontweight='bold', color=text_white)
            ax.text(x + 0.25, cy + 0.25, c_desc, ha='left', va='center',
                    fontsize=7.8, color=text_muted if c_border != border_emerald else text_emerald)

        # Arrow between columns
        if idx < len(phases) - 1:
            arrow_x = x + col_w + 0.05
            arrow_y = phase_y - col_h / 2
            ax.annotate('', xy=(arrow_x + col_gap - 0.1, arrow_y), xytext=(arrow_x, arrow_y),
                        arrowprops=dict(arrowstyle="->", color=text_cyan, lw=2.5, mutation_scale=15))

    # --- Bottom Meta-Governance Banner ---
    gov_box = patches.FancyBboxPatch((0.6, 0.4), 14.8, 0.75, boxstyle="round,pad=0.06,rounding_size=0.12",
                                    facecolor='#1e293b', edgecolor='#a855f7', linewidth=1.5)
    ax.add_patch(gov_box)
    ax.text(1.0, 0.78, "Ecosystem Governance & Quality Guarantee:", fontsize=10.5, fontweight='bold', color='#c084fc')
    ax.text(1.0, 0.55, "• Agent Meta-Auditor monitors ecosystem schemas, prompts & CLIs\n• Zero-tolerance Parity Gate: Image RMSE == 0.0 & Drift Δ == 0.0 px against RELION 5.1",
            fontsize=8.5, color=text_white)
    
    # Key Stats Badges on Right of Bottom Banner
    badge1 = patches.FancyBboxPatch((9.6, 0.5), 2.7, 0.55, boxstyle="round,pad=0.04,rounding_size=0.06",
                                    facecolor='#064e3b', edgecolor=border_emerald, linewidth=1.0)
    ax.add_patch(badge1)
    ax.text(10.95, 0.78, "Bit-Exact RELION Parity", ha='center', va='center', fontsize=8.5, fontweight='bold', color=text_white)
    ax.text(10.95, 0.60, "Exact Gate RMSE = 0.0", ha='center', va='center', fontsize=7.5, color=text_emerald)

    badge2 = patches.FancyBboxPatch((12.5, 0.5), 2.7, 0.55, boxstyle="round,pad=0.04,rounding_size=0.06",
                                    facecolor='#064e3b', edgecolor=border_emerald, linewidth=1.0)
    ax.add_patch(badge2)
    ax.text(13.85, 0.78, "4.1x Measured Speedup", ha='center', va='center', fontsize=8.5, fontweight='bold', color=text_white)
    ax.text(13.85, 0.60, "10 Threads (60s -> 14.8s)", ha='center', va='center', fontsize=7.5, color=text_emerald)

    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight', dpi=200)
    print(f"[Workflow Diagram] Generated PNG -> {out_png}")

    if out_svg:
        plt.savefig(out_svg, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
        print(f"[Workflow Diagram] Generated SVG -> {out_svg}")

    plt.close()


def main():
    parser = argparse.ArgumentParser(description="MotionCorr Agentic Workflow Diagram Generator (16:9)")
    parser.add_argument("--out-png", type=Path, default=Path("presentation/plots/agentic_workflow_diagram.png"),
                        help="Output path for PNG diagram")
    parser.add_argument("--out-svg", type=Path, default=Path("presentation/plots/agentic_workflow_diagram.svg"),
                        help="Output path for SVG diagram")
    args = parser.parse_args()

    render_workflow_diagram(args.out_png, args.out_svg)


if __name__ == "__main__":
    main()
