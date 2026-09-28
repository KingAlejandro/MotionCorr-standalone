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
import signal
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
    """A genuinely separate small parent, as in production.

    The previous version of this control ran `/usr/bin/env python ...`. `env` **execs**
    Python, so the payload pid equalled the launcher pid, `resolve_payload` trivially
    returned the process it was handed, and the distinguishing assertion -- that the
    launcher's residency is smaller -- sat behind `if found["pid"] != proc.pid` and never
    ran. The control proved Python's allocation and units and nothing about payload-versus-
    launcher discrimination.

    This version uses `/usr/bin/time -v`, the same shape production uses: it forks, stays
    alive as a small parent, and keeps a pid distinct from the payload's. Different pids are
    now asserted unconditionally, and the discrimination is mutation-proved -- sampling the
    parent must FAIL the allocation assertion that sampling the child passes.
    """
    if not LINUX:
        check("payload witness follows the child, not the launcher", True, "SKIP: no /proc")
        return
    big_mib = 256
    child = HERE / ".control_child.py"
    child.write_text(
        "import time,sys\n"
        f"buf = bytearray({big_mib} * 1024 * 1024)\n"
        "for i in range(0, len(buf), 4096): buf[i] = 1\n"
        "sys.stderr.write('ready\\n'); sys.stderr.flush()\n"
        "time.sleep(8)\n")
    timev = "/usr/bin/time"
    if not os.path.exists(timev):
        check("payload witness follows the child, not the launcher", True,
              "SKIP: /usr/bin/time absent")
        child.unlink(missing_ok=True)
        return
    proc = None
    try:
        proc = subprocess.Popen([timev, "-v", sys.executable, str(child)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                start_new_session=True)
        for _ in range(200):                      # wait until the child has touched memory
            line = proc.stderr.readline()
            if not line or b"ready" in line:
                break
        found = er.resolve_payload(proc.pid, pathlib.Path(sys.executable))
        check("payload resolved via /proc/<pid>/exe", bool(found), f"{found}")
        if not found:
            return

        # Unconditional: the whole point of the control.
        check("resolved payload PID differs from the launcher PID",
              found["pid"] != proc.pid,
              f"payload={found['pid']} launcher={proc.pid} "
              f"launcher_exe={os.path.realpath(f'/proc/{proc.pid}/exe')}")

        payload = er.numa_residency(found["pid"])
        parent = er.numa_residency(proc.pid)
        got = payload["resident_MiB_total"] if payload else 0.0
        par = parent["resident_MiB_total"] if parent else 0.0
        threshold = big_mib * 0.5

        check(f"sampling the CHILD passes: residency reflects {big_mib} MiB",
              payload is not None and got > threshold, f"child={got} MiB")
        # Mutation: the same assertion applied to the parent must fail, or the witness
        # cannot reject a launcher-sampling implementation -- which is the bug that
        # produced the withdrawn 98.6% node-local claim.
        check("MUTATION - sampling the PARENT fails the same assertion",
              parent is not None and par < threshold,
              f"parent={par} MiB vs threshold {threshold} MiB")
        check("parent residency is strictly smaller than the payload's", par < got,
              f"parent={par} MiB < child={got} MiB")
        check("units are bytes from numa_maps, not numastat MB",
              bool(payload) and payload["unit"].startswith("bytes"),
              payload["unit"][:46] if payload else "n/a")
        print(f"        identity: payload pid={found['pid']} exe={found['exe']} "
              f"session={found.get('session')} starttime={found.get('starttime_ticks')}")
        print(f"        per-node child bytes: {payload['resident_bytes_by_node'] if payload else None}")
    finally:
        if proc:
            try:
                os.killpg(os.getpgid(proc.pid), 9)
            except Exception:
                pass
        child.unlink(missing_ok=True)


def control_3_child_ignoring_sigterm_is_still_reaped():
    """The discriminating case: a cooperative parent and a child that IGNORES SIGTERM.

    This is the shape reproduced against the committed runner (sha256 b05260db...): the
    parent exits on SIGTERM, `proc.wait()` returns, the old helper broke out of its signal
    loop on that basis, then looked for survivors by descending from the now-dead launcher --
    finding none, because the child had been reparented to init -- logged `group_alive=True`,
    and returned -15 while the child was still running.

    Two halves, so the control cannot pass vacuously:
      (a) escalation decided by launcher exit demonstrably leaves the child alive, and a
          descendant walk cannot see it while pgid enumeration can;
      (b) the shipped helper reaps it and reports cleanup_confirmed.
    """
    if not LINUX:
        check("child ignoring SIGTERM is reaped", True, "SKIP")
        return

    src = HERE / ".control_parent.py"
    src.write_text(
        "import os,signal,subprocess,sys,time\n"
        "child = subprocess.Popen([sys.executable,'-c',"
        "\"import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "time.sleep(120)\"])\n"
        "signal.signal(signal.SIGTERM, lambda *a: os._exit(0))\n"
        "sys.stderr.write(str(child.pid)+'\\n'); sys.stderr.flush()\n"
        "time.sleep(120)\n")

    def spawn():
        pr = subprocess.Popen([sys.executable, str(src)], start_new_session=True,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        kid = int(pr.stderr.readline().strip())
        time.sleep(0.4)
        return pr, kid

    try:
        # (a) old semantics: signal the group, wait for the LAUNCHER, then stop deciding.
        pr, kid = spawn()
        pgid = os.getpgid(pr.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            pr.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        time.sleep(0.5)
        leaked = er._alive(kid) and not _is_zombie(kid)
        check("launcher-exit escalation demonstrably leaves the child running", leaked,
              f"child={kid} alive={leaked} ppid_now={_ppid(kid)} "
              f"descendants_of_launcher={sorted(er._descendants(pr.pid))}")
        members = er.group_members(pgid)
        check("pgid enumeration sees the reparented child (descent does not)",
              kid in members, f"group_members={sorted(members)}")
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            pass
        time.sleep(0.3)

        # (b) the shipped helper must reap it and say so.
        pr, kid = spawn()
        pgid = os.getpgid(pr.pid)
        log: list = []
        res = er._kill_group(pr, pgid, log, grace_s=3.0, kill_s=5.0, hold_s=10.0)
        time.sleep(0.3)
        still = er._alive(kid) and not _is_zombie(kid)
        check("shipped cleanup reaps the SIGTERM-ignoring child", not still,
              f"child={kid} still_running={still}")
        check("cleanup reports confirmed", res["cleanup_confirmed"] is True,
              f"confirmed={res['cleanup_confirmed']} survivors={res['surviving_group_members']}")
        check("cleanup escalated to SIGKILL rather than trusting SIGTERM",
              res["escalated_to_sigkill"] is True, f"escalated={res['escalated_to_sigkill']}")
    finally:
        src.unlink(missing_ok=True)


def _ppid(pid: int):
    f = er._stat_fields(f"/proc/{pid}/stat")
    return int(f[er.F_PPID]) if f and len(f) > er.F_PPID else None


def _is_zombie(pid: int) -> bool:
    f = er._stat_fields(f"/proc/{pid}/stat")
    return bool(f and len(f) > er.F_STATE and f[er.F_STATE] == "Z")


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
    control_3_child_ignoring_sigterm_is_still_reaped()
    control_4_payload_is_not_its_own_interference()
    bad = [n for n, ok, _ in results if not ok]
    print(("\nFAILED: " + ", ".join(bad)) if bad else "\nall runner controls passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
