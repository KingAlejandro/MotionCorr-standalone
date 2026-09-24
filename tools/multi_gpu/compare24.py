#!/usr/bin/env python3
"""Gate C: 24/24 exact comparison, serial-CUDA vs parallel-CUDA.

Deliberately does NOT hash whole MRC files: RELION stamps a date/time into the
MRC label and ghostscript embeds dates in the PDF, so whole-file hashes differ
between runs that are scientifically identical. compare_motioncorr.py normalises
the timestamp label and compares the pixel payload, so that is the only valid
exactness check here.
"""
import argparse, json, subprocess, sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True); ap.add_argument("--test", required=True)
    ap.add_argument("--tool", required=True); ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ref, test, out = Path(a.ref), Path(a.test), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    mrcs = sorted(p for p in ref.rglob("*.mrc")
                  if not p.name.endswith(("_PS.mrc", "_EVN.mrc", "_ODD.mrc", "_noDW.mrc"))
                  and p.name != "gain.mrc")
    if not mrcs:
        print("FAIL: no reference MRCs found"); return 2

    results, npass, nfail = [], 0, 0
    for rm in mrcs:
        rel = rm.relative_to(ref); tm = test / rel
        rs, ts = rm.with_suffix(".star"), tm.with_suffix(".star")
        missing = [str(p) for p in (tm, rs, ts) if not p.exists()]
        if missing:
            nfail += 1; results.append({"movie": rel.name, "status": "FAIL",
                                        "reason": "missing: " + ", ".join(missing)}); continue
        j = out / (rel.name.replace(".mrc", "") + "_exact.json")
        cp = subprocess.run([a.python, a.tool, "--ref-mrc", str(rm), "--test-mrc", str(tm),
                             "--ref-star", str(rs), "--test-star", str(ts),
                             "--gate", "exact", "--json-out", str(j)],
                            capture_output=True, text=True)
        rec = {"movie": rel.name, "returncode": cp.returncode}
        try:
            d = json.loads(j.read_text())
            ci = d.get("checks", {}).get("corrected_image", {}) or {}
            # NB: the comparator's top-level verdict key is "overall_status",
            # not "status". Reading the wrong key yields None, which silently
            # fails every movie even when all of them are pixel-identical.
            rec.update({
                "status": d.get("overall_status"),
                "pixel_identical": ci.get("pixel_identical"),
                "image_rmse": ci.get("image_rmse"),
                "coverage_complete": d.get("coverage", {}).get("complete"),
                "star_diffs": (d.get("checks", {}).get("star_fields", {}) or {}).get("difference_count"),
                "max_shift_error": (d.get("checks", {}).get("motion_trajectory", {}) or {}).get("max_shift_error"),
            })
        except Exception as e:
            rec.update({"status": "ERROR", "reason": f"unreadable report: {e}",
                        "stderr": cp.stderr[-400:]})
        # fail closed: exact parity requires all four, not merely status==PASS
        checks = d.get("checks", {}) if isinstance(locals().get("d"), dict) else {}
        ok = (rec.get("status") == "PASS" and rec.get("returncode") == 0
              and rec.get("pixel_identical") is True and rec.get("coverage_complete") is True
              and (checks.get("motion_trajectory", {}) or {}).get("passed") is True
              and (checks.get("star_fields", {}) or {}).get("passed") is True)
        rec["gate_c_pass"] = ok
        npass += ok; nfail += (not ok)
        results.append(rec)

    summary = {"n_movies": len(mrcs), "passed": npass, "failed": nfail,
               "gate_c": "PASS" if (nfail == 0 and npass == 24) else "FAIL",
               "note": "requires exactly 24 movies all pixel_identical with complete coverage",
               "results": results}
    (out / "gate_c_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("n_movies","passed","failed","gate_c")}, indent=2))
    for r in results:
        if not r.get("gate_c_pass"):
            print("  FAIL", r.get("movie"), r.get("reason") or r.get("status"), "pixel_identical=", r.get("pixel_identical"))
    return 0 if summary["gate_c"] == "PASS" else 1

sys.exit(main())
