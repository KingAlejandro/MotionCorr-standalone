#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Host-only policy controls: fake monotonic clock, samples and original driver."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import postrun_idle as policy
import run_native as n

HERE = Path(__file__).resolve().parent
# Remote attempt staging supplies the same original XML beside this test.
XML = HERE / "attempt01/pre-xml.log"
if not XML.exists():
    XML = HERE / "parser-fixture.xml.log"
HEALTH = n.parse_health(XML)


def sample(util=0):
    return dict(index=2, uuid=n.UUID, assigned_apps=[], memory_mib=1,
                utilization=util, health=copy.deepcopy(HEALTH))


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Controls(unittest.TestCase):
    def run_sequence(self, samples, failure=None, delay=0):
        clock = FakeClock()
        recorded = []
        calls = []

        def read(index, deadline):
            calls.append(index)
            self.assertLess(clock.now, deadline)
            clock.now += delay
            return copy.deepcopy(samples[min(index, len(samples) - 1)])

        if failure:
            with self.assertRaises(failure):
                policy.settle(read, recorded.append, monotonic=clock.monotonic, sleep=clock.sleep)
            result = None
        else:
            result = policy.settle(read, recorded.append, monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertLessEqual(clock.now, 10 + delay)
        return result, recorded, calls, clock

    def test_busy_then_two_idle(self):
        result, rows, calls, clock = self.run_sequence([sample(6), sample(), sample()])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual([r["utilization"] for r in rows], [6, 0, 0])
        self.assertEqual([r["elapsed_seconds"] for r in rows], [0, 1, 2])
        self.assertEqual(clock.sleeps, [1, 1])

    def test_persistent_busy_timeout(self):
        _, rows, calls, clock = self.run_sequence([sample(6)], RuntimeError)
        self.assertEqual(len(rows), 10)
        self.assertEqual(clock.now, 10)

    def test_single_idle_insufficient_and_busy_resets(self):
        rows = [sample(6)] * 8 + [sample(), sample(6)]
        self.run_sequence(rows, RuntimeError)
        result, rows, _, _ = self.run_sequence([sample(), sample(6), sample(), sample()])
        self.assertEqual(result["samples"], 4)

    def test_idle_after_deadline_fails(self):
        self.run_sequence([sample()], RuntimeError, delay=5)

    def test_completion_timestamp_does_not_cross_deadline_between_reads(self):
        class CrossingClock(FakeClock):
            armed = False

            def monotonic(self):
                value = self.now
                if self.armed:
                    self.now = 10.001  # Scheduling pause after the completion read.
                return value

        original_validate = policy.validate
        for completion in (9.999, 10.0):
            with self.subTest(completion=completion):
                clock = CrossingClock()
                validated = []

                def validate_at_boundary(value):
                    original_validate(value)
                    validated.append(value)
                    if len(validated) == 2:
                        clock.now = completion
                        clock.armed = True

                with patch.object(policy, "validate", validate_at_boundary):
                    if completion < policy.WINDOW_SECONDS:
                        result = policy.settle(lambda *_: sample(), lambda _: None,
                                               monotonic=clock.monotonic, sleep=clock.sleep)
                        self.assertEqual(result["elapsed_seconds"], completion)
                        self.assertLess(result["elapsed_seconds"], result["window_seconds"])
                    else:
                        with self.assertRaises(RuntimeError):
                            policy.settle(lambda *_: sample(), lambda _: None,
                                          monotonic=clock.monotonic, sleep=clock.sleep)

    def test_every_health_field_at_every_sample_is_fatal(self):
        changes = [
            ("volatile_uncorrected_ecc", key, "1") for key in HEALTH["volatile_uncorrected_ecc"]
        ] + [("remapped_rows", key, "Yes") for key in HEALTH["remapped_rows"]]
        changes += [(None, "pending_retirement", "Yes"), (None, "recovery_action", "Reset"),
                    (None, "uuid", "wrong")]
        for position in range(3):
            for group, key, value in changes:
                for missing in (False, True):
                    with self.subTest(position=position, group=group, key=key, missing=missing):
                        bad = sample()
                        target = bad["health"][group] if group else bad["health"]
                        if missing:
                            del target[key]
                        else:
                            target[key] = value
                        _, rows, calls, clock = self.run_sequence(
                            [sample(6)] * position + [bad, sample(), sample()], (AssertionError, KeyError))
                        self.assertEqual(len(calls), position + 1)
                        self.assertEqual(len(rows), position + 1)
                        self.assertEqual(len(clock.sleeps), position)

    def test_apps_uuid_index_memory_and_missing_fields_fatal(self):
        changes = [("assigned_apps", ["foreign pid"]), ("uuid", "wrong"), ("index", 3),
                   ("memory_mib", 17), ("memory_mib", -1), ("utilization", None)]
        changes += [(key, None) for key in sample()]
        for position in range(3):
            for key, value in changes:
                with self.subTest(position=position, key=key, value=value):
                    bad = sample(6)
                    if value is None:
                        del bad[key]
                    else:
                        bad[key] = value
                    _, rows, calls, clock = self.run_sequence(
                        [sample(6)] * position + [bad, sample(), sample()], (AssertionError, KeyError))
                    self.assertEqual(len(calls), position + 1)
                    self.assertEqual(len(clock.sleeps), position)

    def test_read_failure_not_retried(self):
        clock = FakeClock()
        with self.assertRaises(OSError):
            policy.settle(lambda *_: (_ for _ in ()).throw(OSError("query failed")),
                          lambda _: self.fail("no completed sample"),
                          monotonic=clock.monotonic, sleep=clock.sleep)
        self.assertEqual(clock.sleeps, [])

    def test_original_one_shot_rejects_same_six_then_zero_sequence(self):
        # Invoke the retained original health function, not a reimplemented predicate.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            phases = []
            def command(name, argv):
                phase, kind = name.rsplit("-", 1)
                if kind == "gpus":
                    phases.append(phase)
                    text = "2, %s, NVIDIA A100, 1 MiB, %d %%\n" % (n.UUID, 6 if phase == "six" else 0)
                elif kind == "apps":
                    text = ""
                else:
                    text = XML.read_text()
                (root / (name + ".log")).write_text(text)
            with patch.object(n, "ROOT", root), patch.object(n, "command", command):
                with self.assertRaises(AssertionError):
                    n.health("six", require_idle=True)
                n.health("zero", require_idle=True)
            self.assertEqual(phases, ["six", "zero"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
