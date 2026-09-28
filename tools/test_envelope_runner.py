#!/usr/bin/env python3
"""Negative controls for the issue #26 runner's witnesses.

Each control pins a failure that actually occurred and produced a published wrong number, so
that the fix cannot silently regress:

1. **Sequential size accounting is not a peak.** Two sequential 100 MiB stages must not be
   reported as a 200 MiB peak. The CUDA profile prints `Peak GPU memory allocated` once per
   global/local call; summing 25 patch calls at 62.59 MiB with one global call at
   1569.59 MiB gave 3134.34 MiB, which was published as an allocator-traced process peak. It
   is neither a peak nor a trace.

2. **The memory witness must follow the payload, not the launcher.** The runner spawns
   `taskset ... /usr/bin/time -v <binary>`, so the pid it holds is the launcher. A witness
   sampled there described `/usr/bin/time`: a retained `numa_maps` mapped `file=/usr/bin/time`
   and its `numastat` total of 1.45 -- MB, for the launcher -- was published as 1.45 GB of
   node-local movie arrays. Control: a tiny launcher execs a child holding a large known
   allocation; the witness must identify the child and report the child's residency.

3. **Cancellation must stop the owned tree.** `proc.kill()` signals only the launcher, so a
   payload can outlive a timeout, keep burning the cpuset and contaminate the next arm --
   including someone else's, after the lock is released. Control: a launcher whose child
   keeps sleeping after the launcher dies must be reaped by group termination, and the naive
   single-pid kill must be shown to leave it behind.

Controls 2 and 3 need /proc and POSIX process groups and skip elsewhere.

Run:  python3 tools/test_envelope_runner.py
"""

import importlib.util
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("envelope_runner", HERE / "envelope_runner.py")
er = importlib.util.module_from_spec(spec)
spec.loader.exec_module(er)

LINUX = os.path.isdir("/proc")
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))


def control_1_sequential_sizes_are_not_a_peak():
    text = ("   Peak GPU memory allocated:    100.00 MiB\n"
            "   Peak GPU memory allocated:    100.00 MiB\n"
            "   Total GPU alignment time:     3.00 ms\n"
            "   Total GPU alignment time:     4.00 ms\n")
    cuda = er.parse_stage_timers(text)["cuda_profile"]
    size = cuda["Peak GPU memory allocated [MiB]"]
    ok = size["sum"] is None and size["max"] == 100.0 and size["n"] == 2
    check("two sequential 100 MiB stages are not a 200 MiB peak", ok,
          f"n={size['n']} max={size['max']} sum={size['sum']}")
    t = cuda["Total GPU alignment time [ms]"]
    check("time-like tags still expose a meaningful sum", t["sum"] == 7.0 and t["max"] == 4.0,
          f"sum={t['sum']}")


def control_2_witness_follows_the_payload():
    if not LINUX:
        check("payload witness follows the child, not the launcher", True, "SKIP: no /proc")
        return
    big_mib = 256
    child_src = (
        "import time,sys\n"
        f"buf = bytearray({big_mib} * 1024 * 1024)\n"
        "for i in range(0, len(buf), 4096): buf[i] = 1\n"   # force resident
        "sys.stderr.write('ready\\n'); sys.stderr.flush()\n"
        "time.sleep(6)\n")
    child = HERE / ".control_child.py"
    child.write_text(child_src)
    try:
        # A deliberately tiny launcher in front of a large child, mirroring taskset/time.
        proc = subprocess.Popen(["/usr/bin/env", sys.executable, str(child)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                start_new_session=True)
        proc.stderr.readline()                      # wait until the child has touched memory
        found = er.resolve_payload(proc.pid, pathlib.Path(sys.executable))
        ok_id = bool(found) and found["exe"] == os.path.realpath(sys.executable)
        check("payload identified via /proc/<pid>/exe", ok_id, f"{found}")

        launcher = er.numa_residency(proc.pid)
        payload = er.numa_residency(found["pid"]) if found else None
        got_mib = payload["resident_MiB_total"] if payload else 0
        ok_mem = payload is not None and got_mib > big_mib * 0.5
        check(f"payload residency reflects the child's {big_mib} MiB allocation", ok_mem,
              f"payload={got_mib} MiB")
        check("units are bytes from numa_maps, not numastat MB",
              bool(payload) and payload["unit"].startswith("bytes"),
              payload["unit"][:48] if payload else "n/a")
        if found and found["pid"] != proc.pid and launcher:
            check("launcher residency is not mistaken for the payload's",
                  launcher["resident_MiB_total"] < got_mib,
                  f"launcher={launcher['resident_MiB_total']} MiB vs payload={got_mib} MiB")
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), 9)
        except Exception:
            pass
        child.unlink(missing_ok=True)


def control_3_child_survives_a_single_pid_kill():
    if not LINUX:
        check("group termination reaps a child that outlives its parent", True, "SKIP")
        return
    script = ("exec python3 -c \"import subprocess,time,os;"
              "subprocess.Popen(['sleep','30']);"
              "time.sleep(30)\"")

    def spawn():
        return subprocess.Popen(["bash", "-c", script], start_new_session=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # (a) the naive single-pid kill: the grandchild must still be alive afterwards,
    #     which is what makes this a negative control rather than a tautology.
    p = spawn()
    time.sleep(1.5)
    kids = er._descendants(p.pid)
    p.kill()
    p.wait(timeout=10)
    time.sleep(0.5)
    leaked = [k for k in kids if er._alive(k)]
    check("naive proc.kill() demonstrably leaves the child running", bool(leaked),
          f"survivors={leaked}")
    for k in leaked:
        try:
            os.kill(k, 9)
        except OSError:
            pass

    # (b) group termination must leave nothing behind
    p = spawn()
    time.sleep(1.5)
    kids = er._descendants(p.pid)
    log = []
    er._kill_group(p, os.getpgid(p.pid), log)
    time.sleep(0.5)
    survivors = [k for k in kids if er._alive(k)]
    check("group termination reaps the child that outlived its parent", not survivors,
          f"survivors={survivors} log={log[-1] if log else ''}")


def control_4_payload_is_not_its_own_interference():
    """The payload runs in its own session so cancellation can target the whole group.
    A sampler that owns only the runner's session would then report the very process being
    measured as foreign load inside its own lane -- a self-inflicted contamination reading
    that looks exactly like a real neighbour."""
    if not LINUX:
        check("payload is not counted as its own interference", True, "SKIP")
        return
    mask = open(f"/proc/{os.getpid()}/status").read().split("Cpus_allowed_list:")[1].split()[0]
    cpus = sorted(er.parse_cpu_list(mask))
    burn = ("import time\n" "t=time.time()\n" "while time.time()-t<3.0: pass\n")
    s1 = er.Sampler(own_user="x", gpu_index=None, mask=mask, period=0.25, ps_period=0.25,
                    own_root_pid=os.getpid())
    s1.start()
    time.sleep(0.5)
    proc = subprocess.Popen(["taskset", "-c", str(cpus[0]), sys.executable, "-c", burn],
                            start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    s1.own_also(proc.pid)                      # sid == pid for a session leader
    time.sleep(2.5)
    proc.wait()
    s1.stop(); s1.join(timeout=5)
    # Assert on the payload's own command, not on a global zero: this host has permanent
    # unpinned ctffind, so "no foreign threads at all" is not achievable and asserting it
    # would make the control fail for a reason unrelated to what it tests.
    me = os.path.basename(sys.executable)[:15]
    adopted_hits = s1.foreign_detail.get(me, 0)
    check("adopted payload does not appear in its own foreign list", adopted_hits == 0,
          f"{me} hits={adopted_hits}  (other in-mask commands seen: "
          f"{ {k: v for k, v in s1.foreign_detail.items() if k != me} })")

    # negative half: without adoption the same payload MUST show up, otherwise the control
    # proves nothing about the adoption logic.
    s2 = er.Sampler(own_user="x", gpu_index=None, mask=mask, period=0.25, ps_period=0.25,
                    own_root_pid=os.getpid())
    s2.start()
    time.sleep(0.5)
    p2 = subprocess.Popen(["taskset", "-c", str(cpus[0]), sys.executable, "-c", burn],
                          start_new_session=True,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)
    p2.wait()
    s2.stop(); s2.join(timeout=5)
    unadopted_hits = s2.foreign_detail.get(me, 0)
    check("without adoption the same payload IS seen (control is not vacuous)",
          unadopted_hits >= 1, f"{me} hits={unadopted_hits}")


def main():
    print(f"platform={sys.platform} /proc={LINUX}")
    control_1_sequential_sizes_are_not_a_peak()
    control_2_witness_follows_the_payload()
    control_3_child_survives_a_single_pid_kill()
    control_4_payload_is_not_its_own_interference()
    bad = [n for n, ok, _ in results if not ok]
    print(("\nFAILED: " + ", ".join(bad)) if bad else "\nall runner controls passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
