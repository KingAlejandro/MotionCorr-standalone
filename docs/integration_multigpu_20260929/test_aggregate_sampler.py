#!/usr/bin/env python3
"""Controls for aggregate_sampler.py.

The load-bearing property is that the published peak is a SIMULTANEOUS sweep
total, not a sum of per-process high-water marks. Control 1 is built so those
two answers differ by a factor of two: two children hold the same amount of
memory, but never at the same time. A sum-of-peaks implementation reports ~2x
and fails; the sweep-total implementation reports ~1x and passes.

Exits 2 when the platform cannot run the controls. A skip that exits 0 reads as
a pass in CI, having verified nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate_sampler import AggregateSampler  # noqa: E402

MIB = 40
# Hold, free, then idle -- so the two children below never overlap their peaks.
HOLDER = (
    "import sys,time;n=int(sys.argv[1]);d=float(sys.argv[2]);"
    "time.sleep(d);"
    "b=bytearray(n*1024*1024);"
    "[b.__setitem__(i,1) for i in range(0,len(b),4096)];"
    "time.sleep(1.2);del b;time.sleep(0.3)"
)
PARENT = (
    "import subprocess,sys,time;"
    "c=subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],'0']);"
    "c.wait()"
)


class TestAggregateSampler(unittest.TestCase):
    def _run(self, procs, interval=0.05, settle=0.0):
        s = AggregateSampler([p.pid for p in procs], [], interval)
        s.start()
        for p in procs:
            p.wait()
        time.sleep(settle)
        s.stop()
        s.join(timeout=5)
        return s.record()

    def test_1_peak_is_simultaneous_not_sum_of_peaks(self):
        """Two equal, non-overlapping peaks must read as one peak, not two."""
        a = subprocess.Popen([sys.executable, "-c", HOLDER, str(MIB), "0.0"])
        b = subprocess.Popen([sys.executable, "-c", HOLDER, str(MIB), "2.0"])
        rec = self._run([a, b])
        self.assertGreater(rec["sweeps"], 20, "too few sweeps to conclude anything")
        peak_mib = rec["peak_simultaneous_host_rss_kib"] / 1024
        # One holder plus two interpreters, comfortably under two holders.
        self.assertGreater(peak_mib, MIB * 0.8,
                           f"one live holder not observed at all: {peak_mib:.1f} MiB")
        self.assertLess(peak_mib, MIB * 1.8,
                        f"peak {peak_mib:.1f} MiB looks like a sum of two "
                        f"separately observed {MIB} MiB peaks")

    def test_2_overlapping_peaks_do_add_up(self):
        """Negative control for test 1: when they DO overlap, the total rises.

        Without this, an implementation that always reported one child's RSS
        would pass test 1 for the wrong reason.
        """
        a = subprocess.Popen([sys.executable, "-c", HOLDER, str(MIB), "0.0"])
        b = subprocess.Popen([sys.executable, "-c", HOLDER, str(MIB), "0.0"])
        rec = self._run([a, b])
        peak_mib = rec["peak_simultaneous_host_rss_kib"] / 1024
        self.assertGreater(peak_mib, MIB * 1.8,
                           f"two concurrent {MIB} MiB holders read as "
                           f"{peak_mib:.1f} MiB; the sweep is not aggregating")

    def test_3_grandchildren_are_counted(self):
        """ghostscript is a grandchild of the launcher, so the walk must recurse."""
        p = subprocess.Popen([sys.executable, "-c", PARENT, HOLDER, str(MIB)])
        rec = self._run([p])
        peak_mib = rec["peak_simultaneous_host_rss_kib"] / 1024
        self.assertGreater(peak_mib, MIB * 0.8,
                           f"grandchild holding {MIB} MiB not counted: "
                           f"{peak_mib:.1f} MiB")

    def test_4_no_sweeps_publishes_null_not_zero(self):
        s = AggregateSampler([1], [], 1.0)          # never started
        rec = s.record()
        self.assertEqual(rec["sweeps"], 0)
        self.assertIsNone(rec["peak_simultaneous_host_rss_kib"],
                          "a peak of 0 would read as 'measured, and small'")
        self.assertIsNone(rec["peak_gpu_mib_all_uuids"])

    def test_5_interval_is_published_with_the_figure(self):
        p = subprocess.Popen([sys.executable, "-c", HOLDER, "4", "0.0"])
        rec = self._run([p])
        self.assertEqual(rec["interval_s"], 0.05)
        self.assertIsNotNone(rec["observed_sweep_spacing_s"])
        self.assertIn("max", rec["observed_sweep_spacing_s"])


if __name__ == "__main__":
    if not Path("/proc").is_dir():
        print("SKIP: no /proc on this platform; these controls verified nothing.")
        raise SystemExit(2)
    r = unittest.main(exit=False, verbosity=2).result
    raise SystemExit(0 if r.wasSuccessful() else 1)
