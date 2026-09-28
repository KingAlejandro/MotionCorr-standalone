#!/usr/bin/env python3
"""Pin workers to physical GPUs by UUID, and witness which GPU each one used.

Two problems this exists to avoid.

**Ordinals do not identify silicon.** Under CUDA_VISIBLE_DEVICES every worker
sees one device numbered 0, so four "device 0" workers look identical to a real
four-device run in any log that prints only the ordinal. Worse, a bare CUDA
ordinal is not even a stable index into nvidia-smi's table: CUDA orders devices
by capability unless CUDA_DEVICE_ORDER=PCI_BUS_ID is set, while nvidia-smi
orders by PCI bus. This module therefore never translates a bare ordinal for a
worker. It selects a *physical device*, hands the worker
`CUDA_VISIBLE_DEVICES=GPU-<uuid>` and `--gpu 0`, and the mapping is unambiguous
by construction.

**A request is not a witness.** Asking for four devices and getting them are
different claims. `compute_apps()` reads
`nvidia-smi --query-compute-apps=pid,gpu_uuid`, which reports, for each process
actually holding a CUDA context, the physical GPU it holds it on. Sampling that
while the workers run is what turns "we passed four device flags" into "four
distinct GPUs ran work".

Note that nvidia-smi itself ignores CUDA_VISIBLE_DEVICES -- its --query-gpu
table is always the full physical set. An earlier draft of this file resolved
ordinals by setting that variable for the nvidia-smi child, which silently
returned the wrong devices. All queries here are deliberately unrestricted, and
selection is done on the returned UUIDs.

Nothing in this module initializes CUDA, so importing it never creates a context
that a launcher would then have to avoid forking.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys


class WitnessError(RuntimeError):
    pass


def _run_smi(args: list[str]) -> str:
    exe = shutil.which("nvidia-smi")
    if exe is None:
        raise WitnessError("nvidia-smi not found; cannot witness physical device identity")
    env = dict(os.environ)
    # Always query the full physical set. nvidia-smi ignores CUDA_VISIBLE_DEVICES
    # anyway; clearing it makes that explicit rather than accidental.
    env.pop("CUDA_VISIBLE_DEVICES", None)
    # Bounded: an unresponsive nvidia-smi would otherwise hang the sampler
    # thread, and the launcher's join() would time out while the thread was
    # still appending to the sample list it is about to read.
    try:
        proc = subprocess.run([exe] + args, capture_output=True, text=True, env=env,
                              timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise WitnessError(f"nvidia-smi {' '.join(args)} timed out after 30 s") from exc
    if proc.returncode != 0:
        raise WitnessError(f"nvidia-smi {' '.join(args)} exited {proc.returncode}: "
                           f"{proc.stderr.strip()}")
    return proc.stdout


def host_devices() -> list[dict[str, str]]:
    """Every physical device on the host, in nvidia-smi (PCI) order."""
    out = _run_smi(["--query-gpu=index,uuid,name,memory.total", "--format=csv,noheader"])
    devices = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        devices.append({"smi_index": parts[0], "uuid": parts[1], "name": parts[2],
                        "memory_total": parts[3]})
    if not devices:
        raise WitnessError("nvidia-smi reported no devices")
    return devices


def select(selectors: list[str], devices: list[dict[str, str]] | None = None
           ) -> list[dict[str, str]]:
    """Resolve selectors to distinct physical devices.

    A selector is an nvidia-smi index ("2") or a UUID prefix ("GPU-063e"). The
    result carries the full UUID, which is what a worker is pinned with.
    """
    devices = host_devices() if devices is None else devices
    chosen: list[dict[str, str]] = []
    for sel in selectors:
        s = sel.strip()
        hits = [d for d in devices if d["smi_index"] == s] if s.isdigit() else []
        if not hits:
            hits = [d for d in devices if d["uuid"].startswith(s)]
        if not hits:
            raise WitnessError(
                f"selector {sel!r} matches no device; available: "
                + ", ".join(f"{d['smi_index']}={d['uuid']}" for d in devices)
            )
        if len(hits) > 1:
            raise WitnessError(f"selector {sel!r} is ambiguous: "
                               + ", ".join(d["uuid"] for d in hits))
        entry = dict(hits[0])
        entry["selector"] = sel
        chosen.append(entry)

    seen: dict[str, str] = {}
    for e in chosen:
        if e["uuid"] in seen:
            raise WitnessError(
                f"selectors {seen[e['uuid']]!r} and {e['selector']!r} both resolve to "
                f"physical device {e['uuid']}; that is one GPU, not two"
            )
        seen[e["uuid"]] = e["selector"]
    return chosen


def worker_env(device: dict[str, str], base: dict[str, str] | None = None
               ) -> dict[str, str]:
    """Environment pinning one worker to exactly one physical device.

    The worker then passes `--gpu 0`, which is the only device it can see, so the
    ordinal it prints cannot be mistaken for a claim about which GPU it used.
    """
    env = dict(os.environ if base is None else base)
    env["CUDA_VISIBLE_DEVICES"] = device["uuid"]
    return env


def compute_apps() -> list[dict[str, str]]:
    """Processes currently holding a CUDA context, with the physical GPU each is on."""
    out = _run_smi(["--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
                    "--format=csv,noheader"])
    apps = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        apps.append({"pid": parts[0], "gpu_uuid": parts[1], "used_gpu_memory": parts[2]})
    return apps


def check_observations(expected: dict[int, str], observed: list[dict[str, str]]
                       ) -> dict[str, object]:
    """Compare sampled compute-apps records against the intended pinning.

    `expected` maps worker pid to the physical UUID it was pinned to. Returns a
    verdict record; the caller decides what to do with it. A pid that was never
    observed is reported as unwitnessed rather than as a pass -- a short movie
    can finish between samples, and calling that a witness would be a check that
    cannot observe what it asserts.
    """
    by_pid: dict[str, set[str]] = {}
    for app in observed:
        by_pid.setdefault(app["pid"], set()).add(app["gpu_uuid"])

    witnessed, unwitnessed, wrong_device, shared = {}, [], [], []
    for pid, uuid in expected.items():
        seen = by_pid.get(str(pid))
        if not seen:
            unwitnessed.append(pid)
            continue
        witnessed[pid] = sorted(seen)
        if len(seen) > 1:
            wrong_device.append({"pid": pid, "expected": uuid, "observed": sorted(seen)})
        elif next(iter(seen)) != uuid:
            wrong_device.append({"pid": pid, "expected": uuid, "observed": sorted(seen)})

    uuid_to_pids: dict[str, list[int]] = {}
    for pid, uuids in witnessed.items():
        for u in uuids:
            uuid_to_pids.setdefault(u, []).append(pid)
    for uuid, pids in uuid_to_pids.items():
        if len(pids) > 1:
            shared.append({"gpu_uuid": uuid, "pids": sorted(pids)})

    return {
        "expected": {str(k): v for k, v in expected.items()},
        "witnessed": {str(k): v for k, v in witnessed.items()},
        "unwitnessed_pids": sorted(unwitnessed),
        "wrong_device": wrong_device,
        "shared_devices": shared,
        "distinct_devices_witnessed": len(uuid_to_pids),
        "all_pids_witnessed_on_intended_distinct_devices":
            not unwitnessed and not wrong_device and not shared,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_sel = sub.add_parser("select", help="resolve selectors to distinct physical devices")
    p_sel.add_argument("--devices", required=True,
                       help="comma-separated nvidia-smi indices or UUID prefixes")
    p_sel.add_argument("--json-out", default=None)

    p_obs = sub.add_parser("observe", help="snapshot processes holding CUDA contexts")
    p_obs.add_argument("--json-out", default=None)

    a = ap.parse_args(argv)
    try:
        if a.cmd == "select":
            chosen = select([s for s in a.devices.split(",") if s.strip()])
            record = {"selected": chosen}
            for d in chosen:
                print(f"{d['selector']}\t{d['uuid']}\t{d['name']}\t"
                      f"CUDA_VISIBLE_DEVICES={d['uuid']} --gpu 0")
        else:
            apps = compute_apps()
            record = {"compute_apps": apps}
            for app in apps:
                print(f"{app['pid']}\t{app['gpu_uuid']}\t{app['used_gpu_memory']}")
    except WitnessError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    if a.json_out:
        with open(a.json_out, "w") as fh:
            json.dump(record, fh, indent=2)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
