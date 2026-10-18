#!/usr/bin/env python3
"""Probe: the ported #123 matrix rejects every host-fallback literal the original rejected.

Feeds assert_witnesses() synthetic per-movie logs that carry every required witness and the
`compact` route record, plus at most one fallback line. Expected: the clean log is accepted
(control), and logs with the original NO_SESSION literal, the original uint16 MATERIALIZED
literal, or a main-era int16 "Materialized native" line are each rejected.

  QF_W=... ~/.mc-venv/bin/python3 tools/probe_matrix_fallback_witness.py [path/to/run_compact_ingest_support_matrix.py]
Exit 0 only if every expectation holds. Passing the pre-revision harness shows which literal it missed.
"""
import importlib.util
import sys
from pathlib import Path

target = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent / "run_compact_ingest_support_matrix.py")
sys.path.insert(0, str(target.resolve().parent))
spec = importlib.util.spec_from_file_location("matrix_under_probe", target)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(m)

MOVIE = "Movies/mov00_g1_64x48x6.tiff"
BASE = "\n".join([
    m.STAGED + "; the integer to float expansion ...",
    m.SESSION_READY + " ...",
    " [CUDA Dose-Weighted " + m.RESIDENT_RECON,
    m.RELEASED,
])
CASES = {
    "clean (control, must be accepted)": (BASE, True),
    "original NO_SESSION literal": (BASE + "\nNo resident CUDA session; widening the native uint16 movie to float.", False),
    "original uint16 MATERIALIZED literal": (BASE + "\nMaterialized native uint16 frames as float for CPU fallback.", False),
    "main int16 Materialized line": (BASE + "\nMaterialized native int16 frames as float for CPU fallback.", False),
}
ok = True
for name, (log, accept) in CASES.items():
    arm = m.ArmResult("probe", Path("/nonexistent"), 0, "", "", {f"Movies/{Path(MOVIE).stem}.log": log},
                      {"ingest_witness": [f"{MOVIE} compact"]})
    try:
        m.assert_witnesses(arm, expect_u16=True, movies=[MOVIE])
        accepted, why = True, ""
    except m.CaseFailure as exc:
        accepted, why = False, str(exc)
    good = accepted == accept
    ok &= good
    print(f"{'ok ' if good else 'BAD'} {name}: {'accepted' if accepted else 'rejected (' + why + ')'}")
print("PROBE", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
