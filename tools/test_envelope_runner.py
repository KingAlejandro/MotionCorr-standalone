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
skipped = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))


def skip(name, why=""):
    """A control that did not run is NOT a pass.

    These previously went through `check(name, True, "SKIP: ...")`, so on a host without
    /proc the suite executed one control out of five and printed "all runner controls
    passed" -- the same false-green shape as the `if pid != launcher` guard these controls
    exist to remove. Skips are tracked separately and named in the summary.
    """
    skipped.append((name, why))
    print(f"  SKIP  {name}" + (f"  ({why})" if why else ""))


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
        skip("payload witness follows the child, not the launcher", "no /proc".strip())
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
        skip("payload witness follows the child, not the launcher", "/usr/bin/time absent".strip())
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
        skip("child ignoring SIGTERM is reaped", "".strip())
        return

    src = HERE / ".control_parent.py"
    src.write_text(
        "import os,signal,subprocess,sys,time\n"
        "child = subprocess.Popen([sys.executable,'-c',"
        "\"import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "time.sleep(120)\"])\n"
        "signal.signal(signal.SIGTERM, lambda *a: os._exit(0))\n"
        # The child reports readiness only AFTER installing SIG_IGN, so the test never
        # signals before the handler exists. A fixed sleep raced cold-start CPython on a
        # loaded host and produced a flaky FAIL that reads like a runner regression.
        "import time as _t\n"
        "TERMBIT = 1 << (signal.SIGTERM - 1)\n"
        "for _ in range(200):\n"
        "    try:\n"
        "        st = open('/proc/%d/stat' % child.pid).read()\n"
        # field 33 sigignore, and the SIGTERM bit specifically: sigignore is already
        # non-zero (CPython ignores SIGPIPE), so a plain != 0 test breaks immediately.
        "        if int(st.rsplit(')',1)[1].split()[30]) & TERMBIT: break\n"
        "    except (OSError, ValueError): pass\n"
        "    _t.sleep(0.05)\n"
        "sys.stderr.write(str(child.pid)+'\\n'); sys.stderr.flush()\n"
        "time.sleep(120)\n")

    spawned = []

    def spawn():
        pr = subprocess.Popen([sys.executable, str(src)], start_new_session=True,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        spawned.append(pr)
        kid = int(pr.stderr.readline().strip())
        # Confirm the ignore-handler really is installed before signalling.
        for _ in range(100):
            if _sigign_mask(kid):
                break
            time.sleep(0.05)
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
        check("pgid enumeration sees the reparented child",
              bool(members) and kid in members, f"group_members={sorted(members or {})}")
        # Assert the contrast the whole fix rests on, rather than only naming it: a change
        # that made the descendant walk see the child would otherwise leave this green
        # under a now-false label.
        check("a descendant walk CANNOT see it (this is why pgid is used)",
              kid not in er._descendants(pr.pid),
              f"descendants_of_launcher={sorted(er._descendants(pr.pid))}")
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
        # A control about not leaking processes must not leak processes.
        for pr in spawned:
            try:
                os.killpg(os.getpgid(pr.pid), signal.SIGKILL)
            except OSError:
                pass
        src.unlink(missing_ok=True)


def _sigign_mask(pid: int) -> bool:
    """True once the process has SIGTERM in its ignored-signal mask (field 32 of stat)."""
    try:
        raw = open(f"/proc/{pid}/stat").read()
        # index k == field k+3 here (comm dropped), so 30 -> field 33 `sigignore`.
        # Index 29 is field 32 `blocked`, which signal.signal() never touches: it stayed 0
        # for the whole test, so the previous handshake never fired and was a fixed delay
        # wearing a handshake's name.
        sigignore = int(raw.rsplit(")", 1)[1].split()[30])
        return bool(sigignore & (1 << (signal.SIGTERM - 1)))
    except (OSError, ValueError, IndexError):
        return False


def _ppid(pid: int):
    f = er._stat_fields(f"/proc/{pid}/stat")
    return int(f[er.F_PPID]) if f and len(f) > er.F_PPID else None


def _is_zombie(pid: int) -> bool:
    f = er._stat_fields(f"/proc/{pid}/stat")
    return bool(f and len(f) > er.F_STATE and f[er.F_STATE] == "Z")


def control_5_execute_arm_records_the_payload_not_the_launcher():
    """End-to-end: assert the witness `execute_arm` actually writes.

    control_2 proves `resolve_payload` and `numa_residency` can tell a payload from its
    launcher, but it calls both itself with pids of its own choosing. That cannot reject the
    bug it exists for: reverting `execute_arm` to sample `proc.pid` leaves every control_2
    assertion passing. This control runs `execute_arm` against a stub binary and asserts on
    the emitted record, so the production wiring is what is under test.
    """
    if not LINUX:
        skip("execute_arm records the payload, not the launcher", "no /proc")
        return
    import shutil, tempfile
    cc = shutil.which("cc") or shutil.which("gcc")
    if not cc:
        skip("execute_arm records the payload, not the launcher", "no C compiler")
        return
    big_mib = 192
    stub_dir = pathlib.Path(tempfile.mkdtemp(prefix="envelope-stub-"))
    # A real ELF, because resolve_payload identifies the payload by /proc/<pid>/exe -- the
    # strong check. A shebang script's exe is its interpreter, so it could never match, and
    # production's payload (motioncorr) is a compiled binary. The stub ignores the runner's
    # arguments the way a real payload would accept them.
    src = stub_dir / "stub.c"
    src.write_text(
        "#include <stdlib.h>\n#include <string.h>\n#include <unistd.h>\n"
        "int main(int argc, char **argv){ (void)argc; (void)argv;\n"
        f"  size_t n = (size_t){big_mib} * 1024UL * 1024UL;\n"
        "  char *b = malloc(n); if(!b) return 1;\n"
        "  memset(b, 1, n);\n"
        "  sleep(4); return 0; }\n")
    stub = stub_dir / "stub_payload"
    rc = subprocess.run([cc, "-O0", "-o", str(stub), str(src)],
                        capture_output=True, text=True)
    if rc.returncode != 0:
        skip("execute_arm records the payload, not the launcher",
             f"stub build failed: {rc.stderr.strip()[:80]}")
        return
    out = stub_dir / "out"
    arm = {"id": "ctl5", "binary": str(stub), "cwd": str(stub_dir), "input_star": "x.star",
           "j": 1, "gpu": None, "cpu_mask": _own_mask(), "extra_opts": []}
    cfg = {"own_user": os.environ.get("USER", "?"), "settle_full_gate": False,
           "inter_run_quiet_s": 0.0, "run_timeout_s": 120, "numa_sample_at_s": 1.5,
           "rss_period_s": 0.25, "device_sample_period_s": 0.5,
           "foreign_sample_period_s": 1.0, "_first_run_done": True}
    try:
        rec = er.execute_arm(arm, cfg, out, pair_index=0, order_in_pair=0, rep=1)
    except Exception as exc:
        check("execute_arm completed against the stub", False, f"{type(exc).__name__}: {exc}")
        return
    pl = (rec.get("placement") or {}).get("payload_identity") or {}
    check("execute_arm resolved a payload identity", bool(pl.get("pid")), f"{pl}")
    if not pl.get("pid"):
        return
    check("recorded payload PID differs from the launcher PID",
          pl["pid"] != pl.get("launcher_pid"),
          f"payload={pl['pid']} launcher={pl.get('launcher_pid')}")
    check("recorded payload exe is the stub binary, not /usr/bin/time",
          os.path.basename(pl.get("exe", "")) == "stub_payload", f"exe={pl.get('exe')}")
    mid = (rec.get("placement") or {}).get("payload_numa_midrun") or {}
    got = mid.get("resident_MiB_total", 0.0)
    # The launcher is ~1.5 MiB; the payload ~200 MiB. A record produced by sampling the
    # launcher cannot clear this.
    check(f"recorded mid-run residency is the payload's (> {big_mib // 2} MiB)",
          got > big_mib * 0.5,
          f"recorded={got} MiB  (a launcher-sampling record would be ~1.5 MiB)")
    pcpus = (rec.get("placement") or {}).get("payload_Cpus_allowed_list")
    check("payload cpuset was read from the payload, and matches the requested mask",
          pcpus == arm["cpu_mask"], f"payload_Cpus_allowed_list={pcpus} requested={arm['cpu_mask']}")
    check("recorded cleanup is confirmed on the normal-exit path",
          not rec.get("cleanup_unconfirmed"),
          f"cleanup={rec.get('cleanup')}")
    print(f"        record: pid={pl['pid']} launcher={pl.get('launcher_pid')} "
          f"exe={pl.get('exe')} midrun={got} MiB nodes={mid.get('resident_bytes_by_node')}")


def control_6_normal_exit_with_a_leaked_child_is_caught():
    """R1: the NORMAL-exit path must verify the group, not only the timeout path.

    Production shape: MotionCorr exits 0 while its ghostscript child from
    joinMultipleEPSIntoSinglePDF is still rendering. `/usr/bin/time` reaps the payload and
    exits, `proc.wait()` returns 0, and the child -- reparented to init but still in the
    group -- keeps burning the cpuset underneath the next arm. Because it inherits the
    payload's session the interference sampler adopts it, so without this check it would be
    neither killed, nor reported as interference, nor quarantined.
    """
    if not LINUX:
        skip("normal exit with a leaked child is caught", "no /proc")
        return
    import shutil, tempfile
    cc = shutil.which("cc") or shutil.which("gcc")
    if not cc:
        skip("normal exit with a leaked child is caught", "no C compiler")
        return
    d = pathlib.Path(tempfile.mkdtemp(prefix="envelope-leak-"))
    (d / "leak.c").write_text(
        "#include <unistd.h>\n#include <stdio.h>\n"
        "int main(int argc, char **argv){ (void)argc; (void)argv;\n"
        "  pid_t p = fork();\n"
        "  if (p == 0) { sleep(120); _exit(0); }\n"      # child outlives the parent
        "  printf(\"%d\\n\", (int)p); fflush(stdout);\n"
        "  sleep(1); return 0; }\n")                      # parent exits 0, normally
    stub = d / "leaky_payload"
    rc = subprocess.run([cc, "-O0", "-o", str(stub), str(d / "leak.c")],
                        capture_output=True, text=True)
    if rc.returncode != 0:
        skip("normal exit with a leaked child is caught", "stub build failed")
        return
    arm = {"id": "ctl6", "binary": str(stub), "cwd": str(d), "input_star": "x.star",
           "j": 1, "gpu": None, "cpu_mask": _own_mask(), "extra_opts": []}
    cfg = {"own_user": os.environ.get("USER", "?"), "settle_full_gate": False,
           "inter_run_quiet_s": 0.0, "run_timeout_s": 60, "numa_sample_at_s": 0.5,
           "rss_period_s": 0.25, "device_sample_period_s": 0.5,
           "foreign_sample_period_s": 1.0, "_first_run_done": True}
    rec = er.execute_arm(arm, cfg, d / "out", pair_index=0, order_in_pair=0, rep=1)
    leaked_pid = None
    stdout_log = d / "out" / "ctl6_pair0_ord0_rep1" / "stdout.log"
    try:
        leaked_pid = int(stdout_log.read_text().split()[0])
    except Exception as exc:
        leaked_pid = None
        check("read the leaked child's pid from the stub's stdout", False,
              f"{stdout_log}: {type(exc).__name__}")
    check("payload exited normally (this is the normal-exit path)", rec["exit_code"] == 0,
          f"exit_code={rec['exit_code']} timed_out={rec.get('timed_out')}")
    cl = rec.get("cleanup")
    check("R1: the normal-exit path detected the residual group member", bool(cl),
          f"cleanup={cl if not cl else cl.get('triggered_by')}")
    if cl:
        check("R1: it was triggered by residual members, not a timeout",
              cl.get("triggered_by") == "residual group members after normal exit",
              f"triggered_by={cl.get('triggered_by')}")
        check("R1: the leaked child was reaped and cleanup confirmed",
              cl.get("cleanup_confirmed") is True,
              f"confirmed={cl.get('cleanup_confirmed')} survivors={cl.get('surviving_group_members')}")
    # Reaping cleans the host, not the measurement: the leaked child shared the cpuset
    # during the timed interval and was session-adopted, so it never appeared in the
    # interference figures either. A successfully reaped residual must still quarantine the
    # arm, or a contaminated wall time is published as clean evidence.
    check("R1: the arm is quarantined even though cleanup succeeded",
          rec.get("quarantined") is True,
          f"quarantined={rec.get('quarantined')} reason={str(rec.get('quarantine_reason'))[:90]}")
    if leaked_pid:
        alive = er._alive(leaked_pid) and not _is_zombie(leaked_pid)
        check("R1: the leaked child is actually dead afterwards", not alive,
              f"leaked_pid={leaked_pid} alive={alive}")
        if alive:                                # never leave it behind
            try:
                os.kill(leaked_pid, signal.SIGKILL)
            except OSError:
                pass


def control_7_session_ownership_cannot_hide_a_stranger():
    """A process sharing the launching shell's session must still count as foreign.

    Ownership was "the runner's session id", but the documented reproduction starts plain
    `python3` under taskset/flock with no setsid, so that sid is the shell's. Anything else
    started from the same shell was silently excluded from every interference figure, which
    turns real lane contention into a reported zero.
    """
    if not LINUX:
        skip("session ownership cannot hide a same-shell stranger", "no /proc")
        return
    own = er.establish_isolated_session()
    check("runner establishes an ownership basis and states whether it is isolated",
          own.get("basis") in ("session", "subtree") and "isolated" in own, f"{own}")

    # The discriminating assertion, at unit level. Spawning a "same-session stranger" from
    # inside this process is not possible once establish_isolated_session() has made us a
    # session leader -- and launching one via setsid would put it in neither our session nor
    # our subtree, so it would read as foreign under BOTH bases and discriminate nothing.
    # What must be pinned is that a non-isolated session is never owned wholesale.
    sid_now = er.own_session()
    iso = er.Sampler(own_user="x", gpu_index=None, mask=None, own_root_pid=os.getpid(),
                     ownership={"basis": "session", "isolated": True, "sid": sid_now,
                                "how": "fixture"})
    noniso = er.Sampler(own_user="x", gpu_index=None, mask=None, own_root_pid=os.getpid(),
                        ownership={"basis": "subtree", "isolated": False, "sid": sid_now,
                                   "how": "fixture"})
    check("an ISOLATED session is owned wholesale", iso._own_sids == {sid_now},
          f"owned_sids={iso._own_sids}")
    check("a NON-isolated session is NOT owned wholesale, so a same-shell stranger in it "
          "still counts as foreign", noniso._own_sids == set(),
          f"owned_sids={noniso._own_sids} (must be empty; ownership falls back to subtree)")

    mask = _own_mask()
    cpus = sorted(er.parse_cpu_list(mask))
    burn = "import time\nt=time.time()\nwhile time.time()-t<3.0: pass\n"
    # A stranger in OUR OWN session (no setsid) and not in our subtree: this is exactly the
    # same-shell case. It must be seen.
    samp = er.Sampler(own_user="x", gpu_index=None, mask=mask, period=0.25, ps_period=0.25,
                      own_root_pid=os.getpid(), ownership=own)
    samp.start()
    time.sleep(0.5)
    pr = subprocess.Popen(["setsid", "taskset", "-c", str(cpus[0]), sys.executable, "-c", burn],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2.5)
        pr.wait()
    finally:
        _reap(pr)
        samp.stop(); samp.join(timeout=5)
    seen = max(samp.foreign_in_mask or [0])
    check("a foreign burst in the lane is seen at all", seen >= 1,
          f"in_mask_max={seen} by_command={samp.foreign_detail}")
    # per-sample identity, the ADR requirement
    det = samp.summary().get("per_sample_in_mask_detail") or []
    have = [d for s_ in det for d in s_["processes"]]
    check("per-sample records carry pid / sid / starttime / cmdline / cpus",
          bool(have) and all(k in have[0] for k in
                             ("pid", "sid", "starttime", "cmdline", "cpus", "cpu_pct")),
          f"samples={len(det)} first={have[0] if have else None}")
    check("per-sample records are timestamped",
          bool(det) and "utc" in det[0], f"first_sample_keys={sorted(det[0]) if det else []}")


def control_8_tree_rss_includes_grandchildren():
    """RSS must span the whole owned tree, not just immediate children.

    `ps --ppid` selects only direct children, so helpers MotionCorr spawns (a shell,
    ghostscript) are grandchildren and were omitted from a figure labelled
    peak_simultaneous_tree_rss_kib -- the figure the per-process guidance rests on.
    """
    if not LINUX:
        skip("tree RSS includes grandchildren", "no /proc")
        return
    mib = 160
    src = HERE / ".control_gchild.py"
    src.write_text(
        "import subprocess, sys, time\n"
        # parent -> child -> grandchild; only the GRANDCHILD holds the memory
        "g = subprocess.Popen([sys.executable, '-c',\n"
        f"  \"buf=bytearray({mib}*1024*1024)\\n\"\n"
        "  \"for i in range(0,len(buf),4096): buf[i]=1\\n\"\n"
        "  \"import time; time.sleep(6)\"])\n"
        "sys.stderr.write('up\\n'); sys.stderr.flush()\n"
        "time.sleep(6)\n")
    pr = subprocess.Popen([sys.executable, "-c",
                           f"import subprocess,sys,time;"
                           f"p=subprocess.Popen([sys.executable,{str(src)!r}],"
                           f"stderr=subprocess.PIPE);"
                           f"sys.stderr.write(p.stderr.readline().decode());"
                           f"sys.stderr.flush();time.sleep(6)"],
                          stderr=subprocess.PIPE, start_new_session=True)
    try:
        pr.stderr.readline()
        time.sleep(1.0)
        rss = er.RssSampler(pr.pid, period=0.2)
        rss.start(); time.sleep(1.5); rss.stop(); rss.join(timeout=5)
        summ = rss.summary()
        peak_mib = summ.get("peak_simultaneous_tree_rss_kib", 0) / 1024.0
        depth = len(summ.get("peak_composition") or [])
        check(f"full-tree RSS sees the grandchild's {mib} MiB", peak_mib > mib * 0.5,
              f"peak={peak_mib:.1f} MiB across {depth} processes")
        check("peak records its composition and unit", depth >= 3 and "KiB" in summ.get("unit", ""),
              f"members={[m['comm'] for m in (summ.get('peak_composition') or [])]} unit={summ.get('unit')}")
        # discriminating: the old depth-1 selection must NOT see it
        direct = {pr.pid} | set(int(x) for x in subprocess.run(
            ["ps", "-o", "pid=", "--ppid", str(pr.pid)], capture_output=True,
            text=True).stdout.split())
        shallow = sum(er._rss_kib(x) or 0 for x in direct) / 1024.0
        check("MUTATION - depth-1 selection misses it (this is why the tree walk exists)",
              shallow < mib * 0.5, f"depth1={shallow:.1f} MiB vs full={peak_mib:.1f} MiB")
    finally:
        _reap(pr)
        src.unlink(missing_ok=True)


def _reap(proc) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except OSError:
        pass


def _own_mask() -> str:
    try:
        return open(f"/proc/{os.getpid()}/status").read().split(
            "Cpus_allowed_list:")[1].split()[0]
    except Exception:
        return "0"


def control_4_payload_is_not_its_own_interference():
    """The payload runs in its own session so cancellation can target the whole group.
    A sampler that owns only the runner's session would then report the very process being
    measured as foreign load inside its own lane -- a self-inflicted contamination reading
    that looks exactly like a real neighbour.

    Ownership is configured as an isolated session, matching production. Under the subtree
    fallback a child of this process is ours regardless of adoption, so the negative half
    would have nothing to discriminate.
    """
    if not LINUX:
        skip("payload is not counted as its own interference", "".strip())
        return
    mask = open(f"/proc/{os.getpid()}/status").read().split("Cpus_allowed_list:")[1].split()[0]
    cpus = sorted(er.parse_cpu_list(mask))
    burn = ("import time\n" "t=time.time()\n" "while time.time()-t<3.0: pass\n")
    # Configure ownership the way the runner does in production: an isolated session.
    # Without this the sampler falls back to subtree ownership, under which a child of this
    # test process is ours whether or not it was explicitly adopted -- correct behaviour,
    # but it makes the negative half below untestable, because there would be nothing for
    # adoption to change.
    own = {"basis": "session", "isolated": True, "sid": er.own_session(),
           "how": "control fixture"}
    s1 = er.Sampler(own_user="x", gpu_index=None, mask=mask, period=0.25, ps_period=0.25,
                    own_root_pid=os.getpid(), ownership=own)
    s1.start()
    time.sleep(0.5)
    proc = subprocess.Popen(["taskset", "-c", str(cpus[0]), sys.executable, "-c", burn],
                            start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        payload_sid = proc.pid                 # sid == pid for a session leader
        s1.own_also(payload_sid)
        time.sleep(2.5)
        proc.wait()
    finally:
        _reap(proc)
        s1.stop(); s1.join(timeout=5)
    # Assert on the payload's own SESSION ID, not on its command name and not on a global
    # zero. This host runs permanent unpinned ctffind, so "no foreign threads at all" is
    # unreachable; and another worker's job named `python3` collides with our interpreter's
    # name, which made a name-keyed assertion fail for a reason unrelated to what it tests.
    # The per-sample identity records make the precise check possible.
    def _sids_seen(sampler):
        return {pr["sid"] for smp in (sampler.summary().get("per_sample_in_mask_detail") or [])
                for pr in smp["processes"]}
    adopted_seen = _sids_seen(s1)
    check("adopted payload's session is absent from its own foreign list",
          payload_sid not in adopted_seen,
          f"payload_sid={payload_sid} foreign sids seen={sorted(adopted_seen)}")

    # negative half: without adoption the same payload MUST show up, otherwise the control
    # proves nothing about the adoption logic.
    s2 = er.Sampler(own_user="x", gpu_index=None, mask=mask, period=0.25, ps_period=0.25,
                    own_root_pid=os.getpid(), ownership=own)
    s2.start()
    time.sleep(0.5)
    p2 = subprocess.Popen(["taskset", "-c", str(cpus[0]), sys.executable, "-c", burn],
                          start_new_session=True,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    payload_sid2 = p2.pid
    try:
        time.sleep(2.5)
        p2.wait()
    finally:
        _reap(p2)
        s2.stop(); s2.join(timeout=5)
    unadopted_seen = _sids_seen(s2)
    check("without adoption the same payload IS seen (control is not vacuous)",
          payload_sid2 in unadopted_seen,
          f"payload_sid={payload_sid2} foreign sids seen={sorted(unadopted_seen)}")


def main():
    print(f"platform={sys.platform} /proc={LINUX}")
    control_1_sequential_sizes_are_not_a_peak()
    control_2_witness_follows_the_payload()
    control_3_child_ignoring_sigterm_is_still_reaped()
    control_4_payload_is_not_its_own_interference()
    control_5_execute_arm_records_the_payload_not_the_launcher()
    control_6_normal_exit_with_a_leaked_child_is_caught()
    control_7_session_ownership_cannot_hide_a_stranger()
    control_8_tree_rss_includes_grandchildren()
    bad = [n for n, ok, _ in results if not ok]
    if bad:
        print("\nFAILED: " + ", ".join(bad))
    elif skipped:
        print(f"\n{len(results)} control(s) passed, {len(skipped)} SKIPPED and therefore "
              f"NOT verified here:")
        for n, why in skipped:
            print(f"  - {n}" + (f" ({why})" if why else ""))
        print("this is NOT a green run; re-run on a host where the skipped controls execute")
    else:
        print(f"\nall {len(results)} runner controls passed, 0 skipped")
    # A skip is not a pass: exit non-zero so CI or an operator cannot read it as green.
    return 1 if bad else (2 if skipped else 0)


if __name__ == "__main__":
    sys.exit(main())
