#!/usr/bin/env python3
"""Measure peak device memory for one declared configuration.

Issue #83 asks for memory contracts to be *measured* wherever a capacity claim
is made. This produces exactly one datapoint: the peak device memory observed
while a single declared row runs on a single device.

It deliberately does not sweep sizes, provoke exhaustion or inject allocation
faults -- that is #69. It also makes no fallback claim: the row's exit status
is recorded as-is and is never read as evidence of a CPU fallback.

The sampler reads ``nvidia-smi --query-compute-apps``, so it observes real
device usage rather than anything the program reports about itself.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def device_total_mib(device: int) -> Optional[int]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits",
             "-i", str(device)],
            capture_output=True, text=True, check=True).stdout.strip()
        return int(out.splitlines()[0])
    except (subprocess.CalledProcessError, ValueError, IndexError, FileNotFoundError):
        return None


def sample_used_mib(device: int) -> Optional[int]:
    """Total memory used by compute apps on this device, in MiB."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=used_memory",
             "--format=csv,noheader,nounits", "-i", str(device)],
            capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    total = 0
    for line in out.splitlines():
        line = line.strip()
        if line and line.isdigit():
            total += int(line)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--label", default="",
                        help="Row id or configuration this measures")
    parser.add_argument("--note", default="",
                        help="Free-text description of the configuration")
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="-- followed by the command to run")
    opts = parser.parse_args()

    command = [c for c in opts.command if c != "--"]
    if not command:
        parser.error("no command given after --")

    samples: List[int] = []
    stop = threading.Event()

    def sampler() -> None:
        while not stop.is_set():
            value = sample_used_mib(opts.device)
            if value is not None:
                samples.append(value)
            stop.wait(opts.interval)

    thread = threading.Thread(target=sampler, daemon=True)
    started = time.time()
    thread.start()
    proc = subprocess.run(command, capture_output=True, text=True)
    stop.set()
    thread.join(timeout=5)
    elapsed = time.time() - started

    report: Dict[str, Any] = {
        "schema": "issue83-capacity/1",
        "row_id": opts.label,
        "note": opts.note,
        "device": opts.device,
        "device_total_mib": device_total_mib(opts.device),
        "peak_used_mib": max(samples) if samples else None,
        "samples": len(samples),
        "sample_interval_sec": opts.interval,
        "elapsed_sec": round(elapsed, 1),
        "returncode": proc.returncode,
        "command": command,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
        "caveat": ("One configuration on one device. Not a capacity claim for "
                   "other geometries, frame counts or devices. No CPU-fallback "
                   "behaviour is claimed or inferred from the exit status."),
    }
    opts.json.parent.mkdir(parents=True, exist_ok=True)
    opts.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in
                      ("row_id", "peak_used_mib", "device_total_mib",
                       "samples", "returncode")}, indent=2))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
