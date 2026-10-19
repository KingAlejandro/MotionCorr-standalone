#!/usr/bin/env python3
"""Reproduce the four PR #64 review findings against the pre-review code.

Runs the analysis exactly as published (commit 059d8dd3) on the committed data,
using that revision's own API, and prints the defect each finding names. Then
prints the corrected numbers from the current code so the two can be compared
directly.

This exists so the findings are checkable rather than asserted, and so the
superseded numbers stay visible next to their replacements.

Usage (from the repository root, with the pre-review tree extracted):

    git archive 059d8dd3 | tar -x -C /tmp/prerev
    python3 tools/calibration/reproduce_review_findings.py --prerev /tmp/prerev
"""

from __future__ import annotations

import argparse
import collections
import glob
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def read_cells(data_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    out = {"L1": [], "L2": [], "L3": []}
    for f in sorted(glob.glob(str(data_dir / "layer*.json"))):
        key = "L1" if "layer1" in Path(f).name else "L2" if "layer2" in Path(f).name else "L3"
        out[key].extend(json.loads(Path(f).read_text())["records"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prerev", type=Path, required=True,
                    help="tree extracted from commit 059d8dd3")
    ap.add_argument("--data", type=Path, default=REPO / "docs/calibration/data")
    args = ap.parse_args()

    cells = read_cells(args.data)
    allr = cells["L1"] + cells["L2"] + cells["L3"]
    print(f"data: L1={len(cells['L1'])} L2={len(cells['L2'])} L3={len(cells['L3'])} "
          f"total={len(allr)}\n")

    # ---- finding 1: the hold-out split ----------------------------------
    print("FINDING 1 (discussion_r4119255250) -- hold-out split lost")
    n_split = sum(1 for r in cells["L3"] if "split" in r)
    print(f"  Layer-3 records carrying a `split` field: {n_split} of {len(cells['L3'])}")
    pre_sel = [r for r in allr if r.get("split") in (None, "selection", "control")]
    pre_hold = [r for r in allr if r.get("split") == "holdout"]
    layers = collections.Counter(r.get("layer", "L3") for r in pre_hold)
    print(f"  published buckets: selection={len(pre_sel)} holdout={len(pre_hold)}")
    print(f"  layer composition of the published hold-out: {dict(layers)}")
    holdmovies = {"00042", "00044", "00046", "00047", "00048", "00049"}
    print(f"  hold-out MOVIE cells that leaked into selection: "
          f"{sum(1 for r in pre_sel if r.get('movie') in holdmovies)}")
    print(f"  hold-out MOVIE cells that reached the hold-out bucket: "
          f"{sum(1 for r in pre_hold if r.get('movie') in holdmovies)}")

    from tools.calibration import analyze as NEW
    now = collections.Counter(NEW.joint_split(r) for r in allr)
    print(f"  CORRECTED two-axis split: {dict(now)}")
    print(f"    movie-axis hold-out cells:    "
          f"{sum(1 for r in allr if NEW.axis_bucket(r, 'movie') == 'holdout')}")
    print(f"    severity-axis hold-out cells: "
          f"{sum(1 for r in allr if NEW.axis_bucket(r, 'severity') == 'holdout')}\n")

    # ---- findings 2 and 3: tiering --------------------------------------
    pre = load_module(args.prerev / "tools/calibration/analyze.py", "prerev_analyze")
    floors = pre.noise_floor(cells["L3"])["j4"]
    pre_tiers = collections.Counter(
        pre.tier_of(r, "harm_delta_b_a2", 5.0, floors) for r in allr)
    new_tiers = collections.Counter(
        NEW.tier_of(r, "harm_delta_b_a2", 5.0, floors) for r in allr)

    def fault(r):
        return str(r.get("fault") or r.get("group") or "")

    x1 = [r for r in allr if fault(r).startswith("X1_translation")]
    x8 = [r for r in allr if fault(r).startswith("X8_gain")]
    print("FINDING 2 (discussion_r4119255253) -- accounted translation tiered harmful")
    print(f"  prespecification FAULT_CLASS['X1_translation_px'] = 'benign_but_alarming'")
    print(f"  pre-review: {sum(1 for r in x1 if pre.tier_of(r,'harm_delta_b_a2',5.0,floors).startswith('unacceptable'))}"
          f" of {len(x1)} X1 cells tiered unacceptable")
    print(f"  corrected : {sum(1 for r in x1 if NEW.tier_of(r,'harm_delta_b_a2',5.0,floors).startswith('unacceptable'))}"
          f" of {len(x1)} X1 cells tiered unacceptable\n")

    print("FINDING 3 (discussion_r4119255256) -- uniform scale tiered as frame-dependent harm")
    print("  prespecification: 'A frame-dependent scale error above this fraction is unacceptable'")
    print(f"  pre-review: {sum(1 for r in x8 if pre.tier_of(r,'harm_delta_b_a2',5.0,floors)=='unacceptable:scale')}"
          f" of {len(x8)} uniform-gain cells tiered unacceptable:scale")
    print(f"  corrected : {sum(1 for r in x8 if NEW.tier_of(r,'harm_delta_b_a2',5.0,floors)=='unacceptable:scale')}"
          f" of {len(x8)} uniform-gain cells tiered unacceptable:scale")
    print(f"  tier census pre-review: {dict(pre_tiers)}")
    print(f"  tier census corrected : {dict(new_tiers)}\n")

    # ---- finding 4: the missing X6 arm ----------------------------------
    print("FINDING 4 (discussion_r4119255261) -- prespecified Layer-2 X6 arm absent")
    l2_faults = collections.Counter(r.get("fault") for r in cells["L2"])
    print(f"  Layer-2 X6 cells in the committed data: {l2_faults.get('X6_dose_scale', 0)}")
    print(f"  Layer-2 faults present: {sorted(f for f in l2_faults if f)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
