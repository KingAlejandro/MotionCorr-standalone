#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only reconciliation after a03; NEVER launches another GPU workload."""
import hashlib
import json
from pathlib import Path

import run_native as n

assert json.loads((n.ROOT / "exit.json").read_text())["status"] == "FAIL"
later = json.loads((n.ROOT / "later-controls/result.json").read_text())
early = json.loads((n.ROOT / "early-controls/result.json").read_text())
assert len(later) == 8 and all(row["passed"] for row in later)
assert len(early) == 9 and all(row["passed"] for row in early)
assert all(row["fixed_acceptance"] is True for row in later
           if row["label"].startswith("fixed-later-"))
assert all(row["fixed_acceptance"] is False for row in later
           if row["label"].startswith("mutant-later-"))
assert json.loads((n.ROOT / "later-controls.json").read_text())["exit"] == 0
assert json.loads((n.ROOT / "early-controls.json").read_text())["exit"] == 0
parsed = n.parse_health(n.ROOT / "post-xml.log")
n.save("post-recorded-health.json", dict(status="PASS", **parsed,
       note="Hardware fields in original post-run XML captured under original correctness lock. "
            "Original immediate-idle predicate remains FAIL: utilization 6%, memory 1 MiB, no apps."))
lock = n.lock("/tmp/motioncorr-gpu2-correctness.lock")
try:
    n.health("followup", require_idle=True)
finally:
    n.unlock(lock)
built = Path("/mnt/clathrin/motioncorr-215-native-20261022-409be643-a01")
binaries = json.loads((built / "binaries.json").read_text())
for name, digest in binaries.items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest
n.save("reconciliation.json", dict(utc=n.utc(), original_driver_status="FAIL",
       original_idle_check="FAIL (6% sampled utilization, 1 MiB, no assigned-GPU apps)",
       original_recorded_hardware_health="PASS", followup_idle_and_health="PASS",
       later_rows_passed=8, early_rows_passed=9, binary_rehash="PASS", binaries=binaries,
       additional_gpu_workloads=0, gate_waivers=0,
       note="Native test subprocesses both exited 0. No original receipt or verdict was overwritten."))
print("PASS: 8 later rows + 9 early rows; original hardware XML healthy; fresh idle/health PASS; original driver FAIL retained")
