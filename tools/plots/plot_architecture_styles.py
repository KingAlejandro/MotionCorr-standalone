#!/usr/bin/env python3
"""
Multi-Style Architecture Diagram Generator (16:9 Presentation Ready)
Styles: Art Deco, Art Nouveau, Minimalist, Bauhaus
(Avoids purple and neon colors)
"""

import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.lines as mlines
from matplotlib.path import Path as MPath


PHASES_DATA = [
    ("Phase 1: Dialectic Loop", "Pre-Code Specification", [
        ("GitHub Task", "Parser extracts scope & criteria"),
        ("Architecture Agent", "Generator: drafts ADR & math"),
        ("Spec Conformance", "Critic: audits scope & forward gates"),
        ("refine_specification.py", "Iterative dialectic refinement"),
        ("Certified Spec", "ADR & strict file whitelist")
    ]),
    ("Phase 2: Implementation", "Scope-Bounded Coding", [
        ("Implementation Agent", "Executes whitelisted code"),
        ("C++17 & CUDA Kernels", "Modular MotionCorr engine"),
        ("SIMD FFT Alignment", "Aligned FFTW plan reuse"),
        ("Unit Test Fixtures", "Deterministic thread tests"),
        ("Scope Isolation", "Zero collateral side effects")
    ]),
    ("Phase 3: Verification", "Dual Multi-Agent Gates", [
        ("Review Agent", "Audits thread safety & memory"),
        ("Spec Compliance", "Reverse scope check & completeness"),
        ("Testing Agent", "CMake build & out-of-source test"),
        ("Exact Parity Gate", "Image RMSE=0.0 • Drift Δ=0.0px"),
        ("Dual Gate Verdict", "READY_TO_MERGE & PASS")
    ]),
    ("Phase 4: Compliance", "Hygiene & Attribution", [
        ("License Compliance", "GPL-2.0 & OSI open-source audit"),
        ("Hygiene & Cleanup", "Purges review dumps & caches"),
        ("ai-git-commit", "Automated conventional commits"),
        ("Git Blame Trace", "Co-author & issue provenance"),
        ("Clean Branch", "Merged cleanly into dev_milan")
    ]),
    ("Phase 5: Telemetry", "Benchmarking & Plots", [
        ("CPU Profiling Suite", "Stage timing & RSS memory"),
        ("Visualization Agent", "Autonomous plot tool generator"),
        ("Standalone Plotters", "Decoupled tools/plots/ scripts"),
        ("Speedup Charts", "4.1x Speedup (60s -> 14.8s)"),
        ("Plot Deliverables", "SVG & PNG in plots/YYYYMMDD/")
    ])
]


def render_art_deco(out_png: Path, out_svg: Path = None):
    """Art Deco Style: Deep Charcoal & Matte Gold, Geometric stepped accents, elegant serif tones."""
    fig, ax = plt.subplots(figsize=(16, 9), dpi=200)
    bg_color = "#14181f"      # Deep matte charcoal
    gold_main = "#d4af37"     # Rich Art Deco Gold
    gold_light = "#f3e5ab"    # Champagne gold
    gold_dark = "#997a15"     # Antique bronze gold
    card_bg = "#1e2430"       # Dark steel charcoal
    accent_teal = "#2a6f68"   # Deco geometric teal
    text_cream = "#fdfbf7"    # Warm cream

    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")

    # Double Outer Deco Border with Corner Geometry
    ax.add_patch(patches.Rectangle((0.3, 0.3), 15.4, 8.4, fill=False, edgecolor=gold_dark, linewidth=1.2))
    ax.add_patch(patches.Rectangle((0.4, 0.4), 15.2, 8.2, fill=False, edgecolor=gold_main, linewidth=2.0))
    
    # Corner Deco Chevrons
    for cx, cy, sx, sy in [(0.4, 0.4, 1, 1), (15.6, 0.4, -1, 1), (0.4, 8.6, 1, -1), (15.6, 8.6, -1, -1)]:
        ax.plot([cx, cx + sx * 0.4, cx + sx * 0.4], [cy + sy * 0.4, cy + sy * 0.4, cy], color=gold_main, lw=2.0)
        ax.plot([cx + sx * 0.1, cx + sx * 0.3], [cy + sy * 0.3, cy + sy * 0.1], color=gold_light, lw=1.2)

    # Title Banner (Stepped Geometric Header)
    t_bg = patches.Rectangle((1.5, 7.8), 13.0, 0.85, facecolor="#1a202c", edgecolor=gold_main, linewidth=2.0)
    ax.add_patch(t_bg)
    ax.add_patch(patches.Rectangle((1.6, 7.88), 12.8, 0.69, fill=False, edgecolor=gold_light, linewidth=0.8))
    
    ax.text(8.0, 8.35, "M O T I O N C O R R  :  M U L T I - A G E N T   A R C H I T E C T U R E", ha="center", va="center",
            fontsize=15, fontweight="bold", fontfamily="sans-serif", color=gold_light)
    ax.text(8.0, 8.02, "DIALECTIC SPECIFICATION   ✦   DUAL VERIFICATION GATES   ✦   BIT-EXACT PARITY", ha="center", va="center",
            fontsize=9.5, fontweight="semibold", color=gold_main)

    col_w = 2.75
    col_gap = 0.28
    left_start = 0.6
    phase_y = 7.5
    col_h = 5.7

    for idx, (p_title, p_sub, cards) in enumerate(PHASES_DATA):
        x = left_start + idx * (col_w + col_gap)

        # Column frame with stepped header
        c_box = patches.Rectangle((x, phase_y - col_h), col_w, col_h, facecolor=card_bg, edgecolor=gold_dark, linewidth=1.5)
        ax.add_patch(c_box)

        # Header Plate
        h_box = patches.Rectangle((x + 0.08, phase_y - 0.72), col_w - 0.16, 0.64, facecolor="#14181f", edgecolor=gold_main, linewidth=1.2)
        ax.add_patch(h_box)
        ax.text(x + col_w / 2, phase_y - 0.38, p_title.upper(), ha="center", va="center",
                fontsize=9.5, fontweight="bold", color=gold_light)
        ax.text(x + col_w / 2, phase_y - 0.58, p_sub, ha="center", va="center",
                fontsize=8.0, color=gold_main)

        # Cards
        card_y_start = phase_y - 0.82
        card_h = 0.82
        card_spacing = 0.94

        for c_idx, (c_header, c_desc) in enumerate(cards):
            cy = card_y_start - c_idx * card_spacing - card_h
            is_highlight = ("Certified" in c_header or "Parity Gate" in c_header or "Clean Branch" in c_header or "Speedup" in c_header)
            
            c_fill = "#242d3d" if not is_highlight else "#1b332b"
            c_border = gold_dark if not is_highlight else gold_main
            
            cp = patches.Rectangle((x + 0.12, cy), col_w - 0.24, card_h, facecolor=c_fill, edgecolor=c_border, linewidth=1.0)
            ax.add_patch(cp)

            ax.text(x + 0.22, cy + card_h - 0.24, c_header, ha="left", va="center",
                    fontsize=9.0, fontweight="bold", color=gold_light if is_highlight else text_cream)
            ax.text(x + 0.22, cy + 0.24, c_desc, ha="left", va="center",
                    fontsize=7.5, color=gold_main if is_highlight else "#a0aec0")

        # Deco Diamond connector
        if idx < len(PHASES_DATA) - 1:
            arrow_x = x + col_w + col_gap / 2
            arrow_y = phase_y - col_h / 2
            ax.plot([arrow_x - 0.08, arrow_x, arrow_x + 0.08, arrow_x, arrow_x - 0.08],
                    [arrow_y, arrow_y + 0.1, arrow_y, arrow_y - 0.1, arrow_y], color=gold_main, lw=1.5, fillstyle='full')

    # Footer
    ax.text(8.0, 0.9, "GOVERNANCE: AGENT META-AUDITOR   ✦   STRICT SCIENTIFIC EXACT PARITY (RMSE = 0.0, Δ = 0.0 PX)",
            ha="center", va="center", fontsize=9.0, fontweight="bold", color=gold_main)

    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, facecolor=bg_color, edgecolor="none", bbox_inches="tight", dpi=200)
    if out_svg:
        plt.savefig(out_svg, facecolor=bg_color, edgecolor="none", bbox_inches="tight")
    plt.close()
    print(f"[Style: Art Deco] Generated -> {out_png}")


def render_art_nouveau(out_png: Path, out_svg: Path = None):
    """Art Nouveau Style: Organic warm curves, sage olive, terracotta amber, warm parchment cream."""
    fig, ax = plt.subplots(figsize=(16, 9), dpi=200)
    bg_color = "#f9f6f0"      # Warm ivory parchment
    sage_dark = "#2b4c3f"     # Deep forest sage
    sage_medium = "#4a6b5d"   # Muted sage
    sage_light = "#e8efe9"    # Soft celadon tint
    terracotta = "#b85d34"    # Warm terracotta
    amber = "#d9822b"         # Warm golden amber
    card_bg = "#ffffff"       # Clean ivory white
    text_dark = "#1c2b24"     # Deep forest slate

    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")

    # Organic Arched Header & Sinuous Border
    outer_border = patches.FancyBboxPatch((0.4, 0.4), 15.2, 8.2, boxstyle="round,pad=0.1,rounding_size=0.4",
                                          facecolor="none", edgecolor=sage_medium, linewidth=1.8)
    ax.add_patch(outer_border)
    inner_border = patches.FancyBboxPatch((0.5, 0.5), 15.0, 8.0, boxstyle="round,pad=0.08,rounding_size=0.35",
                                          facecolor="none", edgecolor=terracotta, linewidth=0.8)
    ax.add_patch(inner_border)

    # Title Banner with organic rounded arc
    t_box = patches.FancyBboxPatch((1.8, 7.85), 12.4, 0.8, boxstyle="round,pad=0.1,rounding_size=0.3",
                                  facecolor=sage_light, edgecolor=sage_dark, linewidth=1.5)
    ax.add_patch(t_box)
    ax.text(8.0, 8.35, "MotionCorr: Multi-Agent Engineering Lifecycle", ha="center", va="center",
            fontsize=16, fontweight="bold", fontfamily="sans-serif", color=sage_dark)
    ax.text(8.0, 8.05, "Dialectic Specification  •  Dual Verification Gates  •  Bit-Exact Parity", ha="center", va="center",
            fontsize=10.0, fontstyle="italic", color=terracotta)

    col_w = 2.75
    col_gap = 0.28
    left_start = 0.6
    phase_y = 7.55
    col_h = 5.75

    for idx, (p_title, p_sub, cards) in enumerate(PHASES_DATA):
        x = left_start + idx * (col_w + col_gap)

        # Column organic container
        c_box = patches.FancyBboxPatch((x, phase_y - col_h), col_w, col_h,
                                       boxstyle="round,pad=0.08,rounding_size=0.25",
                                       facecolor="#f2ede4", edgecolor=sage_medium, linewidth=1.2)
        ax.add_patch(c_box)

        # Header Pill
        h_pill = patches.FancyBboxPatch((x + 0.1, phase_y - 0.72), col_w - 0.2, 0.62,
                                        boxstyle="round,pad=0.06,rounding_size=0.2",
                                        facecolor=sage_dark, edgecolor=amber, linewidth=1.0)
        ax.add_patch(h_pill)
        ax.text(x + col_w / 2, phase_y - 0.38, p_title, ha="center", va="center",
                fontsize=9.8, fontweight="bold", color="#ffffff")
        ax.text(x + col_w / 2, phase_y - 0.58, p_sub, ha="center", va="center",
                fontsize=8.0, fontstyle="italic", color="#f7e6c4")

        # Cards
        card_y_start = phase_y - 0.82
        card_h = 0.82
        card_spacing = 0.94

        for c_idx, (c_header, c_desc) in enumerate(cards):
            cy = card_y_start - c_idx * card_spacing - card_h
            is_highlight = ("Certified" in c_header or "Parity Gate" in c_header or "Clean Branch" in c_header or "Speedup" in c_header)

            c_fill = "#ffffff" if not is_highlight else "#e2ede6"
            c_edge = sage_medium if not is_highlight else terracotta

            cp = patches.FancyBboxPatch((x + 0.12, cy), col_w - 0.24, card_h,
                                        boxstyle="round,pad=0.05,rounding_size=0.15",
                                        facecolor=c_fill, edgecolor=c_edge, linewidth=1.0)
            ax.add_patch(cp)

            ax.text(x + 0.22, cy + card_h - 0.24, c_header, ha="left", va="center",
                    fontsize=9.2, fontweight="bold", color=sage_dark if not is_highlight else terracotta)
            ax.text(x + 0.22, cy + 0.24, c_desc, ha="left", va="center",
                    fontsize=7.6, color="#4a5568")

        # Organic curved link
        if idx < len(PHASES_DATA) - 1:
            arrow_x = x + col_w + 0.05
            arrow_y = phase_y - col_h / 2
            ax.annotate('', xy=(arrow_x + col_gap - 0.1, arrow_y), xytext=(arrow_x, arrow_y),
                        arrowprops=dict(arrowstyle="->", color=terracotta, lw=2.0, mutation_scale=12,
                                        connectionstyle="arc3,rad=-0.1"))

    # Footer
    ax.text(8.0, 0.88, "Governance & Quality: Continuous Meta-Auditor  •  Bit-Exact Scientific Parity (RMSE = 0.0, Δ = 0.0 px)",
            ha="center", va="center", fontsize=9.2, fontweight="semibold", color=sage_dark)

    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, facecolor=bg_color, edgecolor="none", bbox_inches="tight", dpi=200)
    if out_svg:
        plt.savefig(out_svg, facecolor=bg_color, edgecolor="none", bbox_inches="tight")
    plt.close()
    print(f"[Style: Art Nouveau] Generated -> {out_png}")


def render_minimalist(out_png: Path, out_svg: Path = None):
    """Minimalist Style: Clean Swiss grid, monochrome palette with single deep cobalt blue accent, ultra-clean typography."""
    fig, ax = plt.subplots(figsize=(16, 9), dpi=200)
    bg_color = "#ffffff"      # Pure white
    text_primary = "#0f172a"  # Slate 900
    text_secondary = "#475569"# Slate 600
    border_light = "#e2e8f0"  # Slate 200
    border_dark = "#94a3b8"   # Slate 400
    cobalt_accent = "#1d4ed8" # Deep Cobalt Blue
    card_bg = "#f8fafc"       # Slate 50
    highlight_bg = "#eff6ff"  # Soft Blue 50

    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")

    # Clean Top Header (Swiss Style Typography)
    ax.plot([0.6, 15.4], [8.6, 8.6], color=text_primary, lw=2.0)
    ax.text(0.6, 8.28, "MotionCorr Standalone", fontsize=18, fontweight="bold", color=text_primary)
    ax.text(0.6, 7.98, "Multi-Agent Engineering Lifecycle  |  Exact Reference Gates (RMSE = 0.0)",
            fontsize=10.5, color=text_secondary)
    ax.text(15.4, 8.28, "16:9 SPECIFICATION", ha="right", fontsize=10.5, fontweight="bold", color=cobalt_accent)
    ax.text(15.4, 7.98, "RELION 5.1 Parity", ha="right", fontsize=9.5, color=text_secondary)
    ax.plot([0.6, 15.4], [7.75, 7.75], color=border_light, lw=1.0)

    col_w = 2.75
    col_gap = 0.28
    left_start = 0.6
    phase_y = 7.55
    col_h = 5.9

    for idx, (p_title, p_sub, cards) in enumerate(PHASES_DATA):
        x = left_start + idx * (col_w + col_gap)

        # Column Header (Clean minimal text)
        ax.text(x, phase_y - 0.22, f"0{idx + 1}. {p_title.split(':')[1].strip()}",
                fontsize=11.0, fontweight="bold", color=cobalt_accent)
        ax.text(x, phase_y - 0.42, p_sub, fontsize=8.5, color=text_secondary)
        ax.plot([x, x + col_w], [phase_y - 0.52, phase_y - 0.52], color=text_primary, lw=1.2)

        # Cards
        card_y_start = phase_y - 0.65
        card_h = 0.85
        card_spacing = 0.98

        for c_idx, (c_header, c_desc) in enumerate(cards):
            cy = card_y_start - c_idx * card_spacing - card_h
            is_highlight = ("Certified" in c_header or "Parity Gate" in c_header or "Clean Branch" in c_header or "Speedup" in c_header)

            c_fill = highlight_bg if is_highlight else card_bg
            c_edge = cobalt_accent if is_highlight else border_light

            cp = patches.Rectangle((x, cy), col_w, card_h, facecolor=c_fill, edgecolor=c_edge, linewidth=1.0)
            ax.add_patch(cp)

            ax.text(x + 0.14, cy + card_h - 0.25, c_header, ha="left", va="center",
                    fontsize=9.2, fontweight="bold", color=cobalt_accent if is_highlight else text_primary)
            ax.text(x + 0.14, cy + 0.25, c_desc, ha="left", va="center",
                    fontsize=7.8, color=text_secondary)

        # Clean vertical separator or minimal right arrow
        if idx < len(PHASES_DATA) - 1:
            arrow_x = x + col_w + 0.08
            arrow_y = phase_y - col_h / 2
            ax.annotate('', xy=(arrow_x + col_gap - 0.16, arrow_y), xytext=(arrow_x, arrow_y),
                        arrowprops=dict(arrowstyle="->", color=border_dark, lw=1.5, mutation_scale=10))

    # Bottom minimal rule
    ax.plot([0.6, 15.4], [0.85, 0.85], color=border_light, lw=1.0)
    ax.text(0.6, 0.6, "Meta-Governance: Continuous Agent Auditor", fontsize=8.5, color=text_secondary)
    ax.text(15.4, 0.6, "Tested on 4x NVIDIA A100 GPUs • Bit-Exact Parity Guaranteed", ha="right", fontsize=8.5, color=text_secondary)

    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, facecolor=bg_color, edgecolor="none", bbox_inches="tight", dpi=200)
    if out_svg:
        plt.savefig(out_svg, facecolor=bg_color, edgecolor="none", bbox_inches="tight")
    plt.close()
    print(f"[Style: Minimalist] Generated -> {out_png}")


def render_bauhaus(out_png: Path, out_svg: Path = None):
    """Bauhaus Style: Primary colors (Bauhaus red, cobalt blue, warm ochre yellow), bold geometric blocks, structured balance."""
    fig, ax = plt.subplots(figsize=(16, 9), dpi=200)
    bg_color = "#f4f1ea"      # Classic Bauhaus off-white / parchment
    b_black = "#121212"       # Deep black
    b_red = "#d92b27"         # Bauhaus Crimson Red
    b_blue = "#1e40af"        # Bauhaus Cobalt Blue
    b_yellow = "#eab308"      # Bauhaus Ochre Yellow
    b_white = "#ffffff"       # Crisp white
    text_dark = "#121212"

    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")

    # Bauhaus Geometric Title Header
    ax.add_patch(patches.Rectangle((0.6, 7.8), 0.4, 0.85, facecolor=b_red, edgecolor="none"))
    ax.add_patch(patches.Rectangle((1.0, 7.8), 0.4, 0.85, facecolor=b_blue, edgecolor="none"))
    ax.add_patch(patches.Rectangle((1.4, 7.8), 0.4, 0.85, facecolor=b_yellow, edgecolor="none"))
    
    t_box = patches.Rectangle((1.9, 7.8), 13.5, 0.85, facecolor=b_black, edgecolor="none")
    ax.add_patch(t_box)
    ax.text(2.2, 8.32, "MOTIONCORR : MULTI-AGENT ENGINEERING", fontsize=15, fontweight="bold", color=b_white)
    ax.text(2.2, 8.02, "FUNCTION FOLLOWS FORM  ✦  DIALECTIC SPECIFICATION  ✦  EXACT NUMERICAL GATES", fontsize=9.0, fontweight="bold", color=b_yellow)

    # Bauhaus Circle Element in Header
    circle = patches.Circle((14.8, 8.22), 0.28, facecolor=b_red, edgecolor=b_white, lw=1.5)
    ax.add_patch(circle)

    col_w = 2.75
    col_gap = 0.28
    left_start = 0.6
    phase_y = 7.55
    col_h = 5.85

    phase_colors = [b_blue, b_red, b_yellow, b_black, b_blue]

    for idx, (p_title, p_sub, cards) in enumerate(PHASES_DATA):
        x = left_start + idx * (col_w + col_gap)
        p_color = phase_colors[idx % len(phase_colors)]

        # Column frame with bold top bar
        c_box = patches.Rectangle((x, phase_y - col_h), col_w, col_h, facecolor=b_white, edgecolor=b_black, linewidth=1.5)
        ax.add_patch(c_box)

        # Bold top color block
        h_bar = patches.Rectangle((x, phase_y - 0.65), col_w, 0.65, facecolor=p_color, edgecolor=b_black, linewidth=1.2)
        ax.add_patch(h_bar)
        
        h_text_color = b_black if p_color == b_yellow else b_white
        ax.text(x + col_w / 2, phase_y - 0.32, p_title.upper(), ha="center", va="center",
                fontsize=9.2, fontweight="bold", color=h_text_color)
        ax.text(x + col_w / 2, phase_y - 0.50, p_sub, ha="center", va="center",
                fontsize=7.8, fontweight="bold", color=h_text_color)

        # Cards
        card_y_start = phase_y - 0.78
        card_h = 0.84
        card_spacing = 0.95

        for c_idx, (c_header, c_desc) in enumerate(cards):
            cy = card_y_start - c_idx * card_spacing - card_h
            is_highlight = ("Certified" in c_header or "Parity Gate" in c_header or "Clean Branch" in c_header or "Speedup" in c_header)

            c_fill = "#fffbeb" if is_highlight else "#f8f8f8"
            c_edge = b_red if is_highlight else b_black

            cp = patches.Rectangle((x + 0.1, cy), col_w - 0.2, card_h, facecolor=c_fill, edgecolor=c_edge, linewidth=1.2 if is_highlight else 0.8)
            ax.add_patch(cp)

            # Little Bauhaus color notch on card left
            notch_color = p_color if not is_highlight else b_red
            ax.add_patch(patches.Rectangle((x + 0.1, cy), 0.08, card_h, facecolor=notch_color, edgecolor="none"))

            ax.text(x + 0.26, cy + card_h - 0.25, c_header, ha="left", va="center",
                    fontsize=9.0, fontweight="bold", color=b_black)
            ax.text(x + 0.26, cy + 0.25, c_desc, ha="left", va="center",
                    fontsize=7.5, color="#374151")

        # Bold geometric connector
        if idx < len(PHASES_DATA) - 1:
            arrow_x = x + col_w + 0.06
            arrow_y = phase_y - col_h / 2
            ax.annotate('', xy=(arrow_x + col_gap - 0.12, arrow_y), xytext=(arrow_x, arrow_y),
                        arrowprops=dict(arrowstyle="->", color=b_black, lw=2.5, mutation_scale=14))

    # Bottom Bauhaus Banner
    ax.add_patch(patches.Rectangle((0.6, 0.45), 14.8, 0.65, facecolor=b_black, edgecolor="none"))
    ax.text(0.9, 0.78, "BAUHAUS GOVERNANCE : META-AUDITOR & CONTINUOUS TESTING", fontsize=9.2, fontweight="bold", color=b_yellow)
    ax.text(0.9, 0.58, "STRICT RELION 5.1 BIT-PARITY : EXACT GATE RMSE = 0.0 • 4.1X MEASURED CPU SPEEDUP", fontsize=8.0, color=b_white)

    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, facecolor=bg_color, edgecolor="none", bbox_inches="tight", dpi=200)
    if out_svg:
        plt.savefig(out_svg, facecolor=bg_color, edgecolor="none", bbox_inches="tight")
    plt.close()
    print(f"[Style: Bauhaus] Generated -> {out_png}")


def main():
    parser = argparse.ArgumentParser(description="Multi-Style Architecture Diagram Generator")
    parser.add_argument("--out-dir", type=Path, default=Path("presentation/plots"), help="Output directory")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    render_art_deco(args.out_dir / "architecture_art_deco.png", args.out_dir / "architecture_art_deco.svg")
    render_art_nouveau(args.out_dir / "architecture_art_nouveau.png", args.out_dir / "architecture_art_nouveau.svg")
    render_minimalist(args.out_dir / "architecture_minimalist.png", args.out_dir / "architecture_minimalist.svg")
    render_bauhaus(args.out_dir / "architecture_bauhaus.png", args.out_dir / "architecture_bauhaus.svg")


if __name__ == "__main__":
    main()
