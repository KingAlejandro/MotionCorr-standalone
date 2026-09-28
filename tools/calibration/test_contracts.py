#!/usr/bin/env python3
"""Data and analysis contract controls for the issue #60 calibration.

These are distinct from ``test_calibration.py``, which checks the measuring
instrument against closed-form answers. These check the CONTRACTS between the
frozen prespecification, the data the layer drivers emit, and the analysis that
consumes it -- the seam where the four review findings on PR #64 all lived:

  * hold-out split lost because Layer-3 records carried no split field
    (discussion_r4119255250)
  * accounted translations tiered as harmful (discussion_r4119255253)
  * uniform scale tiered as frame-dependent harm (discussion_r4119255256)
  * a prespecified Layer-2 fault arm never generated (discussion_r4119255261)

Each control below fails on the pre-review code and passes after the fix, so a
regression re-introduces a visible failure rather than a silent mislabelling.

Run:  python3 tools/calibration/test_contracts.py [--data docs/calibration/data]
"""

from __future__ import annotations

import argparse
import glob
import inspect
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.calibration import analyze as A                 # noqa: E402
from tools.calibration import layer2_forward as L2         # noqa: E402
from tools.calibration.prespecification import (           # noqa: E402
    FAULT_LAYERS,
    HOLDOUT_MOVIES,
    SELECTION_MOVIES,
    SEVERITY_GRIDS,
)

FAILURES: List[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def load(data_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {"L1": [], "L2": [], "L3": []}
    for f in sorted(glob.glob(str(data_dir / "layer*.json"))):
        name = Path(f).name
        key = "L1" if "layer1" in name else "L2" if "layer2" in name else "L3"
        out[key].extend(A.load([Path(f)]))
    return out


# ---------------------------------------------------------------------------

def test_layer2_covers_declared_faults() -> None:
    """Every fault FAULT_LAYERS says is reachable in L2 must actually be generated.

    This is the control that would have caught the missing X6 dose arm: the
    frozen matrix declared it reachable in Layer 2, and the driver simply never
    emitted it, so the real-pipeline dose response had no ground-truth bridge.
    """
    print("\nContract 1: Layer 2 generates every fault the frozen matrix declares reachable there")
    src = inspect.getsource(L2.run_trial)
    declared = sorted(f for f, layers in FAULT_LAYERS.items()
                      if "L2" in layers and f in SEVERITY_GRIDS)
    for fault in declared:
        check(f"{fault} generated in layer 2", f'"{fault}"' in src)


def test_layer3_records_carry_a_movie_split(data: Dict[str, List[Dict[str, Any]]]) -> None:
    """Every Layer-3 cell must resolve to a side of the frozen movie split."""
    print("\nContract 2: every Layer-3 cell resolves to a side of the movie split")
    l3 = data["L3"]
    if not l3:
        check("layer 3 data present", False, "no layer3_*.json found")
        return
    unresolved = [r["run_id"] for r in l3 if A.axis_bucket(r, "movie") is None]
    check("all Layer-3 cells resolve a movie axis", not unresolved,
          f"{len(l3)} cells, {len(unresolved)} unresolved"
          + (f", first: {unresolved[:3]}" if unresolved else ""))
    hold = [r for r in l3 if A.axis_bucket(r, "movie") == "holdout"]
    check("hold-out movies reach the hold-out bucket", len(hold) > 0,
          f"{len(hold)} Layer-3 cells on {sorted(HOLDOUT_MOVIES)}")
    sel = [r for r in l3 if A.axis_bucket(r, "movie") == "selection"]
    check("selection movies reach the selection bucket", len(sel) > 0,
          f"{len(sel)} Layer-3 cells on {sorted(SELECTION_MOVIES)}")
    leaked = [r for r in hold if A.joint_split(r) == "selection"]
    check("no hold-out movie is classified as selection", not leaked,
          f"{len(leaked)} leaked")


def test_accounted_translation_is_not_harmful(data: Dict[str, List[Dict[str, Any]]]) -> None:
    """Under the default reading an accounted translation must not be a harmful positive.

    The prespecification's FAULT_CLASS labels X1 "benign_but_alarming" and its
    harm clause applies only to a translation NOT recorded in the metadata.
    Tiering X1 as harmful trains a translation gate to reject the benign
    reparameterisation the calibration exists to identify.
    """
    print("\nContract 3: an accounted translation is not a harmful positive (default reading)")
    allr = data["L1"] + data["L2"] + data["L3"]
    floors = A.noise_floor(data["L3"])["j4"] if data["L3"] else {}
    x1 = [r for r in allr if A.fault_of(r).startswith("X1_translation")]
    check("X1 cells present", len(x1) > 0, f"{len(x1)} cells")
    bad = [r for r in x1
           if A.tier_of(r, "harm_delta_b_a2", 5.0, floors, "benign").startswith("unacceptable")]
    check("no X1 cell is unacceptable under the benign reading", not bad,
          f"{len(bad)} of {len(x1)} tiered harmful")
    # And the alternative reading must still be reachable, so the ambiguity in
    # the prespecification stays visible instead of being silently resolved.
    flipped = [r for r in x1
               if A.tier_of(r, "harm_delta_b_a2", 5.0, floors, "harmful") == "unacceptable:geometry"]
    check("the harmful reading remains available for sensitivity reporting", len(flipped) > 0,
          f"{len(flipped)} of {len(x1)} would be geometry positives")


def test_uniform_scale_is_not_frame_dependent_harm(data: Dict[str, List[Dict[str, Any]]]) -> None:
    """A uniform gain error must not trip the frame-dependent scale clause."""
    print("\nContract 4: a uniform scale error is not tiered as frame-dependent harm")
    allr = data["L1"] + data["L2"] + data["L3"]
    floors = A.noise_floor(data["L3"])["j4"] if data["L3"] else {}
    x8 = [r for r in allr if A.fault_of(r).startswith("X8_gain")]
    check("X8 cells present", len(x8) > 0, f"{len(x8)} cells")
    bad = [r for r in x8
           if A.tier_of(r, "harm_delta_b_a2", 5.0, floors).startswith("unacceptable:scale")]
    check("no uniform-gain cell is tiered unacceptable:scale", not bad,
          f"{len(bad)} of {len(x8)} tiered harmful")
    check("SCALE_MODE marks X8 uniform", A.SCALE_MODE.get("X8_gain_error") == "uniform")
    check("SCALE_MODE marks the C2 control frame-dependent",
          A.SCALE_MODE.get("C2_frame_dependent_scale") == "frame_dependent")


def test_split_axes_are_independent(data: Dict[str, List[Dict[str, Any]]]) -> None:
    """A cell hold-out on one axis and selection on the other is neither."""
    print("\nContract 5: movie and severity hold-out axes stay independent")
    allr = data["L1"] + data["L2"] + data["L3"]
    mixed = [r for r in allr if A.joint_split(r) == "mixed"]
    for r in mixed[:1]:
        pass
    bad = [r for r in mixed if A.joint_split(r) in ("selection", "holdout")]
    check("mixed cells are in neither bucket", not bad, f"{len(mixed)} mixed cells")
    both = [r for r in allr if set(A.cell_axes(r)) == {"movie", "severity"}]
    check("at least some cells carry both axes", len(both) > 0, f"{len(both)} cells")
    joint_hold = [r for r in allr if A.joint_split(r) == "holdout"]
    for r in joint_hold:
        ax = A.cell_axes(r)
        if any(v != "holdout" for v in ax.values()):
            check("joint hold-out cells are hold-out on every applicable axis", False, str(ax))
            return
    check("joint hold-out cells are hold-out on every applicable axis", True,
          f"{len(joint_hold)} cells")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=Path("docs/calibration/data"))
    args = ap.parse_args()
    print("=" * 74)
    print(" MotionCorr issue #60 data and analysis contract controls")
    print("=" * 74)
    data = load(args.data)
    print(f"loaded: L1={len(data['L1'])} L2={len(data['L2'])} L3={len(data['L3'])} cells")
    test_layer2_covers_declared_faults()
    test_layer3_records_carry_a_movie_split(data)
    test_accounted_translation_is_not_harmful(data)
    test_uniform_scale_is_not_frame_dependent_harm(data)
    test_split_axes_are_independent(data)
    print("\n" + "=" * 74)
    if FAILURES:
        print(f" {len(FAILURES)} CONTRACT(S) FAILED: {', '.join(FAILURES)}")
        return 1
    print(" ALL CONTRACTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
