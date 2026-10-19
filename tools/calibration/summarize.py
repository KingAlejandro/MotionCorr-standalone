#!/usr/bin/env python3
"""Render the calibration measurements as the tables that go into the report.

Pure formatting over the JSON produced by the three layer drivers. Kept
separate from analyze.py so that the tables in the report can be regenerated
without re-running the threshold search.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.calibration.prespecification import (  # noqa: E402
    GATE2_LIMITS_READONLY,
    PIXEL_SIZE_A,
    amplitude_loss,
)

COLS = [
    ("image_relative_rmse", "relRMSE"),
    ("image_rmse", "absRMSE"),
    ("image_max_abs_error", "maxpix"),
    ("std_scale_dev", "scale_dev"),
    ("std_shift_px", "shift_px"),
    ("std_delta_b_a2", "dB_A2"),
    ("std_eps_incoherent", "eps_inc"),
    ("traj_max_shift_error", "trajmax"),
    ("traj_coord_rms_error", "trajrms"),
    ("field_rms_px", "fieldRMS"),
    ("field_interframe_rms_px", "fieldIF"),
    ("rel_rmse_low", "relLow"),
    ("rel_rmse_mid", "relMid"),
    ("rel_rmse_high", "relHigh"),
    ("border_interior_ratio", "border/int"),
]


def num(rec: Dict[str, Any], key: str) -> Optional[float]:
    v = rec.get(key)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def load(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in paths:
        out.extend(json.loads(Path(p).read_text())["records"])
    return out


def table(records: List[Dict[str, Any]], key_fn, title: str, stat: str = "median") -> None:
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    for r in records:
        groups.setdefault(key_fn(r), []).append(r)
    width = max((len(str(k)) for k in groups), default=10) + 2
    print(f"\n### {title}   ({stat} over cells; n = replicates)\n")
    hdr = f"| {'cell':{width}s} | n |" + "".join(f" {n} |" for _, n in COLS)
    print(hdr)
    print("|" + "---|" * (len(COLS) + 2))
    for k in sorted(groups, key=str):
        rs = groups[k]
        row = f"| {str(k):{width}s} | {len(rs)} |"
        for col, _ in COLS:
            vals = [abs(v) for v in (num(r, col) for r in rs) if v is not None]
            if not vals:
                row += " - |"
                continue
            v = st.median(vals) if stat == "median" else max(vals)
            row += f" {v:.4g} |" if v else " 0 |"
        print(row)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layer1", type=Path, nargs="*", default=[])
    ap.add_argument("--layer2", type=Path, nargs="*", default=[])
    ap.add_argument("--layer3", type=Path, nargs="*", default=[])
    ap.add_argument("--stat", choices=["median", "max"], default="median")
    args = ap.parse_args()

    if args.layer3:
        l3 = load(args.layer3)
        harmless = [r for r in l3 if r.get("group") in
                    ("REF", "H1_threads", "H2_proc_bind", "H3_repeat")
                    or r.get("label") in ("gain_null", "mov_null")]
        vals = []
        for r in harmless:
            for col, _ in COLS:
                v = num(r, col)
                if v is not None:
                    vals.append(abs(v))
        print(f"\n### Layer 3 harmless-variation floor\n")
        print(f"cells: {len(harmless)}   diagnostic values: {len(vals)}")
        print(f"largest absolute value across every diagnostic and every "
              f"harmless cell: {max(vals) if vals else float('nan'):.3e}")
        nonzero = [v for v in vals if v > 0]
        print(f"nonzero values: {len(nonzero)}"
              + (f"   largest {max(nonzero):.3e}" if nonzero else ""))
        table([r for r in l3 if r.get("group") not in
               ("REF", "H1_threads", "H2_proc_bind", "H3_repeat")],
              lambda r: f"{r['group']}/{r['label']}", "Layer 3 faults", args.stat)

    if args.layer1:
        l1 = load(args.layer1)
        table(l1, lambda r: f"{r['fault']}={r['severity']:g}"
              + (f"/L{r['correlation_fraction']:g}" if "correlation_fraction" in r else ""),
              "Layer 1: faults injected into real corrected micrographs", args.stat)

    if args.layer2:
        l2 = load(args.layer2)
        print("\n### Layer 2 harm bridge: reference-measured delta-B against absolute harm\n")
        print("| fault | severity | noise | n | gate dB | harm dB | ratio | relRMSE | "
              "eps_inc | amp loss at 3A |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        g: Dict[Any, List[Dict[str, Any]]] = {}
        for r in l2:
            g.setdefault((r["fault"], r["severity"], r.get("noise_sigma")), []).append(r)
        for (flt, sev, ns), rs in sorted(g.items(), key=lambda x: (x[0][0], x[0][1], x[0][2] or 0)):
            gd = [num(r, "std_delta_b_a2") for r in rs]
            hd = [num(r, "harm_delta_b_a2") for r in rs]
            rr = [num(r, "image_relative_rmse") for r in rs]
            ep = [num(r, "std_eps_incoherent") for r in rs]
            gd = [v for v in gd if v is not None]
            hd = [v for v in hd if v is not None]
            if not gd or not hd:
                continue
            mg, mh = st.median(gd), st.median(hd)
            ratio = f"{mg/mh:.2f}" if abs(mh) > 1e-6 else "n/a"
            print(f"| {flt} | {sev:g} | {ns:g} | {len(rs)} | {mg:.3f} | {mh:.3f} | {ratio} | "
                  f"{st.median([v for v in rr if v is not None]):.3e} | "
                  f"{st.median([v for v in ep if v is not None]):.3e} | "
                  f"{100*amplitude_loss(max(mg, 0.0)):.2f}% |")

    print(f"\n(Gate 2 limits, quoted read-only and unchanged: {GATE2_LIMITS_READONLY})")
    print(f"(pixel size {PIXEL_SIZE_A} A/px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
