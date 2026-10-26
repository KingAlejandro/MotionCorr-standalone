#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fail-closed controls for tools/stageC_guard.sh with fake command shims and /proc/stat fixtures (no real resource read).

Each failure mode must end with its own non-zero code and never 0: failed command (14), empty/malformed/non-finite or missing
data (15), scratch accounting (16), granted-GPU stops (11, 12), busy core (13), test hook where it is not allowed (20). A valid
realistic fixture passes (0). The real guard on the real host is exercised separately, read-only, on 4GPUs.
"""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parent / "stageC_guard.sh"
GPU2 = "GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598"
FOREIGN = "3983855"
CAP = 21474836480

SHIM = '#!/bin/bash\nD="$(dirname "$0")/data"\ncase "$*" in\n  *--query-gpu*) n=gpus;;\n  *--query-compute-apps*) n=apps;;\n  *) n=$(basename "$0");;\nesac\n[ -f "$D/$n.out" ] && cat "$D/$n.out"\nexit $(cat "$D/$n.rc" 2>/dev/null || echo 0)\n'

DEFAULTS = dict(
    gpus=f"0, GPU-eddb42fe-4f9a-adde-76d3-b924e14add54, 1551, 0, 39\n1, GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d, 425, 0, 37\n"
         f"2, {GPU2}, 425, 0, 31\n3, GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d, 49769, 87, 66\n",
    apps=f"{FOREIGN}, {GPU2}, 414 MiB, /home/x/llama-server\n{FOREIGN}, GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d, 49758 MiB, /home/x/llama-server\n",
    ps="0 S 0.0 root 1 /sbin/init\n81 R 0.0 alex 4242 ps -eo psr\n",
    df="Filesystem 1-blocks Used Available Capacity Mounted on\n/dev/sda1 3000000000000 2500000000000 600000000000 81% /\n",
    du="1048576\t/scratch\n",
    free="              total        used        free      shared  buff/cache   available\nMem:   463000000000 16000000000 4000000000 1000000000 443000000000 440000000000\nSwap:  0 0 0\n",
)


def stat_text(n_cores, user, idle, skip=(), junk=None):
    out = []
    for c in range(0, 90):
        if c in skip:
            continue
        if c in n_cores:
            vals = [user(c), 0, 0, idle(c), 0, 0, 0, 0, 0, 0]
        else:
            vals = [100, 0, 100, 1000, 0, 0, 0, 0, 0, 0]
        if junk and c == junk[0]:
            vals[junk[1]] = "x"
        out.append(f"cpu{c} " + " ".join(str(v) for v in vals))
    return "\n".join(out) + "\n"


class Guard:
    def __init__(self, tmp):
        self.tmp = Path(tmp)
        self.shim = self.tmp / "shim"
        (self.shim / "data").mkdir(parents=True)
        for name in ("nvidia-smi", "ps", "df", "du", "free"):
            p = self.shim / name
            p.write_text(SHIM)
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
        for k, v in DEFAULTS.items():
            self.set(k, v)
        self.scratch = self.tmp / "scratch"
        self.scratch.mkdir()
        cores = set(range(80, 88))
        self.s1 = self.tmp / "stat1"
        self.s2 = self.tmp / "stat2"
        self.s1.write_text(stat_text(cores, lambda c: 100, lambda c: 1000))
        self.s2.write_text(stat_text(cores, lambda c: 120, lambda c: 1080))      # 20 busy of 100 -> 20 %
        self.env = dict(PATH=f"{self.shim}:{os.environ['PATH']}", STAGEC_GPU2=GPU2, STAGEC_FOREIGN_PID=FOREIGN,
                        STAGEC_SCRATCH=str(self.scratch), STAGEC_TEST_MODE="1", STAGEC_TEST_NO_SLEEP="1",
                        STAGEC_TEST_PROC_STAT_1=str(self.s1), STAGEC_TEST_PROC_STAT_2=str(self.s2), HOME=str(self.tmp))

    def set(self, name, text=None, rc=None):
        d = self.shim / "data"
        if text is not None:
            (d / f"{name}.out").write_text(text)
        if rc is not None:
            (d / f"{name}.rc").write_text(str(rc))

    def run(self, need_gpu="1", label="t", **env):
        e = dict(self.env)
        e.update(env)
        for k in [k for k, v in e.items() if v is None]:
            del e[k]
        return subprocess.run(["bash", str(GUARD), label, need_gpu], env=e, capture_output=True, text=True, timeout=60)


class GuardFailClosed(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.g = Guard(self._t.name)

    def rc(self, expect, why="", need_gpu="1", **env):
        r = self.g.run(need_gpu, **env)
        self.assertEqual(r.returncode, expect, f"{why}\n{r.stdout}\n{r.stderr}")
        if expect == 0:
            self.assertIn("guard t passed", r.stdout)
        else:
            self.assertNotIn("guard t passed", r.stdout)
            self.assertIn("STOP guard", r.stdout)
        return r

    def test_valid_realistic_fixture_passes(self):
        r = self.rc(0)
        self.assertIn("cpu80-87 busy%: cpu80 20 cpu81 20", r.stdout)
        self.assertIn("scratch used 1048576 bytes", r.stdout)

    def test_gpu_query_failures(self):
        self.g.set("gpus", rc=1); self.rc(14, "nvidia-smi gpu query exits non-zero")
        self.g.set("gpus", rc=0, text=""); self.rc(15, "empty GPU table")
        self.g.set("gpus", text=DEFAULTS["gpus"].replace(", 0, 31", ", N/A, 31")); self.rc(15, "non-numeric utilisation")
        self.g.set("gpus", text=DEFAULTS["gpus"].replace(", 425, 0, 31", ", 425, nan, 31")); self.rc(15, "NaN utilisation")
        self.g.set("gpus", text=DEFAULTS["gpus"].replace(", 0, 31", ", 101, 31")); self.rc(15, "utilisation out of range")
        self.g.set("gpus", text=DEFAULTS["gpus"].replace(", 425, 0, 31", ", 425, 31")); self.rc(15, "malformed row")
        self.g.set("gpus", text=DEFAULTS["gpus"].replace(GPU2, "GPU-00000000-0000-0000-0000-000000000000")); self.rc(15, "granted UUID absent")
        self.g.set("gpus", text=DEFAULTS["gpus"] + f"4, {GPU2}, 1, 0, 30\n"); self.rc(15, "granted UUID twice")
        self.g.set("gpus", text=DEFAULTS["gpus"].replace(", 425, 0, 31", ", -, 0, 31")); self.rc(15, "non-numeric memory")
        self.g.set("gpus", text=DEFAULTS["gpus"]); self.rc(0, "restored")

    def test_compute_app_failures_and_stop_rules(self):
        self.g.set("apps", rc=1); self.rc(14, "compute-app query fails")
        self.g.set("apps", rc=0, text="garbage line\n"); self.rc(15, "malformed compute-app line")
        self.g.set("apps", text=f"{FOREIGN}, {GPU2}, notmem, name\n"); self.rc(15, "memory field malformed")
        self.g.set("apps", text=f"abc, {GPU2}, 5 MiB, name\n"); self.rc(15, "pid not numeric")
        self.g.set("apps", text=""); self.rc(0, "empty compute-app answer is valid")
        self.g.set("apps", text=DEFAULTS["apps"] + f"4242, {GPU2}, 100 MiB, other\n"); self.rc(11, "other compute app on GPU2")
        self.g.set("apps", text=DEFAULTS["apps"] + "4242, GPU-eddb42fe-4f9a-adde-76d3-b924e14add54, 100 MiB, other\n"); self.rc(0, "another app on a different GPU is not this guard's concern")
        self.g.set("apps", text=DEFAULTS["apps"])
        self.g.set("gpus", text=DEFAULTS["gpus"].replace(", 425, 0, 31", ", 425, 51, 31")); self.rc(12, "granted GPU utilisation above 50")
        self.rc(0, "the same utilisation is only read, not enforced, when no GPU is needed", need_gpu="0")
        self.g.set("gpus", text=DEFAULTS["gpus"].replace(", 425, 0, 31", ", 425, 50, 31")); self.rc(0, "exactly 50 passes (threshold unchanged)")

    def test_cpu_sample_failures(self):
        cores = set(range(80, 88))
        base1 = stat_text(cores, lambda c: 100, lambda c: 1000)
        ok2 = lambda f: stat_text(cores, lambda c: 120, lambda c: 1080, **f)
        cases = [
            ("missing core 83 in the second sample", dict(skip=(83,)), 15),
            ("non-numeric field", dict(junk=(84, 4)), 15),
        ]
        for why, kw, code in cases:
            self.g.s2.write_text(ok2(kw)); self.rc(code, why)
        self.g.s2.write_text(stat_text(cores, lambda c: 100, lambda c: 1000)); self.rc(15, "zero delta on every core")
        self.g.s2.write_text(stat_text(cores, lambda c: 120 if c != 85 else 100, lambda c: 1080 if c != 85 else 1000)); self.rc(15, "zero delta on one core")
        self.g.s2.write_text(stat_text(cores, lambda c: 50, lambda c: 900)); self.rc(15, "counters went backwards")
        self.g.s2.write_text(""); self.rc(15, "empty second sample")
        self.g.s2.write_text("garbage\n"); self.rc(15, "no per-core rows")
        self.g.s1.write_text(base1.replace("cpu81 ", "cpux ", 1)); self.g.s2.write_text(ok2({})); self.rc(15, "core 81 missing from the first sample")
        self.g.s1.write_text(base1); self.g.s2.write_text(ok2({})); self.rc(0, "restored")
        self.rc(15, "fixture file missing", STAGEC_TEST_PROC_STAT_2=str(self.g.tmp / "nope"))
        busy = stat_text(cores, lambda c: 160 if c == 86 else 120, lambda c: 1040 if c == 86 else 1080)  # core 86: 60/100
        self.g.s2.write_text(busy); r = self.rc(13, "a core above 50 percent"); self.assertIn("cpu86 60", r.stdout)
        self.g.s2.write_text(stat_text(cores, lambda c: 150 if c == 86 else 120, lambda c: 1050 if c == 86 else 1080)); self.rc(0, "exactly 50 passes")

    def test_other_resource_failures(self):
        for name, code in (("ps", 14), ("df", 14), ("du", 14), ("free", 14)):
            self.g.set(name, rc=1); self.rc(code, f"{name} exits non-zero"); self.g.set(name, rc=0)
        self.g.set("ps", text=""); self.rc(15, "empty process list"); self.g.set("ps", text=DEFAULTS["ps"])
        self.g.set("df", text=DEFAULTS["df"].replace("600000000000", "-")); self.rc(16, "df available not numeric")
        self.g.set("df", text="Filesystem\n"); self.rc(16, "df has no data row")
        self.g.set("df", text=DEFAULTS["df"].replace("600000000000", str(CAP - 1048576 - 1))); self.rc(16, "df room below the cap headroom")
        self.g.set("df", text=DEFAULTS["df"].replace("600000000000", str(CAP - 1048576))); self.rc(0, "exactly the headroom passes")
        self.g.set("df", text=DEFAULTS["df"])
        self.g.set("du", text="abc\t/s\n"); self.rc(16, "scratch use not numeric")
        self.g.set("du", text=f"{CAP + 1}\t/s\n"); self.rc(16, "scratch above the frozen cap")
        self.g.set("du", text=f"{CAP}\t/s\n"); self.rc(0, "scratch exactly at the cap passes with enough df")
        self.g.set("du", text=DEFAULTS["du"])
        self.g.set("free", text="no memory line\n"); self.rc(15, "no Mem row")
        self.g.set("free", text=DEFAULTS["free"].replace("440000000000", "x")); self.rc(15, "available not numeric")
        self.g.set("free", text=DEFAULTS["free"].replace("440000000000", "500000000000")); self.rc(15, "available above total")
        self.g.set("free", text=DEFAULTS["free"].replace("440000000000", "0")); self.rc(15, "no available memory")
        self.g.set("free", text=DEFAULTS["free"]); self.rc(0, "restored")

    def test_environment_and_arguments(self):
        self.rc(15, "malformed UUID", STAGEC_GPU2="GPU-nope")
        self.rc(15, "missing UUID", STAGEC_GPU2=None)
        self.rc(15, "non-numeric foreign pid", STAGEC_FOREIGN_PID="abc")
        self.rc(16, "scratch directory missing", STAGEC_SCRATCH=str(self.g.tmp / "absent"))
        self.assertEqual(self.g.run("2").returncode, 15)
        self.assertEqual(self.g.run("").returncode, 15)

    def test_test_hooks_are_rejected_outside_tests(self):
        self.rc(20, "hook without test mode", STAGEC_TEST_MODE=None)
        self.rc(20, "hook in a real run", STAGEC_REAL="1")
        env = {k: v for k, v in self.g.env.items() if not k.startswith("STAGEC_TEST_")}
        env["STAGEC_REAL"] = "1"
        r = subprocess.run(["bash", str(GUARD), "t", "1"], env=env, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(r.returncode, 20, "a real run without hooks proceeds to the real reads")
        self.assertNotEqual(r.returncode, 0 if not os.path.exists("/proc/stat") else 99)

    def test_missing_proc_stat_is_a_stop_not_zero_percent(self):
        self.g.s1.write_text(stat_text({90}, lambda c: 1, lambda c: 1))   # no cores 80-87 at all
        self.g.s2.write_text(stat_text({90}, lambda c: 2, lambda c: 2))
        self.g.s1.write_text("".join(l + "\n" for l in self.g.s1.read_text().splitlines() if not any(l.startswith(f"cpu{n} ") for n in range(80, 88))))
        self.g.s2.write_text("".join(l + "\n" for l in self.g.s2.read_text().splitlines() if not any(l.startswith(f"cpu{n} ") for n in range(80, 88))))
        r = self.rc(15, "cores 80-87 absent must not read as idle")
        self.assertIn("MISSING", r.stdout)


if __name__ == "__main__":
    unittest.main()
