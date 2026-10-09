#!/usr/bin/env python3
"""tools/run_cuda_patch_validation.py must recognise the profile blocks that
src/acc/cuda/cuda_alignpatch.cu actually writes, in both formats:

- timed (--profile): per-kernel lines, with "(Resident VRAM)" after the H2D time;
- untimed (default since #159): "Per-kernel timing: not measured";
- batched patch alignment (#160): "Batched alignment: N patches together".

The block text below is assembled from the literal strings in the source, so
a change to either side that breaks the GPU-execution gate fails here instead
of only on a native validation run. An empty log must still fail the gate.
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validation", ROOT / "tools" / "run_cuda_patch_validation.py")
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)

source = (ROOT / "src" / "acc" / "cuda" / "cuda_alignpatch.cu").read_text()
# Literal log strings as emitted by the source (fail if any disappears).
needed = {
    "h2d": '"   Host-to-Device transfer time: 0.00 ms (Resident VRAM)"',
    "kernel": '"   Custom kernel execution time: "',
    "cufft": '"   cuFFT execution time:         "',
    "d2h": '"   Device-to-Host transfer time: "',
    "untimed": '"   Per-kernel timing:            not measured (enable with --profile)"',
    "batched": '"   Batched alignment:            "',
    "batched_tail": '" patches together; time and VRAM below are for all of them"',
    "total": '"   Total GPU alignment time:     "',
    "buf": '"   Buffer VRAM:                  "',
    "ws": '"   cuFFT workspace VRAM:         "',
    "peak": '"   Peak GPU memory allocated:    "',
}
failures = []
for key, lit in needed.items():
    if lit not in source:
        failures.append(f"source no longer emits {lit}")


def unq(lit):
    return lit.strip('"')


def block(stage, timed, batch=None):
    lines = [f" [CUDA {stage} Profile]"]
    if batch:
        lines += [unq(needed["batched"]) + str(batch) + unq(needed["batched_tail"])]
    elif timed:
        lines += [unq(needed["h2d"]), unq(needed["kernel"]) + "3.21 ms",
                  unq(needed["cufft"]) + "1.10 ms", unq(needed["d2h"]) + "0.40 ms"]
    else:
        lines += [unq(needed["untimed"])]
    lines += [unq(needed["total"]) + "5.00 ms", unq(needed["buf"]) + "10.00 MiB",
              unq(needed["ws"]) + "2.00 MiB", unq(needed["peak"]) + "12.00 MiB"]
    return "\n".join(lines) + "\n"


ok = {"overall_status": "PASS", "comparator_exit_code": 0, "gpu_startup": 0,
      "checks": {n: {"passed": True} for n in ("motion_trajectory", "corrected_image", "star_fields")},
      "coverage": {"complete": True}}
for timed in (True, False):
    log = block("Global Alignment", timed) + block("Patch Alignment", timed) * 9
    t = validation.parse_telemetry(log)
    label = "timed" if timed else "untimed"
    if t["global_profile"] is None or t["num_patch_profiles"] != 9:
        failures.append(f"{label}: parsed global={t['global_profile'] is not None} patches={t['num_patch_profiles']}")
        continue
    if timed and t["global_profile"]["kernel"] != 3.21:
        failures.append("timed: per-kernel value lost")
    if not timed and t["global_profile"]["kernel"] is not None:
        failures.append("untimed: per-kernel value fabricated")
    if not validation.stage_result(dict(ok, telemetry=t), 9, 0)["gpu_execution_pass"]:
        failures.append(f"{label}: gpu_execution_pass false on a complete log")
# Default path: per-call global block, then 9 patches batched together. Each
# patch block repeats the batch total (5.00 ms), which must be counted once.
t = validation.parse_telemetry(block("Global Alignment", False) + block("Patch Alignment", False, 9) * 9)
if t["num_patch_profiles"] != 9:
    failures.append(f"batched: parsed patches={t['num_patch_profiles']}")
elif not validation.stage_result(dict(ok, telemetry=t), 9, 0)["gpu_execution_pass"]:
    failures.append("batched: gpu_execution_pass false on a complete log")
elif abs(t["total_patch_gpu_ms"] - 5.0) > 1e-9 or t["patch_profiles"][0]["batch"] != 9:
    failures.append(f"batched: total_patch_gpu_ms={t['total_patch_gpu_ms']} batch={t['patch_profiles'][0]['batch']}")
if validation.stage_result(dict(ok, telemetry=validation.parse_telemetry("")), 9, 0)["gpu_execution_pass"]:
    failures.append("empty log passes the GPU-execution gate")

for f in failures:
    print("FAIL", f)
print("PASS" if not failures else f"{len(failures)} FAILURE(S)")
sys.exit(1 if failures else 0)
