#!/usr/bin/env python3
"""Content pins (git blob id and sha256) for every file the tiny-tier admission relies on.

    python3 -I make_pins.py > PINS.json        (run from anywhere inside the repository)
"""
import hashlib, json, subprocess
from pathlib import Path

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
D = "docs/post_rc0/ccf_dc_native_compat_20261026/"
GROUPS = {
    "production_and_build": ["src/experiment_ccf_dc.h", "src/motioncorr_runner.cpp", "src/acc/cuda/cuda_alignpatch.cu", "CMakeLists.txt"],
    "tests": ["tests/experiment_ccf_dc_stage.cpp", "tests/test_ccf_dc_request.py", "tools/test_ccf_dc_tap_field.py",
              "tools/test_ccf_dc_native_rows.py"],
    "consumers_new": ["tools/ccf_dc_tap_field.py", "tools/ccf_dc_native_rows.py", "test-data/generate_ccf_dc_n_controls.py"],
    "stage_c_draft": ["tools/ccf_dc_stagec_driver.py", "tools/stageC_guard.sh", "tools/test_ccf_dc_stagec_driver.py",
                      "tools/test_ccf_dc_stagec_guard.py", "tools/test_ccf_dc_stagec_lifecycle.py", "tools/test_ccf_dc_stagec_seal.py",
                      "tools/stageC_ldd_preflight.sh", D + "evidence/stageC/PLAN_AMENDMENT_2.md", D + "review/STAGEC_R1_REPORT.md",
                      D + "evidence/stageC/STAGEC_PINS.26e74d8a.json",
                      D + "evidence/stageC/PLAN_AMENDMENT_1.md", D + "evidence/stageC/STAGEC_PINS.b7935fd5.json",
                      D + "evidence/stageC/STAGEC_PINS.json", D + "evidence/stageC/make_stagec_pins.py", D + "evidence/stageC/DRIVER_PLAN.md"],
    "scorers_and_math_unchanged": ["tools/check_motion_diagnostics.py", "tools/check_realistic_motion.py", "tools/motion_field.py",
                                   "test-data/generate_motion_diagnostics.py", "test-data/generate_known_motion_fixture.py"],
    "plan_and_ledger": [D + f for f in ("DESIGN.md", "CONTROL_PLAN.md", "make_ledger.py", "ledger.csv", "pairs.csv", "repro.csv", "counts.json",
                                        "review/ROUND1_REPORT.md", "review/ROUND1_RESPONSE.md",
                                        "review/ROUND2_REPORT.md", "review/ROUND2_RESPONSE.md",
                                        "review/ROUND3_REPORT.md", "review/ROUND3_RESPONSE.md")],
    "retained_references": [D + "evidence/retained_render_report.json", D + "evidence/retained_cpu_reference.json",
                            D + "evidence/retained_n_runs/INDEX.json"],
}


def pin(rel):
    p = ROOT / rel
    return dict(path=rel, git_blob=subprocess.check_output(["git", "hash-object", str(p)], text=True).strip(),
                sha256=hashlib.sha256(p.read_bytes()).hexdigest())


print(json.dumps({g: [pin(f) for f in fs] for g, fs in GROUPS.items()}, indent=1))
