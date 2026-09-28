#!/usr/bin/env python3
"""Record the placement of the *payload* process, not of whatever launched it.

Run this alongside a validation run. It polls ``/proc`` for processes whose
executable matches ``--match`` and records, per process actually observed: the
resolved executable and its digest, the start time, the CPU affinity the
process really has, the memory nodes it is allowed, and its observed NUMA page
residency.

The distinction matters. A wrapper such as ``taskset``, ``numactl``, ``flock``
or ``/usr/bin/time`` has its own pid, its own affinity and its own -- tiny --
page residency. Sampling the wrapper yields a confident-looking record that
describes the launcher rather than the work, which is the measurement defect
review found in the #109 locality witness. Nothing here samples a process whose
executable does not match, and a run where the payload was never seen is
reported as ``observed: false`` rather than as a clean record.

    python3 tools/validation_issue83/record_payload_env.py \
        --match motioncorr --json placement.json --timeout 3600 &
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

PROC = Path("/proc")
NUMA_NODE = re.compile(r"\bN(\d+)=(\d+)")


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _sha256(path: Path) -> Optional[str]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def boot_time() -> Optional[float]:
    for line in _read(PROC / "stat").splitlines():
        if line.startswith("btime "):
            return float(line.split()[1])
    return None


def numa_residency(pid: int) -> Dict[str, Any]:
    """Pages actually resident per NUMA node, summed over the mappings.

    This is the payload's own residency. A launcher would report a few hundred
    pages here; a real correction run reports orders of magnitude more, which
    is the cheapest way to tell the two records apart after the fact.
    """
    per_node: Dict[str, int] = {}
    text = _read(PROC / str(pid) / "numa_maps")
    for line in text.splitlines():
        for node, pages in NUMA_NODE.findall(line):
            per_node[f"node{node}"] = per_node.get(f"node{node}", 0) + int(pages)
    total = sum(per_node.values())
    policies = sorted({parts[1] for parts in
                       (line.split() for line in text.splitlines())
                       if len(parts) > 1})
    return {"pages_per_node": per_node, "pages_total": total,
            "mib_per_node": {k: round(v * os.sysconf("SC_PAGE_SIZE") / 2**20, 1)
                             for k, v in sorted(per_node.items())},
            "policies_seen": policies,
            "mappings_counted": len(text.splitlines())}


def sample(pid: int, btime: Optional[float]) -> Optional[Dict[str, Any]]:
    status = _read(PROC / str(pid) / "status")
    if not status:
        return None
    fields = {}
    for line in status.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    try:
        exe = os.readlink(PROC / str(pid) / "exe")
    except OSError:
        exe = None
    stat = _read(PROC / str(pid) / "stat")
    started = None
    if stat and btime:
        # Field 22 is starttime in clock ticks since boot; the comm field can
        # contain spaces, so index from the closing parenthesis.
        tail = stat[stat.rfind(")") + 2:].split()
        if len(tail) >= 20:
            started = btime + int(tail[19]) / os.sysconf("SC_CLK_TCK")
    return {
        "pid": pid,
        "executable": exe,
        "executable_sha256": _sha256(Path(exe)) if exe and Path(exe).exists() else None,
        "cmdline": _read(PROC / str(pid) / "cmdline").replace("\0", " ").strip(),
        "started_utc": (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
                        if started else None),
        "cpus_allowed_list": fields.get("Cpus_allowed_list"),
        "mems_allowed_list": fields.get("Mems_allowed_list"),
        "vm_rss_kb": fields.get("VmRSS"),
        "threads": fields.get("Threads"),
        "numa": numa_residency(pid),
        "sampled_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def host_snapshot() -> Dict[str, Any]:
    load = os.getloadavg()
    return {
        "hostname": os.uname().nodename,
        "loadavg": {"1m": load[0], "5m": load[1], "15m": load[2]},
        "cpu_count": os.cpu_count(),
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--match", required=True,
                        help="Substring the payload's executable path must contain")
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--stop-file", type=Path,
                        help="Stop as soon as this file appears")
    opts = parser.parse_args()

    btime = boot_time()
    record: Dict[str, Any] = {
        "schema": "issue83-payload-placement/1",
        "match": opts.match,
        "host_at_start": host_snapshot(),
        "payloads": {},
        "note": ("Sampled processes whose own /proc/<pid>/exe matches --match. "
                 "Launchers (taskset, numactl, flock, /usr/bin/time) are not "
                 "matched and are not recorded as the payload."),
    }
    deadline = time.time() + opts.timeout
    best: Dict[int, Dict[str, Any]] = {}

    if not (PROC / "self").exists():
        # No procfs (macOS, container without /proc): say so rather than write
        # an empty record that reads like "the payload was clean".
        record["observed"] = False
        record["procfs_available"] = False
        record["warning"] = ("this host has no /proc; placement of the payload "
                             "was not observed and is not recorded here")
        opts.json.parent.mkdir(parents=True, exist_ok=True)
        opts.json.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"observed": False, "procfs_available": False}, indent=2))
        return 2
    record["procfs_available"] = True

    while time.time() < deadline:
        if opts.stop_file and opts.stop_file.exists():
            break
        for entry in PROC.iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            try:
                exe = os.readlink(entry / "exe")
            except OSError:
                continue
            if opts.match not in exe:
                continue
            got = sample(pid, btime)
            if not got:
                continue
            # Keep the sample with the largest observed residency: the payload
            # is most informative once it has actually allocated its frames.
            prior = best.get(pid)
            if prior is None or got["numa"]["pages_total"] > prior["numa"]["pages_total"]:
                best[pid] = got
        time.sleep(opts.interval)

    record["payloads"] = {str(pid): entry for pid, entry in sorted(best.items())}
    record["observed"] = bool(best)
    record["distinct_payload_pids"] = len(best)
    record["host_at_end"] = host_snapshot()
    if not best:
        record["warning"] = (f"no process matching {opts.match!r} was ever seen; "
                             "this record does not describe the payload")
    executables = sorted({e["executable"] for e in best.values() if e["executable"]})
    record["executables"] = executables
    cpusets = sorted({e["cpus_allowed_list"] for e in best.values()
                      if e["cpus_allowed_list"]})
    record["cpus_allowed_observed"] = cpusets
    record["mems_allowed_observed"] = sorted({e["mems_allowed_list"] for e in best.values()
                                              if e["mems_allowed_list"]})

    opts.json.parent.mkdir(parents=True, exist_ok=True)
    opts.json.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"observed": record["observed"],
                      "pids": record["distinct_payload_pids"],
                      "executables": executables,
                      "cpus_allowed": cpusets,
                      "mems_allowed": record["mems_allowed_observed"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
