#!/usr/bin/env python3
"""Controls for the issue #26 interference witness. Linux only: it reads /proc.

An interference number that is always zero is indistinguishable from a clean run, so this
pins that the sampler reacts to the three cases that matter:

  quiet lane                 -> 0 threads in mask
  foreign burst in the lane  -> detected, attributed to the right command
  foreign burst outside it   -> 0, because work outside the cpuset is not our contention

and that the sampler does not count its own `ps`/`nvidia-smi` children. It did: ownership was
decided by walking a `ps` snapshot, which races with the children the sampler had just
forked, and a real series recorded `foreign_cpu_max = 2750%` against `ps` and `gs` -- the
sampler's own subprocess and MotionCorr's own ghostscript. Ownership is now session id.

Run on a Linux host:  setsid python3 tools/test_envelope_interference.py [--lane 96-111]
"""

import argparse
import importlib.util
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lane", default=None,
                    help="cpuset to treat as the measurement lane, e.g. 96-111")
    ap.add_argument("--seconds", type=float, default=2.0)
    args = ap.parse_args()

    if not os.path.isdir("/proc"):
        print("SKIP: /proc is absent (not Linux); the interference witness cannot run here")
        return 0

    spec = importlib.util.spec_from_file_location("envelope_runner", HERE / "envelope_runner.py")
    er = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(er)

    lane = args.lane
    if lane is None:
        own = sorted(er.parse_cpu_list(
            open(f"/proc/{os.getpid()}/status").read().split("Cpus_allowed_list:")[1]
            .split()[0]))
        lane = f"{own[0]}-{own[min(3, len(own) - 1)]}"
    lane_cpus = sorted(er.parse_cpu_list(lane))
    outside = next((c for c in range(os.cpu_count() or 1) if c not in lane_cpus), None)

    def sample(burst_cpu=None):
        s = er.Sampler(own_user=os.environ.get("USER", "?"), gpu_index=None, mask=lane,
                       period=0.25, ps_period=0.25, own_root_pid=os.getpid())
        s.start()
        time.sleep(0.6)
        b = None
        if burst_cpu is not None:
            b = subprocess.Popen(
                ["taskset", "-c", str(burst_cpu), sys.executable, "-c",
                 f"import time\nt=time.time()\nwhile time.time()-t<{args.seconds}: pass"],
                preexec_fn=os.setsid)          # own session, so genuinely foreign
        time.sleep(args.seconds)
        if b:
            b.wait()
        s.stop()
        s.join(timeout=5)
        return s

    print(f"lane={lane}  outside_cpu={outside}")
    cases = [("quiet lane", sample(), 0, "eq"),
             (f"burst inside lane (cpu {lane_cpus[min(8, len(lane_cpus) - 1)]})",
              sample(lane_cpus[min(8, len(lane_cpus) - 1)]), 1, "ge")]
    if outside is not None:
        cases.append((f"burst outside lane (cpu {outside})", sample(outside), 0, "eq"))

    failures = 0
    for name, s, want, how in cases:
        got = max(s.foreign_in_mask or [0])
        ok = got == want if how == "eq" else got >= want
        own_children = {c for c in s.foreign_detail if c in ("ps", "nvidia-smi", "pgrep")}
        if own_children:
            ok = False
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<34} in_mask_max={got} "
              f"(want {how} {want})  by_command={s.foreign_detail}")
        if own_children:
            print(f"        own sampler subprocesses counted as foreign: {own_children}")

    print("FAILED" if failures else "\nall interference controls passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
