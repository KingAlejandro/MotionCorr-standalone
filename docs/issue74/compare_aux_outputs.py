#!/usr/bin/env python3
"""Issue #74: compare the per-movie outputs that the exactness gate does not read.

`compare24.py` + `tools/compare_motioncorr.py --gate exact` cover the scientific
payload: MRC pixels, MRC headers and the per-movie STAR trajectories. That is the
verdict that matters, and this script does not second-guess it.

What it adds is coverage of the *rest* of the per-movie output array, so that
"complete per-movie output arrays" is an actual check and not an assertion:

  * `corrected_micrographs.star`  - the top-level result table (path-normalised)
  * `*_shifts.eps`               - the rendered trajectory (date-normalised)
  * `*.log`                      - every line except the ones that are legitimately
                                   expected to differ

The log comparison is the interesting one. Detailed CUDA event profiling is exactly
the thing under test, so its lines must be allowed to differ between the two
candidate modes; everything else in the log - hot pixel counts, per-iteration RMSD,
patch geometry, polynomial fit RMSD, the FFT plan sizes, and the
`[CUDA ...] completed; converged=` execution marker - must be byte-identical.
Wall-clock lines are dropped because they are timings, not results.

Exit status is 0 only if every file matched. Missing files are failures.
"""

import argparse
import re
import sys
from pathlib import Path

# Lines whose value is a duration: never comparable between two runs.
TIMING_VARIABLE = [
    r"Custom kernel execution time:",
    r"cuFFT execution time:",
    r"Device-to-Host transfer time:",
    r"Total GPU alignment time:",
    r"Dose Weighting Kernel:",
    r"cuFFT C2R Execution:",
    r"Interpolation & Accum:",
    r"Total DW Reconstruction Time:",
    r"Total Unweighted Reconstruction Time:",
    r"Full movie wall time:",
]

# Lines that differ *by design* between detailed-profiling on and off.
MODE_DEPENDENT = [
    r"Detailed event profiling:",
]

# Lines whose label text this branch corrects (issue #74 item 3). Only dropped
# when comparing against a pre-change baseline binary.
LABEL_CHANGED = [
    r"Host-to-Device transfer time:",
    r"Buffer VRAM:",
    r"Peak GPU memory allocated:",
    r"Peak VRAM:",
]

EPS_VOLATILE = re.compile(r"^%%(CreationDate|Creator|Title|For|BoundingBox\s*:\s*\(atend\)).*$")


def compile_drop(patterns):
    return re.compile("|".join(patterns))


def normalise_paths(text, ref_dir, test_dir):
    for d in (str(ref_dir.resolve()), str(test_dir.resolve()), str(ref_dir), str(test_dir)):
        text = text.replace(d.rstrip("/"), "<OUTDIR>")
    return text


def filtered_lines(path, drop, ref_dir, test_dir):
    text = normalise_paths(path.read_text(errors="replace"), ref_dir, test_dir)
    return [ln for ln in text.splitlines() if not drop.search(ln)]


def eps_lines(path, ref_dir, test_dir):
    text = normalise_paths(path.read_text(errors="replace"), ref_dir, test_dir)
    return [ln for ln in text.splitlines() if not EPS_VOLATILE.match(ln)]


def first_difference(a, b):
    for i, (x, y) in enumerate(zip(a, b), start=1):
        if x != y:
            return f"line {i}: ref={x!r} test={y!r}"
    if len(a) != len(b):
        longer, which = (a, "ref") if len(a) > len(b) else (b, "test")
        return f"{which} has {abs(len(a) - len(b))} extra line(s), first: {longer[min(len(a), len(b))]!r}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--allow-label-changes", action="store_true",
                    help="Also ignore the profile lines whose label text issue #74 corrects. "
                         "Use only when the reference was produced by a pre-change binary.")
    ap.add_argument("--report")
    a = ap.parse_args()

    ref, test = Path(a.ref), Path(a.test)
    drop = compile_drop(TIMING_VARIABLE + MODE_DEPENDENT +
                        (LABEL_CHANGED if a.allow_label_changes else []))

    results = []
    npass = nfail = nskip = 0

    for rp in sorted(ref.rglob("*")):
        if rp.is_dir():
            continue
        rel = rp.relative_to(ref)
        tp = test / rel
        name = rp.name

        if name.endswith(".mrc") or (name.endswith(".star") and name != "corrected_micrographs.star"):
            nskip += 1
            results.append((str(rel), "COVERED_BY_GATE_C", "pixels/headers/trajectory compared by compare_motioncorr.py --gate exact"))
            continue
        if name.endswith((".pdf", ".lst")):
            nskip += 1
            results.append((str(rel), "EXCLUDED", "ghostscript embeds a creation timestamp"))
            continue

        if not tp.exists():
            nfail += 1
            results.append((str(rel), "FAIL", "missing in test tree"))
            continue

        if name.endswith(".eps"):
            diff = first_difference(eps_lines(rp, ref, test), eps_lines(tp, ref, test))
            kind = "eps (date-normalised)"
        elif name.endswith(".log"):
            diff = first_difference(filtered_lines(rp, drop, ref, test),
                                    filtered_lines(tp, drop, ref, test))
            kind = "log (timing/profile lines dropped)"
        elif name == "corrected_micrographs.star":
            diff = first_difference(
                normalise_paths(rp.read_text(), ref, test).splitlines(),
                normalise_paths(tp.read_text(), ref, test).splitlines())
            kind = "star (path-normalised)"
        else:
            diff = None if rp.read_bytes() == tp.read_bytes() else "bytes differ"
            kind = "bytes"

        if diff is None:
            npass += 1
            results.append((str(rel), "PASS", kind))
        else:
            nfail += 1
            results.append((str(rel), "FAIL", f"{kind}: {diff}"))

    width = max((len(r[0]) for r in results), default=10)
    lines = [f"ref  = {ref}", f"test = {test}",
             f"allow_label_changes = {a.allow_label_changes}", ""]
    for rel, status, detail in results:
        lines.append(f"{status:<18} {rel:<{width}}  {detail}")
    lines += ["", f"compared={npass} failed={nfail} skipped={nskip}"]
    verdict = "PASS" if nfail == 0 and npass > 0 else "FAIL"
    if npass == 0:
        verdict, lines[-1] = "FAIL", lines[-1] + "  (nothing was actually compared)"
    lines.append(f"AUX OUTPUT COMPARISON: {verdict}")

    out = "\n".join(lines)
    print(out)
    if a.report:
        Path(a.report).write_text(out + "\n")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
