#!/usr/bin/env python3
"""CPU-only cancellation controls for the genuine CUDA fault driver's lease.

Run the actual main/run_process path with real detached children and temporary
flocks. Only GPU/host admission and health queries are replaced; no GPU is used.
Signal injection is synchronous at the two reviewed ownership boundaries.
"""
import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import run_sticky_cuda_control as driver


UUID = "GPU-00000000-0000-0000-0000-000000000000"
CHILD = """
import json, pathlib, signal, sys, time
if sys.argv[2] == 'ignore':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
blocked = signal.pthread_sigmask(signal.SIG_BLOCK, [])
pathlib.Path(sys.argv[1]).write_text(json.dumps(sorted(blocked)))
if sys.argv[2] == 'exit':
    while not pathlib.Path(sys.argv[1] + '.exit').exists():
        time.sleep(0.01)
    print('completed')
    sys.exit(int(sys.argv[3]))
time.sleep(30)
"""


class Lifecycle(unittest.TestCase):
    def exercise(self, phase, first=signal.SIGTERM, repeated=signal.SIGTERM, completed_rc=0):
        original_popen = subprocess.Popen
        original_killpg = os.killpg
        original_handlers = {sig: signal.getsignal(sig)
                             for sig in (signal.SIGINT, signal.SIGTERM)}
        children = []
        events = []
        sent = []
        with tempfile.TemporaryDirectory(prefix="sticky-lifecycle-") as folder:
            root = Path(folder).resolve()
            lease_path = root / "gpu.lock"
            ready = root / "ready.json"

            def lease_held():
                # A distinct open file description must be refused even in the
                # same process; this checks the actual flock, not a mock flag.
                with lease_path.open("a") as probe:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def group_gone():
                for proc, _ in children:
                    self.assertIsNotNone(proc.returncode, "child was not reaped")
                    with self.assertRaises(ProcessLookupError,
                                           msg="detached process group survived"):
                        os.killpg(proc.pid, 0)

            def spawn(*args, **kwargs):
                lease_held()
                if phase == "spawn-failure":
                    raise OSError("injected spawn failure")
                proc = original_popen(*args, **kwargs)
                real_wait = proc.wait
                children.append((proc, real_wait))
                deadline = time.monotonic() + 5
                while not ready.exists():
                    self.assertIsNone(proc.poll(), "child exited before readiness")
                    self.assertLess(time.monotonic(), deadline, "child readiness timed out")
                    time.sleep(0.01)
                self.assertFalse(set(json.loads(ready.read_text())) & {signal.SIGINT, signal.SIGTERM},
                                 "spawn deferral blocked cancellation signals through exec")
                events.append("spawned")
                if phase == "spawn":
                    # The real Popen has returned, but run_process has not yet
                    # received its handle. Old code unwinds with a live group.
                    os.kill(os.getpid(), first)

                def wait(timeout=None):
                    lease_held()
                    if timeout == 120:
                        events.append("wait")
                        if phase == "repeated":
                            os.kill(os.getpid(), first)
                        if phase == "timeout":
                            raise subprocess.TimeoutExpired(args[0], timeout)
                    if timeout == 150:
                        events.append("term-grace")
                        if phase == "repeated":
                            # These run inside the real TERM/reap grace period,
                            # after the child has installed SIG_IGN for TERM.
                            os.kill(os.getpid(), repeated)
                            os.kill(os.getpid(), first)
                        # Bound the test, preserving the production 150 s value
                        # at the call boundary and using a real timed wait.
                        timeout = 0.05
                    if timeout == 10:
                        events.append("kill-reap")
                    rc = real_wait(timeout=timeout)
                    lease_held()
                    events.append("reaped")
                    return rc

                proc.wait = wait
                if phase == "success":
                    # A healthy process exits itself; no termination is needed.
                    Path(str(ready) + ".exit").touch()
                return proc

            def signal_group(group, sig):
                if sig != 0:
                    lease_held()
                    sent.append(sig)
                return original_killpg(group, sig)

            def health(_uuid, _work, name, settle=False):
                lease_held()
                if name == "after":
                    self.assertTrue(settle)
                    group_gone()
                events.append(name + "-health")
                return "0"

            def controls(_binary, work, _uuid):
                mode = "ignore" if phase in ("repeated", "timeout") else "normal"
                rc, console = driver.run_process(
                    [sys.executable, "-c", CHILD, str(ready),
                     "exit" if phase == "success" else mode, str(completed_rc)],
                    root, dict(os.environ), work, "control")
                self.assertEqual(phase, "success", "cancellation returned normally")
                self.assertEqual(rc, completed_rc)
                self.assertEqual(console.strip(), "completed")
                receipt = json.loads((work / "control-command.json").read_text())
                self.assertEqual(receipt["returncode"], rc)

            def local_path(value):
                if str(value) == "/tmp/motioncorr-gpu0-correctness.lock":
                    return lease_path
                return Path(value)

            def local_open(value, *args, **kwargs):
                self.assertEqual(value, "/tmp/motioncorr-bench.lock")
                return (root / "bench.lock").open(*args, **kwargs)

            try:
                with contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(driver, "Path", local_path))
                    stack.enter_context(patch.object(driver, "open", local_open, create=True))
                    stack.enter_context(patch.object(driver.sys, "platform", "linux"))
                    stack.enter_context(patch.object(driver.os, "sched_getaffinity",
                                                     return_value={0, 1}, create=True))
                    stack.enter_context(patch.dict(os.environ, CUDA_VISIBLE_DEVICES=UUID))
                    stack.enter_context(patch.object(sys, "argv", ["sticky-control",
                        "--binary", sys.executable, "--workdir", str(root / "evidence")]))
                    stack.enter_context(patch.object(driver, "command", return_value="0, " + UUID))
                    stack.enter_context(patch.object(driver, "gpu_state", health))
                    stack.enter_context(patch.object(driver, "run_controls", controls))
                    stack.enter_context(patch.object(driver.subprocess, "Popen", spawn))
                    stack.enter_context(patch.object(driver.os, "killpg", signal_group))
                    stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                    stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                    if phase == "success":
                        self.assertEqual(driver.main(), 0)
                    elif phase == "spawn-failure":
                        with self.assertRaisesRegex(OSError, "injected spawn failure"):
                            driver.main()
                    elif phase == "timeout":
                        with self.assertRaisesRegex(RuntimeError, "control: hung; bounded timeout expired"):
                            driver.main()
                    elif first == signal.SIGINT:
                        with self.assertRaises(KeyboardInterrupt):
                            driver.main()
                    else:
                        with self.assertRaisesRegex(RuntimeError, "driver interrupted by signal 15"):
                            driver.main()

                # main deliberately installs a TERM handler; the process scope
                # must restore that handler and the original SIGINT handler.
                self.assertIs(signal.getsignal(signal.SIGINT), original_handlers[signal.SIGINT])
                self.assertEqual(signal.getsignal(signal.SIGTERM).__name__, "interrupted")
                group_gone()
                self.assertEqual(events[-1], "after-health")
                if phase not in ("success", "spawn-failure"):
                    self.assertLess(events.index("reaped"), events.index("after-health"))
                    self.assertFalse((root / "evidence/control-command.json").exists(),
                                     "cancelled/timed-out command published a completion receipt")
                if phase in ("repeated", "timeout"):
                    self.assertLess(events.index("term-grace"), events.index("kill-reap"))
                    self.assertEqual(children[0][0].returncode, -signal.SIGKILL)
                    self.assertEqual(sent, [signal.SIGTERM, signal.SIGKILL])
                elif phase == "spawn":
                    self.assertEqual(sent, [signal.SIGTERM])
                else:
                    self.assertEqual(sent, [])
                # Health and reap completed while locked. Only now may another
                # owner acquire the correctness lease.
                with lease_path.open("a") as probe:
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                # Negative controls against old code must not leak their own
                # detached child, even when a survival assertion fails above.
                for sig in original_handlers:
                    signal.signal(sig, signal.SIG_IGN)
                for proc, real_wait in children:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                    real_wait(timeout=5)
                for sig, handler in original_handlers.items():
                    signal.signal(sig, handler)

    def test_spawn_registration_cancellation(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=sig):
                self.exercise("spawn", first=sig)

    def test_repeated_cancellation_during_term_reap(self):
        for first in (signal.SIGINT, signal.SIGTERM):
            for repeated in (signal.SIGINT, signal.SIGTERM):
                with self.subTest(first=first, repeated=repeated):
                    self.exercise("repeated", first=first, repeated=repeated)

    def test_timeout_is_failure_after_kill_reap(self):
        self.exercise("timeout")

    def test_spawn_failure_preserved(self):
        self.exercise("spawn-failure")

    def test_completed_child_and_command_receipt(self):
        for rc in (0, 1):
            with self.subTest(returncode=rc):
                self.exercise("success", completed_rc=rc)


if __name__ == "__main__":
    unittest.main()
