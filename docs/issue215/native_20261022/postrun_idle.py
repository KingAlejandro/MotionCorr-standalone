#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only post-run policy; preflight continues to use strict one-shot idle."""
import time

import run_native as n

WINDOW_SECONDS = 10.0
SPACING_SECONDS = 1.0


def validate(sample):
    """Only utilization may settle. Every other gate is immediately fatal."""
    assert sample["index"] == 2 and sample["uuid"] == n.UUID, sample
    assert sample["assigned_apps"] == [], sample
    assert type(sample["memory_mib"]) is int and 0 <= sample["memory_mib"] <= 16, sample
    assert type(sample["utilization"]) is int and 0 <= sample["utilization"] <= 100, sample
    health = sample["health"]
    assert health["uuid"] == n.UUID, health
    ecc = health["volatile_uncorrected_ecc"]
    assert all(ecc[key] == "0" for key in (
        "sram_uncorrectable_parity", "sram_uncorrectable_secded", "dram_uncorrectable")), health
    assert health["pending_retirement"] in ("No", "N/A"), health
    assert health["recovery_action"] == "None", health
    assert all(health["remapped_rows"][key] == "No" for key in (
        "remapped_row_pending", "remapped_row_failure")), health


def settle(read_sample, record, *, monotonic=time.monotonic, sleep=time.sleep):
    """Keep every sample, require two consecutive idle checks within 10 seconds.

    read_sample(index, deadline) must bound its read-only queries by deadline.
    record is called before validation, including for a rejected sample.
    """
    start = monotonic()
    deadline = start + WINDOW_SECONDS
    consecutive = 0
    index = 0
    while True:
        if monotonic() >= deadline:
            raise RuntimeError("post-run idle settling deadline exceeded")
        sample = read_sample(index, deadline)
        record(dict(sample=index, elapsed_seconds=monotonic() - start, **sample))
        validate(sample)
        completed = monotonic()
        if completed >= deadline:
            raise RuntimeError("post-run idle sampling exceeded deadline")
        consecutive = consecutive + 1 if sample["utilization"] == 0 else 0
        if consecutive == 2:
            return dict(status="PASS", samples=index + 1, consecutive_idle=consecutive,
                        elapsed_seconds=completed - start,
                        window_seconds=WINDOW_SECONDS, spacing_seconds=SPACING_SECONDS)
        sleep(min(SPACING_SECONDS, max(0, deadline - monotonic())))
        index += 1


def read_sample(index, deadline):
    phase = "post-sample-%02d" % index
    for suffix, argv in (
        ("gpus", ["nvidia-smi", "--query-gpu=index,uuid,name,memory.used,utilization.gpu", "--format=csv,noheader"]),
        ("apps", ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory", "--format=csv,noheader"]),
        ("xml", ["nvidia-smi", "-i", n.UUID, "-q", "-x"]),
    ):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("post-run query deadline exceeded")
        n.command(phase + "-" + suffix, argv, timeout=remaining)
    rows = [r.split(", ") for r in (n.ROOT / (phase + "-gpus.log")).read_text().splitlines()]
    assigned = [r for r in rows if r[0] == "2"]
    assert len(assigned) == 1, rows
    row = assigned[0]
    apps = [r for r in (n.ROOT / (phase + "-apps.log")).read_text().splitlines()
            if r.split(", ")[0] == n.UUID]
    return dict(utc=n.utc(), index=int(row[0]), uuid=row[1], assigned_apps=apps,
                memory_mib=int(row[3].split()[0]), utilization=int(row[4].split()[0]),
                health=n.parse_health(n.ROOT / (phase + "-xml.log")))


def postrun_health():
    def record(sample):
        with (n.ROOT / "post-samples.jsonl").open("a") as out:
            out.write(n.json.dumps(sample) + "\n")
    try:
        result = settle(read_sample, record)
    except Exception as error:
        n.save("post-settle.json", dict(status="FAIL", utc=n.utc(), error=repr(error)))
        raise
    n.save("post-settle.json", dict(utc=n.utc(), **result))
