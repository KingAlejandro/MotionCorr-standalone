#!/usr/bin/env python3
"""Simultaneous aggregate host RSS and UUID-filtered sampled GPU memory.

Why this exists rather than reusing what is already in the tree.

`tools/multi_gpu/run_multi_gpu.py` records `rss_hwm_kib` per worker from
`/proc/<pid>/status` VmHWM. VmHWM is a per-process *lifetime* peak and the
launcher explicitly excludes the ghostscript children. Adding N of those
together gives an upper bound on a quantity nobody observed: the workers need
not have peaked at the same instant. A 1/2/4-worker comparison at a fixed total
CPU budget is exactly the case where that distinction decides the answer, so the
aggregate has to be sampled on one clock.

`tools/envelope_runner.py` (#26) has the right RSS semantics but is structurally
single-process -- one Popen, one blocking wait -- and its GPU sampler addresses
devices by nvidia-smi ordinal (`--id=<n>`) and reads whole-device `memory.used`.
An ordinal does not identify silicon once CUDA_VISIBLE_DEVICES is set, and a
whole-device figure includes co-tenants. Both are disqualifying here.

So: one sweep, one timestamp, every sampled figure published next to the
interval that produced it.

  host RSS   sum of /proc/<pid>/statm resident pages * page size over the whole
             descendant tree of the watched roots, ghostscript children
             included. Peak = max over sweeps of the *sweep total*, never a sum
             of separately observed maxima. Shared pages are counted once per
             process, so a sweep total is an upper bound on unique resident
             bytes; it is the same upper bound in every arm.

  GPU memory nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory via
             tools/multi_gpu/gpu_witness, restricted to the UUIDs granted to
             this arm. Per-process and UUID-addressed, so a co-tenant on the
             same physical device is not attributed to us.

Both figures are sampled lower bounds on the true peak: a spike entirely between
two sweeps is invisible. `sweeps`, `interval_s` and the observed sweep spacing
are emitted so that is checkable rather than implied. With zero successful
sweeps no peak is emitted at all -- the field is null and `error` says why. A
figure of 0 would read as "measured, and small".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "multi_gpu"))
try:
    import gpu_witness  # noqa: E402
except ImportError as _exc:  # host RSS still works; GPU sampling reports why it did not
    gpu_witness = None
    _GPU_IMPORT_ERROR = f"gpu_witness unavailable: {_exc}"
else:
    _GPU_IMPORT_ERROR = None

PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")


def _children_map() -> dict[int, list[int]]:
    """ppid -> [pid] for every process visible in /proc, in one pass."""
    kids: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            # Field 4 of /proc/<pid>/stat is ppid. comm (field 2) is parenthesised
            # and may itself contain spaces and ')', so split after the LAST ')'.
            stat = (entry / "stat").read_text()
            after = stat[stat.rindex(")") + 2:].split()
            kids.setdefault(int(after[1]), []).append(int(entry.name))
        except (OSError, ValueError, IndexError):
            continue
    return kids


def _descendants(roots: list[int], kids: dict[int, list[int]]) -> list[int]:
    seen, stack = [], list(roots)
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.append(pid)
        stack.extend(kids.get(pid, ()))
    return seen


def _tree_rss_kib(pids: list[int]) -> tuple[int, int]:
    """(summed resident KiB, number of pids that actually contributed)."""
    total = counted = 0
    for pid in pids:
        try:
            resident = int(Path(f"/proc/{pid}/statm").read_text().split()[1])
        except (OSError, ValueError, IndexError):
            continue  # exited between enumeration and read
        total += resident * PAGE_SIZE // 1024
        counted += 1
    return total, counted


class AggregateSampler(threading.Thread):
    # The stop flag is _stop_event, not _stop: threading.Thread already has a
    # private _stop(), and join() calls it through _wait_for_tstate_lock once
    # the thread has finished. Shadowing it makes every join() raise
    # "'Event' object is not callable" after the run has already completed.
    def __init__(self, roots: list[int], uuids: list[str], interval: float):
        super().__init__(daemon=True)
        self.roots = roots
        self.uuids = [u for u in uuids if u]
        self.interval = interval
        self.sweeps: list[dict] = []
        self.error: str | None = None
        self._stop_event = threading.Event()

    def run(self) -> None:
        if not Path("/proc").is_dir():
            self.error = "no /proc on this platform; no host RSS was sampled"
            return
        while not self._stop_event.is_set():
            t = time.time()
            try:
                kids = _children_map()
                pids = _descendants(self.roots, kids)
                rss_kib, counted = _tree_rss_kib(pids)
            except Exception as exc:  # noqa: BLE001
                # Record and stop. A sampler that dies silently would certify the
                # whole arm on the sweeps it happened to take before dying.
                self.error = f"host sweep failed: {type(exc).__name__}: {exc}"
                return
            gpu, gpu_err = {}, None
            if self.uuids and gpu_witness is None:
                gpu_err = _GPU_IMPORT_ERROR
            elif self.uuids:
                try:
                    for app in gpu_witness.compute_apps():
                        if app["gpu_uuid"] in self.uuids:
                            mib = int(app["used_gpu_memory"].split()[0])
                            gpu[app["gpu_uuid"]] = gpu.get(app["gpu_uuid"], 0) + mib
                except Exception as exc:  # noqa: BLE001
                    gpu_err = f"{type(exc).__name__}: {exc}"
            self.sweeps.append({"t": round(t, 3), "rss_kib": rss_kib,
                                "pids": counted, "gpu_mib_by_uuid": gpu,
                                "gpu_error": gpu_err})
            self._stop_event.wait(self.interval)

    def stop(self) -> None:
        self._stop_event.set()

    def record(self) -> dict:
        n = len(self.sweeps)
        base = {
            "interval_s": self.interval,
            "sweeps": n,
            "roots": self.roots,
            "uuids": self.uuids,
            "error": self.error,
            "semantics": (
                "peak_simultaneous_host_rss_kib is the maximum over sweeps of one "
                "sweep's total across the whole descendant tree, ghostscript "
                "children included. It is NOT a sum of per-process high-water "
                "marks. Both peaks are sampled lower bounds: a spike between two "
                "sweeps is not observed."),
        }
        if n == 0:
            base.update({"peak_simultaneous_host_rss_kib": None,
                         "peak_gpu_mib_by_uuid": None,
                         "peak_gpu_mib_all_uuids": None,
                         "observed_sweep_spacing_s": None})
            return base
        spacing = [round(self.sweeps[i + 1]["t"] - self.sweeps[i]["t"], 3)
                   for i in range(n - 1)]
        by_uuid = {}
        for u in self.uuids:
            vals = [s["gpu_mib_by_uuid"].get(u) for s in self.sweeps
                    if s["gpu_mib_by_uuid"].get(u) is not None]
            by_uuid[u] = max(vals) if vals else None
        all_sweep_totals = [sum(s["gpu_mib_by_uuid"].values())
                            for s in self.sweeps if s["gpu_mib_by_uuid"]]
        gpu_errors = sorted({s["gpu_error"] for s in self.sweeps if s["gpu_error"]})
        peak = max(self.sweeps, key=lambda s: s["rss_kib"])
        base.update({
            "peak_simultaneous_host_rss_kib": peak["rss_kib"],
            "peak_simultaneous_host_rss_gib": round(peak["rss_kib"] / 1048576, 4),
            "peak_sweep_pid_count": peak["pids"],
            "peak_sweep_t": peak["t"],
            "peak_gpu_mib_by_uuid": by_uuid,
            "peak_gpu_mib_all_uuids": max(all_sweep_totals) if all_sweep_totals else None,
            "gpu_sample_errors": gpu_errors or None,
            "observed_sweep_spacing_s": {
                "min": min(spacing), "max": max(spacing),
                "median": sorted(spacing)[len(spacing) // 2]} if spacing else None,
            "sweeps_raw": self.sweeps,
        })
        return base


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pid", type=int, action="append", required=True,
                    help="root pid to watch; repeatable. Descendants are included.")
    ap.add_argument("--uuid", action="append", default=[],
                    help="GPU UUID granted to this arm; repeatable. Omit for CPU arms.")
    ap.add_argument("--interval", type=float, default=0.25)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    s = AggregateSampler(a.pid, a.uuid, a.interval)
    s.start()
    # Watch until every root has gone. The sampler owns no child, so this is the
    # only termination condition that does not need the caller to time it.
    while any(Path(f"/proc/{p}").exists() for p in a.pid):
        time.sleep(a.interval)
    s.stop()
    s.join(timeout=10 * a.interval + 5)
    Path(a.out).write_text(json.dumps(s.record(), indent=2) + "\n")
    return 0 if s.error is None and s.sweeps else 1


if __name__ == "__main__":
    raise SystemExit(main())
