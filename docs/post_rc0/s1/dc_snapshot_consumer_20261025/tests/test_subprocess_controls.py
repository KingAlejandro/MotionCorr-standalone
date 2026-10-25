#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Harmless fake-child process controls; no evaluator JSON is passed to a child."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dc_snapshot_consumer", ROOT / "dc_snapshot_consumer.py")
consumer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(consumer)
BASELINE = ROOT / "expected/tierB-v2.json"


def fake_adapter(path: Path, scenario: str) -> None:
    baseline = str(BASELINE)
    path.write_text(f'''#!/usr/bin/env python3
import json, pathlib, sys
out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=False)
mode = {scenario!r}
summary = json.load(open({baseline!r}, encoding="utf-8"))
exit_code = 0
if mode in ("exit0-error", "exit2-error"):
    summary["state"] = "EVALUATION_ERROR"
    summary["global_error_count"] = 1
    summary["record_audit"][0]["reasons"].append("synthetic control only")
    exit_code = 2 if mode == "exit2-error" else 0
elif mode == "nonzero-complete":
    summary["state"] = "COMPLETE"
    exit_code = 1
elif mode == "exit0-complete":
    summary["state"] = "COMPLETE"
elif mode == "schema-invalid":
    summary = {{"format": summary["format"], "state": "IN_PROGRESS",
               "rows": None, "pairs": None, "regressions": None, "record_audit": None}}
elif mode in ("missing", "malformed"):
    if mode == "malformed":
        (out / "tierB-v2.json").write_text("{{bad json", encoding="utf-8")
    sys.exit(0)
(out / "tierB-v2.json").write_text(json.dumps(summary, allow_nan=False), encoding="utf-8")
(out / "coverage.md").write_text("synthetic control\\n", encoding="utf-8")
if mode == "schema-invalid":
    print("{{}}")
    sys.exit(0)
print(json.dumps({{"format": summary["format"], "state": summary["state"],
      "global_error_count": summary["global_error_count"],
      "derived_error_count": summary["derived_error_count"]}}))
sys.exit(exit_code)
''', encoding="utf-8")
    path.chmod(0o755)


class AdapterProcessControls(unittest.TestCase):
    def run_control(self, scenario: str):
        temp = tempfile.TemporaryDirectory(prefix=f"control-{scenario}-", dir=ROOT)
        self.addCleanup(temp.cleanup)
        work = Path(temp.name)
        adapter = work / "fake_adapter.py"
        fake_adapter(adapter, scenario)
        adapter_output = work / "adapter-output"
        argv, proc = consumer.invoke_adapter(adapter, Path("/unused/eval-dir"), adapter_output)
        state, stdout_obj, summary, coverage = consumer.parse_adapter_result(proc.returncode, proc.stdout, adapter_output)
        return state, proc.returncode, stdout_obj, summary, coverage, argv

    def test_exit_zero_with_error_state_is_rejected(self):
        state, code, _, summary, _, argv = self.run_control("exit0-error")
        self.assertEqual((state, code, summary["state"]), ("EXIT_STATE_MISMATCH", 0, "EVALUATION_ERROR"))
        self.assertEqual(argv[-2], "/unused/eval-dir")

    def test_nonzero_with_complete_state_is_rejected(self):
        state, code, _, summary, _, _ = self.run_control("nonzero-complete")
        self.assertEqual((state, code, summary["state"]), ("EXIT_STATE_MISMATCH", 1, "COMPLETE"))

    def test_exit_zero_with_complete_state_is_a_valid_tier_b_enum(self):
        state, code, _, summary, _, _ = self.run_control("exit0-complete")
        self.assertEqual((state, code, summary["state"]), ("READY_FOR_PARENT_REVIEW", 0, "COMPLETE"))

    def test_missing_summary_is_distinct(self):
        state, _, _, summary, coverage, _ = self.run_control("missing")
        self.assertEqual((state, summary, coverage), ("SUMMARY_MISSING", None, None))

    def test_malformed_summary_is_distinct(self):
        state, _, _, summary, coverage, _ = self.run_control("malformed")
        self.assertEqual((state, summary, coverage), ("SUMMARY_MALFORMED", None, None))

    def test_exit_two_error_state_is_a_coherent_report_not_scientific_pass(self):
        state, code, stdout, summary, coverage, _ = self.run_control("exit2-error")
        self.assertEqual((state, code, summary["state"]), ("READY_FOR_PARENT_REVIEW", 2, "EVALUATION_ERROR"))
        self.assertEqual(stdout["state"], "EVALUATION_ERROR")
        self.assertTrue(Path(coverage).is_file())

    def test_valid_in_progress_summary_keeps_its_actual_enum(self):
        state, code, stdout, summary, coverage, _ = self.run_control("ready")
        self.assertEqual((state, code, summary["state"]), ("READY_FOR_PARENT_REVIEW", 0, "IN_PROGRESS"))
        self.assertEqual(stdout["state"], "IN_PROGRESS")
        self.assertTrue(Path(coverage).is_file())

    def test_schema_invalid_nonnull_summary_writes_receipt_and_returns_nonzero(self):
        temp = tempfile.TemporaryDirectory(prefix="control-schema-invalid-", dir=ROOT)
        self.addCleanup(temp.cleanup)
        work = Path(temp.name)
        adapter = work / "fake_adapter.py"
        fake_adapter(adapter, "schema-invalid")
        out = work / "new-consumer-output"
        fake_inputs = {"hashes": {"adapter": "control-only"}, "queue": [], "runs": {}, "tier_a_ids": set()}
        args = type("Args", (), {"out": out, "baseline": BASELINE, "adapter": adapter, "eval_dir": work})()
        with patch.object(consumer, "check_inputs", return_value=fake_inputs):
            state, code = consumer.run(args)
        self.assertEqual((state, code), ("SUMMARY_FORMAT_INVALID", 1))
        receipt = json.loads((out / "dc-join.json").read_text())
        self.assertEqual(receipt["consumer_state"], "SUMMARY_FORMAT_INVALID")
        self.assertEqual(receipt["adapter_exit"], 0)
        self.assertEqual(receipt["adapter_summary_state"], "IN_PROGRESS")
        self.assertEqual(receipt["baseline_comparison"]["state"], "NOT_COMPARABLE")
        self.assertEqual(receipt["queue_run_evaluation_join"]["state"], "NOT_JOINED")
        self.assertTrue((out / "SHA256SUMS").is_file())


class QueueRunJoin(unittest.TestCase):
    def test_snapshot_counts_keep_ungraded_runs_and_orphan_separate(self):
        harvest = ROOT / "fixtures"
        queue = json.loads((harvest / "snap/dc/queue.json").read_text())
        runs = consumer.read_run_exits(harvest / "dc_run_exits.txt")
        summary = json.loads(BASELINE.read_text())
        tier_a = json.loads((harvest / "snap/dc/A-summary.json").read_text())
        tier_a_ids = {f"A-{r['case']}-{a['backend']}-{a['arm']}" for a in tier_a for r in a["results"]}
        joined = consumer.join_queue(queue, runs, tier_a_ids, summary)
        self.assertEqual(joined["queue_ids"], 1700)
        self.assertEqual(joined["run_receipts"], 1403)
        self.assertEqual(joined["no_run_receipt"], 297)
        self.assertEqual(joined["tier_b_missing_evaluation_records"], 68)
        self.assertEqual(joined["tier_c_completed_ungraded"], 519)
        self.assertEqual(joined["completed_without_terminal_grade"], 587)


if __name__ == "__main__":
    unittest.main(verbosity=2)
