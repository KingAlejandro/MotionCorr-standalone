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
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import star_io  # noqa: E402


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def report_identifier(rel_root: str) -> str:
    """A filename that is injective in the complete output root.

    Substituting separators is not enough: "a/b" and "a__b" both become "a__b",
    so the second comparison overwrites the first report and a later --reuse
    reads one movie's result for both -- turning a genuine fail-then-pass pair
    into a false 2/2 PASS. The readable part is therefore only a label, and the
    identity comes from a digest of the exact root.
    """
    # surrogatepass: os.scandir yields surrogate escapes for filenames that are
    # not valid UTF-8, and a plain encode would abort the whole comparator with
    # a traceback instead of recording a FAIL for that one movie.
    digest = hashlib.sha256(rel_root.encode("utf-8", "surrogatepass")).hexdigest()[:16]
    label = _SAFE.sub("_", rel_root).strip("_")[-60:] or "root"
    return f"{label}-{digest}"


def root_sidecar(report_path: Path) -> Path:
    return report_path.with_suffix(".origin.json")


def origin_record(rel: str, ref: Path, test: Path, tool: str,
                  files: list[Path]) -> dict[str, object]:
    """What a report must still describe for --reuse to accept it.

    The root alone is not enough: a report produced for root X against one pair
    of trees would otherwise be accepted as the verdict for root X against
    completely different trees, so a passing run could be reused to certify
    inputs it never saw. Pin the resolved trees, the comparator, and each input
    file's size and mtime.
    """
    stat = {}
    for f in files:
        try:
            st = f.stat()
            stat[str(f)] = [st.st_size, int(st.st_mtime_ns)]
        except OSError:
            stat[str(f)] = None
    # The comparator's path is not its identity. Replacing tools/compare_motioncorr.py
    # in place, or resolving the same relative string to a different file, leaves the
    # recorded string unchanged, so --reuse would certify checks the current
    # comparator never performed. Pin the resolved path and its contents.
    tool_path = Path(tool).resolve()
    try:
        tool_sha = hashlib.sha256(tool_path.read_bytes()).hexdigest()
    except OSError:
        tool_sha = None
    return {"root": rel, "ref": str(ref), "test": str(test), "tool": str(tool_path),
            "tool_sha256": tool_sha, "inputs": stat}


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

    ref, test, out = Path(a.ref).resolve(), Path(a.test).resolve(), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    if a.manifest:
        manifest = json.loads(Path(a.manifest).read_text())
        roots = list(manifest["canonical_output_roots"])
        expect = len(roots)
        if expect == 0:
            print("FAIL: manifest lists no movies; a zero-pair comparison cannot pass",
                  file=sys.stderr)
            return 2
        normalized = [star_io.worker_relative_root(r) for r in roots]
        if len(set(normalized)) != len(normalized):
            dupes = sorted({n for n in normalized if normalized.count(n) > 1})
            print(f"FAIL: manifest roots are not distinct after normalization: {dupes}; "
                  "one product pair would be compared for two movies", file=sys.stderr)
            return 2
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
        report_id = report_identifier(rel)
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
            # Independently of the filename encoding, a reused report must
            # carry the root it was produced for. Without this, any future
            # change to the identifier silently reintroduces cross-reads.
            side = root_sidecar(j)
            if not side.exists():
                results.append({"movie": name, "root": root, "gate_c_pass": False,
                                "reason": f"--reuse but no origin sidecar at {side}; "
                                          "report identity cannot be validated"})
                continue
            try:
                recorded = json.loads(side.read_text())
            except Exception as exc:  # noqa: BLE001
                results.append({"movie": name, "root": root, "gate_c_pass": False,
                                "reason": f"--reuse but unreadable sidecar {side}: {exc}"})
                continue
            expected = origin_record(rel, ref, test, a.tool, [rm, tm, rs, ts])
            if recorded != expected:
                differing = sorted(k for k in set(recorded) | set(expected)
                                   if recorded.get(k) != expected.get(k))
                results.append({"movie": name, "root": root, "gate_c_pass": False,
                                "reason": f"--reuse origin mismatch for {j}: "
                                          f"{differing} differ from the run that "
                                          "produced it"})
                continue
            rc = 0
        else:
            # Remove any earlier report and its sidecar FIRST. A comparator that
            # exits before writing --json-out leaves the previous run's report in
            # place; writing the sidecar unconditionally afterwards would bind that
            # stale verdict to the new inputs, and a later --reuse -- whose rc is 0
            # by construction -- would accept it as a pass for inputs it never saw.
            j.unlink(missing_ok=True)
            root_sidecar(j).unlink(missing_ok=True)
            cp = subprocess.run(
                [a.python, a.tool, "--ref-mrc", str(rm), "--test-mrc", str(tm),
                 "--ref-star", str(rs), "--test-star", str(ts),
                 "--gate", "exact", "--json-out", str(j)],
                capture_output=True, text=True)
            rc = cp.returncode
            if not j.exists():
                results.append({"movie": name, "root": root, "gate_c_pass": False,
                                "returncode": rc,
                                "reason": f"comparator produced no report at {j} "
                                          f"(exit {rc}); no sidecar published"})
                continue
            root_sidecar(j).write_text(
                json.dumps(origin_record(rel, ref, test, a.tool, [rm, tm, rs, ts]),
                           indent=2, sort_keys=True) + "\n")

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
            # compare_motioncorr.py emits these as "rmse" (tools/compare_motioncorr.py:279)
            # and "num_differences" (:398). Reading the wrong name records None,
            # which reads as "no differences" in the summary.
            "image_rmse": img.get("rmse"),
            "coverage_complete": (d.get("coverage", {}) or {}).get("complete"),
            "star_diffs": stars.get("num_differences"),
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
    # A zero-pair comparison is not a pass. An empty manifest would otherwise
    # satisfy "no failures and passed == expected" with nothing compared.
    verdict = "PASS" if (expect > 0 and nfail == 0 and npass == expect) else "FAIL"
    summary = {
        "n_expected": expect, "n_compared": len(results),
        "passed": npass, "failed": nfail, "verdict": verdict,
        "criterion": "at least one pair, every movie pixel-identical with complete "
                     "coverage, and the trajectory and STAR checks each passed; a PASS "
                     "overall_status alone is not sufficient",
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
