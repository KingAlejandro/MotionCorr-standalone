#!/usr/bin/env python3
"""Issue #74: decide the CUDA execution witness from backend evidence alone.

`run_known_motion_gates.py` returns a single aggregate exit status that mixes two
very different things: whether the run executed on the requested backend, and
whether the motion estimator met its accuracy gates. Historical CPU accuracy
failures are still failures and are not this issue's business to hide or to fix.

This issue's question is narrower and must not be answered by that exit status:

    with detailed event profiling OFF, does the code still demonstrably start
    and complete on the GPU, and is that demonstration something a CPU run
    cannot produce?

So read `backend_evidence` out of the aggregate JSON and judge only that.

  --expect cuda  every run must show BOTH the startup marker and the completion
                 marker. Exit status and case accuracy are ignored.
  --expect cpu   every run must show NO CUDA marker at all, and must still have
                 completed. This is the masquerade control: it is what makes the
                 markers a witness rather than a string that happens to be
                 printed. It is reported separately from accuracy on purpose.

Also reports any case whose status is ERROR, because `run_case` raises ERROR
when the backend evidence is incomplete, and that must never be silently lost.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--expect", choices=("cuda", "cpu"), required=True)
    ap.add_argument("--report")
    a = ap.parse_args()

    doc = json.loads(Path(a.json).read_text())
    results = doc["results"] if isinstance(doc, dict) and "results" in doc else doc
    if isinstance(results, dict):
        results = results.get("results", [])

    lines = [f"source  = {a.json}", f"expect  = {a.expect}", ""]
    nrun = nbad = 0
    errors = []

    for r in results:
        case = r.get("case", "?")
        if r.get("status") == "ERROR":
            errors.append(f"{case}: ERROR: {r.get('reason', '')[:200]}")
        for tag, run in (r.get("runs") or {}).items():
            ev = run.get("backend_evidence") or {}
            nrun += 1
            if a.expect == "cuda":
                ok = (ev.get("requested") == "cuda"
                      and ev.get("startup_marker_found") is True
                      and ev.get("completion_marker_found") is True)
                detail = (f"requested={ev.get('requested')} "
                          f"startup={ev.get('startup_marker_found')} "
                          f"completion={ev.get('completion_marker_found')}")
            else:
                ok = (ev.get("requested") == "cpu"
                      and ev.get("unexpected_cuda_marker") is False
                      and ev.get("movie_completed") is True)
                detail = (f"requested={ev.get('requested')} "
                          f"unexpected_cuda_marker={ev.get('unexpected_cuda_marker')} "
                          f"movie_completed={ev.get('movie_completed')}")
            if not ok:
                nbad += 1
            lines.append(f"{'ok  ' if ok else 'BAD '} {case:24s} {tag:6s} {detail}")

    lines.append("")
    if errors:
        lines.append("cases reported ERROR by the gate runner (backend evidence is "
                     "load-bearing inside it, so these matter):")
        lines += ["  " + e for e in errors]
        lines.append("")
    lines.append(f"runs_checked={nrun} bad={nbad} errored_cases={len(errors)}")

    verdict = "PASS" if nrun > 0 and nbad == 0 and not errors else "FAIL"
    if nrun == 0:
        lines[-1] += "  (no runs found in the report)"
    if a.expect == "cuda":
        lines.append(f"CUDA EXECUTION WITNESS: {verdict}")
    else:
        lines.append(f"CPU MASQUERADE REJECTION: {verdict}")
    lines.append("This verdict is about the backend only. It says nothing about "
                 "estimator accuracy gates, which are reported separately and "
                 "whose historical failures remain failures.")

    out = "\n".join(lines)
    print(out)
    if a.report:
        Path(a.report).write_text(out + "\n")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
