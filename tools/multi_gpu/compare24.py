#!/usr/bin/env python3
"""Per-movie exact comparison of a sharded run against a serial baseline.

Salvaged from the #53 prototype (PR55) onto current main. Two things it will not
do, both deliberate:

  * It does not hash whole MRC or PDF files. RELION stamps a timestamp into the
    MRC label and ghostscript embeds dates in the PDF, so two scientifically
    identical runs differ byte for byte at the file level.
    tools/compare_motioncorr.py normalizes the label and compares the pixel
    payload, so that is the only valid exactness check here.
  * It does not compare directories in one call. discover_output_files() hard
    fails on a directory holding several corrected MRCs, so the comparator is
    invoked once per movie.

Fail-closed verdict. `overall_status == "PASS"` alone is not accepted: exact
equivalence also requires pixel_identical, complete coverage, and the trajectory
and STAR checks each individually passed. The comparator's top-level verdict key
is `overall_status`, not `status`; reading the wrong key yields None and would
silently fail every movie even when all are pixel-identical.

The movie set is taken from the partition manifest, not from globbing the
reference tree, so a reference directory that is itself missing a movie is a
failure rather than a smaller passing set.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import star_io  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", required=True, help="serial baseline output tree")
    ap.add_argument("--test", required=True, help="sharded/merged output tree")
    ap.add_argument("--tool", required=True, help="path to tools/compare_motioncorr.py")
    ap.add_argument("--manifest", default=None,
                    help="partition manifest; its canonical movie list defines the "
                         "expected set (preferred over --expect)")
    ap.add_argument("--expect", type=int, default=None,
                    help="required movie count when no manifest is given")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reuse", action="store_true",
                    help="re-aggregate existing per-movie reports instead of re-running "
                         "the comparator; the comparisons are unchanged, only this "
                         "script's verdict logic is recomputed. Fails if one is missing.")
    a = ap.parse_args(argv)

    ref, test, out = Path(a.ref), Path(a.test), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    if a.manifest:
        manifest = json.loads(Path(a.manifest).read_text())
        roots = list(manifest["canonical_output_roots"])
        expect = len(roots)
    else:
        roots = sorted(
            str(p.relative_to(ref).with_suffix(""))  # already worker-relative
            for p in ref.rglob("*.mrc")
            if not p.name.endswith(("_PS.mrc", "_EVN.mrc", "_ODD.mrc", "_noDW.mrc"))
            and p.name != "gain.mrc")
        expect = a.expect if a.expect is not None else len(roots)
        if not roots:
            print("FAIL: no reference MRCs found and no manifest given", file=sys.stderr)
            return 2

    results, npass = [], 0
    for root in roots:
        rel = star_io.worker_relative_root(root)
        rm, tm = ref / (rel + ".mrc"), test / (rel + ".mrc")
        rs, ts = ref / (rel + ".star"), test / (rel + ".star")
        name = Path(rel).name
        # Key the report by the COMPLETE root, not the basename. Movies/set1/a and
        # Movies/set2/a both end in "a": keying on the basename makes the second
        # comparison overwrite the first report, and a later --reuse then reads one
        # movie's report for both -- turning a real fail-then-pass pair into a
        # false 2/2 exact PASS.
        report_id = rel.replace("/", "__").replace("\\", "__")
        missing = [str(p) for p in (rm, tm, rs, ts) if not p.exists()]
        if missing:
            results.append({"movie": name, "root": root, "gate_c_pass": False,
                            "reason": "missing: " + ", ".join(missing)})
            continue

        j = out / (report_id + "_exact.json")
        if a.reuse:
            if not j.exists():
                results.append({"movie": name, "root": root, "gate_c_pass": False,
                                "reason": f"--reuse but no report at {j}"})
                continue
            rc = 0
        else:
            cp = subprocess.run(
                [a.python, a.tool, "--ref-mrc", str(rm), "--test-mrc", str(tm),
                 "--ref-star", str(rs), "--test-star", str(ts),
                 "--gate", "exact", "--json-out", str(j)],
                capture_output=True, text=True)
            rc = cp.returncode

        rec: dict[str, object] = {"movie": name, "root": root, "report": j.name,
                                  "returncode": rc}
        try:
            d = json.loads(j.read_text())
        except Exception as exc:  # noqa: BLE001
            rec.update({"gate_c_pass": False, "reason": f"unreadable report: {exc}"})
            results.append(rec)
            continue

        checks = d.get("checks", {}) or {}
        img = checks.get("corrected_image", {}) or {}
        traj = checks.get("motion_trajectory", {}) or {}
        stars = checks.get("star_fields", {}) or {}
        rec.update({
            "overall_status": d.get("overall_status"),
            "pixel_identical": img.get("pixel_identical"),
            "image_rmse": img.get("image_rmse"),
            "coverage_complete": (d.get("coverage", {}) or {}).get("complete"),
            "star_diffs": stars.get("difference_count"),
            "max_shift_error": traj.get("max_shift_error"),
        })
        rec["gate_c_pass"] = (
            rc == 0
            and d.get("overall_status") == "PASS"
            and img.get("pixel_identical") is True
            and (d.get("coverage", {}) or {}).get("complete") is True
            and traj.get("passed") is True
            and stars.get("passed") is True)
        npass += bool(rec["gate_c_pass"])
        results.append(rec)

    nfail = len(results) - npass
    verdict = "PASS" if (nfail == 0 and npass == expect) else "FAIL"
    summary = {
        "n_expected": expect, "n_compared": len(results),
        "passed": npass, "failed": nfail, "verdict": verdict,
        "criterion": "every movie pixel-identical with complete coverage, and the "
                     "trajectory and STAR checks each passed; a PASS overall_status "
                     "alone is not sufficient",
        "excluded": "logfile.pdf -- path-dependent by construction, see #53 section 6.3",
        "results": results,
    }
    (out / "exact_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in
                      ("n_expected", "n_compared", "passed", "failed", "verdict")},
                     indent=2))
    for r in results:
        if not r.get("gate_c_pass"):
            print("  FAIL", r.get("movie"), r.get("reason") or r.get("overall_status"),
                  "pixel_identical=", r.get("pixel_identical"), file=sys.stderr)
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
