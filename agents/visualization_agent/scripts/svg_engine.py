#!/usr/bin/env python3
"""
Pure-Python SVG Vector Graphics Engine
Generates publication-quality charts (line, bar, stacked bar, trajectory vectors)
without external dependencies (e.g. matplotlib).
"""

import math
from typing import Dict, List, Optional, Tuple


class SvgCanvas:
    """Lightweight, self-contained SVG builder."""

    def __init__(self, width: int = 800, height: int = 500, title: str = ""):
        self.width = width
        self.height = height
        self.title = title
        self.elements: List[str] = []

    def add_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str = "#3b82f6",
        stroke: str = "none",
        stroke_width: float = 1.0,
        rx: float = 0.0,
        opacity: float = 1.0,
    ) -> None:
        self.elements.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" rx="{rx:.1f}" opacity="{opacity:.2f}"/>'
        )

    def add_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        stroke: str = "#64748b",
        stroke_width: float = 1.5,
        stroke_dasharray: str = "none",
        opacity: float = 1.0,
    ) -> None:
        dash_attr = f' stroke-dasharray="{stroke_dasharray}"' if stroke_dasharray != "none" else ""
        self.elements.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}"{dash_attr} opacity="{opacity:.2f}"/>'
        )

    def add_circle(
        self,
        cx: float,
        cy: float,
        r: float,
        fill: str = "#2563eb",
        stroke: str = "#ffffff",
        stroke_width: float = 1.5,
    ) -> None:
        self.elements.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>'
        )

    def add_polyline(
        self,
        points: List[Tuple[float, float]],
        stroke: str = "#2563eb",
        stroke_width: float = 2.5,
        fill: str = "none",
        stroke_dasharray: str = "none",
    ) -> None:
        pts_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        dash_attr = f' stroke-dasharray="{stroke_dasharray}"' if stroke_dasharray != "none" else ""
        self.elements.append(
            f'<polyline points="{pts_str}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"{dash_attr}/>'
        )

    def add_text(
        self,
        x: float,
        y: float,
        text: str,
        font_size: int = 12,
        fill: str = "#1e293b",
        font_family: str = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        font_weight: str = "normal",
        text_anchor: str = "start",
        transform: Optional[str] = None,
    ) -> None:
        tf_attr = f' transform="{transform}"' if transform else ""
        escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.elements.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{font_size}" fill="{fill}" '
            f'font-family="{font_family}" font-weight="{font_weight}" text-anchor="{text_anchor}"{tf_attr}>'
            f'{escaped_text}</text>'
        )

    def render(self) -> str:
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" width="{self.width}" height="{self.height}">',
            '  <defs>',
            '    <style>',
            '      .axis-text { font-family: system-ui, sans-serif; font-size: 11px; fill: #64748b; }',
            '      .title-text { font-family: system-ui, sans-serif; font-size: 16px; font-weight: 600; fill: #0f172a; }',
            '      .legend-text { font-family: system-ui, sans-serif; font-size: 11px; fill: #334155; }',
            '    </style>',
            '  </defs>',
            f'  <rect width="{self.width}" height="{self.height}" fill="#ffffff" rx="8"/>',
        ]
        if self.title:
            lines.append(f'  <text x="{self.width / 2:.2f}" y="32" class="title-text" text-anchor="middle">{self.title}</text>')
        for el in self.elements:
            lines.append(f'  {el}')
        lines.append('</svg>')
        return "\n".join(lines)


def render_speedup_scaling_svg(
    title: str,
    thread_counts: List[int],
    wall_times: List[float],
    speedups: List[float],
    amdahl_fit: Optional[List[float]] = None,
    width: int = 850,
    height: int = 500,
) -> str:
    """Render dual-axis execution time and speedup curve."""
    canvas = SvgCanvas(width, height, title)
    margin_l, margin_r, margin_t, margin_b = 80, 80, 60, 60
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    # Draw plot background and grid
    canvas.add_rect(margin_l, margin_t, plot_w, plot_h, fill="#f8fafc", stroke="#e2e8f0", stroke_width=1.0)

    # Scales
    max_threads = max(thread_counts) if thread_counts else 10
    max_time = max(wall_times) * 1.1 if wall_times else 100.0
    max_speedup = max(max(speedups) if speedups else 1.0, max(amdahl_fit) if amdahl_fit else 1.0, max_threads) * 1.1

    def x_coord(th: float) -> float:
        return margin_l + (th / max_threads) * plot_w

    def y_time_coord(t: float) -> float:
        return margin_t + plot_h - (t / max_time) * plot_h

    def y_speedup_coord(s: float) -> float:
        return margin_t + plot_h - (s / max_speedup) * plot_h

    # Horizontal grid lines for time
    for i in range(6):
        val = (max_time / 5) * i
        y = y_time_coord(val)
        canvas.add_line(margin_l, y, margin_l + plot_w, y, stroke="#e2e8f0", stroke_width=1.0)
        canvas.add_text(margin_l - 10, y + 4, f"{val:.1f}s", font_size=10, text_anchor="end")

    # Right axis: speedup ticks
    for i in range(6):
        val = (max_speedup / 5) * i
        y = y_speedup_coord(val)
        canvas.add_text(margin_l + plot_w + 10, y + 4, f"{val:.1f}x", font_size=10, fill="#2563eb", text_anchor="start")

    # X-axis ticks
    for th in thread_counts:
        x = x_coord(th)
        canvas.add_line(x, margin_t + plot_h, x, margin_t + plot_h + 5, stroke="#64748b")
        canvas.add_text(x, margin_t + plot_h + 20, f"{th} th", font_size=11, text_anchor="middle")

    # Ideal linear speedup line (dashed gray)
    canvas.add_line(
        x_coord(1), y_speedup_coord(1),
        x_coord(max_threads), y_speedup_coord(max_threads),
        stroke="#94a3b8", stroke_width=1.5, stroke_dasharray="4,4"
    )

    # Amdahl fit curve (dashed blue)
    if amdahl_fit and len(amdahl_fit) == len(thread_counts):
        pts_amdahl = [(x_coord(th), y_speedup_coord(s)) for th, s in zip(thread_counts, amdahl_fit)]
        canvas.add_polyline(pts_amdahl, stroke="#3b82f6", stroke_width=2.0, stroke_dasharray="5,3")

    # Measured Speedup line (solid blue with nodes)
    pts_sp = [(x_coord(th), y_speedup_coord(s)) for th, s in zip(thread_counts, speedups)]
    canvas.add_polyline(pts_sp, stroke="#1d4ed8", stroke_width=2.5)
    for x, y in pts_sp:
        canvas.add_circle(x, y, 4.5, fill="#1d4ed8", stroke="#ffffff", stroke_width=1.5)

    # Measured Wall time line (solid red with nodes)
    pts_wt = [(x_coord(th), y_time_coord(t)) for th, s, t in zip(thread_counts, speedups, wall_times)]
    canvas.add_polyline(pts_wt, stroke="#dc2626", stroke_width=2.5)
    for x, y in pts_wt:
        canvas.add_circle(x, y, 4.5, fill="#dc2626", stroke="#ffffff", stroke_width=1.5)

    # Legend
    leg_x = margin_l + 15
    leg_y = margin_t + 20
    # Wall Time
    canvas.add_line(leg_x, leg_y, leg_x + 20, leg_y, stroke="#dc2626", stroke_width=2.5)
    canvas.add_circle(leg_x + 10, leg_y, 3.5, fill="#dc2626", stroke="#ffffff")
    canvas.add_text(leg_x + 28, leg_y + 4, "Wall-Clock Time (s)", font_size=11, font_weight="bold", fill="#dc2626")
    # Speedup
    canvas.add_line(leg_x + 180, leg_y, leg_x + 200, leg_y, stroke="#1d4ed8", stroke_width=2.5)
    canvas.add_circle(leg_x + 190, leg_y, 3.5, fill="#1d4ed8", stroke="#ffffff")
    canvas.add_text(leg_x + 208, leg_y + 4, "Measured Speedup (x)", font_size=11, font_weight="bold", fill="#1d4ed8")
    # Linear Ideal
    canvas.add_line(leg_x + 360, leg_y, leg_x + 380, leg_y, stroke="#94a3b8", stroke_width=1.5, stroke_dasharray="4,4")
    canvas.add_text(leg_x + 388, leg_y + 4, "Ideal Linear", font_size=11, fill="#64748b")

    # Axis Labels
    canvas.add_text(margin_l + plot_w / 2, height - 15, "OpenMP Thread Count", font_size=12, font_weight="600", text_anchor="middle")
    canvas.add_text(25, margin_t + plot_h / 2, "Execution Time (seconds)", font_size=12, font_weight="600", text_anchor="middle", transform=f"rotate(-90 25 {margin_t + plot_h / 2})")
    canvas.add_text(width - 20, margin_t + plot_h / 2, "Speedup Multiplier (x)", font_size=12, font_weight="600", fill="#1d4ed8", text_anchor="middle", transform=f"rotate(90 {width - 20} {margin_t + plot_h / 2})")

    return canvas.render()


def render_stacked_stages_svg(
    title: str,
    categories: List[str],  # e.g. ["1 Thread", "4 Threads", "10 Threads"]
    stage_names: List[str],  # e.g. ["FFT", "Patch Alignment", "Dose Weighting", "I/O"]
    stage_matrix: List[List[float]],  # shape: len(categories) x len(stage_names)
    stage_colors: Optional[List[str]] = None,
    width: int = 850,
    height: int = 450,
) -> str:
    """Render horizontal stacked bar chart showing subroutine breakdown."""
    canvas = SvgCanvas(width, height, title)
    margin_l, margin_r, margin_t, margin_b = 130, 40, 60, 90
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    default_colors = ["#2563eb", "#38bdf8", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#64748b"]
    colors = stage_colors or default_colors

    # Background
    canvas.add_rect(margin_l, margin_t, plot_w, plot_h, fill="#f8fafc", stroke="#e2e8f0")

    # Find max total duration
    totals = [sum(row) for row in stage_matrix]
    max_tot = max(totals) * 1.1 if totals else 100.0

    # Grid lines
    for i in range(6):
        val = (max_tot / 5) * i
        x = margin_l + (val / max_tot) * plot_w
        canvas.add_line(x, margin_t, x, margin_t + plot_h, stroke="#e2e8f0")
        canvas.add_text(x, margin_t + plot_h + 18, f"{val:.1f}s", font_size=10, text_anchor="middle")

    n_cats = len(categories)
    bar_h = min(40.0, (plot_h / (n_cats or 1)) * 0.6)
    gap = (plot_h - n_cats * bar_h) / (n_cats + 1)

    for c_idx, cat in enumerate(categories):
        y = margin_t + gap * (c_idx + 1) + bar_h * c_idx
        canvas.add_text(margin_l - 10, y + bar_h / 2 + 4, cat, font_size=11, font_weight="600", text_anchor="end")
        
        curr_x = margin_l
        for s_idx, s_val in enumerate(stage_matrix[c_idx]):
            if s_val <= 0:
                continue
            seg_w = (s_val / max_tot) * plot_w
            c = colors[s_idx % len(colors)]
            canvas.add_rect(curr_x, y, seg_w, bar_h, fill=c, stroke="#ffffff", stroke_width=0.5)
            # Segment text if wide enough
            if seg_w > 40:
                canvas.add_text(curr_x + seg_w / 2, y + bar_h / 2 + 4, f"{s_val:.1f}s", font_size=9, fill="#ffffff", font_weight="bold", text_anchor="middle")
            curr_x += seg_w

    # Legend at bottom
    leg_x = margin_l
    leg_y = height - 35
    for s_idx, name in enumerate(stage_names):
        c = colors[s_idx % len(colors)]
        canvas.add_rect(leg_x, leg_y, 14, 14, fill=c, rx=2.0)
        canvas.add_text(leg_x + 18, leg_y + 11, name, font_size=10, fill="#334155")
        leg_x += len(name) * 7 + 45

    canvas.add_text(margin_l + plot_w / 2, margin_t + plot_h + 35, "Cumulative Stage Time (seconds)", font_size=11, font_weight="600", text_anchor="middle")
    return canvas.render()


def render_trajectory_drift_svg(
    title: str,
    frames: List[int],
    shift_x: List[float],
    shift_y: List[float],
    width: int = 800,
    height: int = 480,
) -> str:
    """Render 2D motion trajectory and cumulative shift curves."""
    canvas = SvgCanvas(width, height, title)
    margin_l, margin_r, margin_t, margin_b = 60, 40, 60, 60
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    canvas.add_rect(margin_l, margin_t, plot_w, plot_h, fill="#f8fafc", stroke="#e2e8f0")

    all_shifts = shift_x + shift_y
    min_s = min(all_shifts) if all_shifts else 0.0
    max_s = max(all_shifts) if all_shifts else 1.0
    span = max(abs(min_s), abs(max_s), 1.0) * 1.2
    max_frame = max(frames) if frames else len(shift_x)

    def x_coord(f: int) -> float:
        return margin_l + ((f - 1) / max(1, max_frame - 1)) * plot_w

    def y_coord(s: float) -> float:
        return margin_t + plot_h / 2 - (s / span) * (plot_h / 2)

    # Center zero line
    canvas.add_line(margin_l, margin_t + plot_h / 2, margin_l + plot_w, margin_t + plot_h / 2, stroke="#94a3b8", stroke_width=1.0)
    canvas.add_text(margin_l - 8, margin_t + plot_h / 2 + 4, "0.0 px", font_size=10, text_anchor="end")

    # Grid & Y-ticks
    for val in [-span * 0.75, -span * 0.5, span * 0.5, span * 0.75]:
        y = y_coord(val)
        canvas.add_line(margin_l, y, margin_l + plot_w, y, stroke="#e2e8f0", stroke_width=1.0)
        canvas.add_text(margin_l - 8, y + 4, f"{val:+.1f} px", font_size=10, text_anchor="end")

    # X-ticks
    for f in frames[::max(1, len(frames) // 8)]:
        x = x_coord(f)
        canvas.add_line(x, margin_t + plot_h, x, margin_t + plot_h + 5, stroke="#64748b")
        canvas.add_text(x, margin_t + plot_h + 18, f"F{f}", font_size=10, text_anchor="middle")

    # Shift X line (Blue)
    pts_x = [(x_coord(f), y_coord(sx)) for f, sx in zip(frames, shift_x)]
    canvas.add_polyline(pts_x, stroke="#2563eb", stroke_width=2.5)
    for x, y in pts_x:
        canvas.add_circle(x, y, 3.5, fill="#2563eb", stroke="#ffffff")

    # Shift Y line (Green)
    pts_y = [(x_coord(f), y_coord(sy)) for f, sy in zip(frames, shift_y)]
    canvas.add_polyline(pts_y, stroke="#059669", stroke_width=2.5)
    for x, y in pts_y:
        canvas.add_circle(x, y, 3.5, fill="#059669", stroke="#ffffff")

    # Legend
    canvas.add_line(margin_l + 20, margin_t + 20, margin_l + 40, margin_t + 20, stroke="#2563eb", stroke_width=2.5)
    canvas.add_text(margin_l + 48, margin_t + 24, "Shift X (px)", font_size=11, font_weight="bold", fill="#2563eb")
    canvas.add_line(margin_l + 160, margin_t + 20, margin_l + 180, margin_t + 20, stroke="#059669", stroke_width=2.5)
    canvas.add_text(margin_l + 188, margin_t + 24, "Shift Y (px)", font_size=11, font_weight="bold", fill="#059669")

    canvas.add_text(margin_l + plot_w / 2, height - 15, "Movie Frame Index", font_size=12, font_weight="600", text_anchor="middle")
    canvas.add_text(18, margin_t + plot_h / 2, "Displacement (pixels)", font_size=12, font_weight="600", text_anchor="middle", transform=f"rotate(-90 18 {margin_t + plot_h / 2})")

    return canvas.render()
