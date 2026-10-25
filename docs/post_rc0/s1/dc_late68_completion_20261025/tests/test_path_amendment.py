import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ORIGINAL = HERE / "source/evaluate-original.py"
AMENDED = HERE / "source/evaluate-late68-v1.py"
ORIGINAL_SHA = "dcc5ddb3d52d14652f11214fb2a9339fb5fb63637d87dc0c82ee3a4c2d0de14d"
AMENDED_SHA = "66903f90da17c72d785f1c18ff6149b5cf4cc4ad3ed940c39027c02422e114b7"


class PathAmendmentControls(unittest.TestCase):
    def test_exact_three_path_substitutions_and_source_pins(self):
        old = ORIGINAL.read_text()
        new = AMENDED.read_text()
        self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(), ORIGINAL_SHA)
        self.assertEqual(hashlib.sha256(AMENDED.read_bytes()).hexdigest(), AMENDED_SHA)
        self.assertEqual(old.count("/mnt/clathrin/alex-motioncorr-synth-combined/truth-4096x4096.npy"), 1)
        self.assertEqual(old.count("/mnt/clathrin/alex-motioncorr-synth-combined/truth-5760x4092.npy"), 1)
        self.assertEqual(old.count("receipt = Path(rec['cwd']) / 'RECEIPT.json'"), 1)
        self.assertIn("str(ROOT / 'truth' / 'truth-4096x4096.npy')", new)
        self.assertIn("str(ROOT / 'truth' / 'truth-5760x4092.npy')", new)
        self.assertIn("ROOT / 'fixture-receipts' / name / 'RECEIPT.json'", new)
        self.assertEqual(new.count("/mnt/clathrin/alex-motioncorr-synth-combined/"), 0)
        compile(new, str(AMENDED), "exec")

    def test_plain_receipt_mapping_without_old_cwd_or_array_reads(self):
        with tempfile.TemporaryDirectory(prefix="dc-late68-path-control-") as td:
            root = Path(td) / "root"
            (root / "runs/B-control-cpu-plain").mkdir(parents=True)
            (root / "fixture-receipts/B-control-cpu-plain").mkdir(parents=True)
            (root / "src/tools").mkdir(parents=True)
            (root / "src/test-data").mkdir(parents=True)
            for module, body in {
                "check_realistic_motion.py": "def validate_star_rows(*a): raise AssertionError\ndef evaluate(*a): raise AssertionError\ndef convergence(*a): raise AssertionError\n",
                "check_realistic_image.py": "def evaluate_sum(*a): raise AssertionError\n",
                "motion_field.py": "def read_motion_star(*a): raise AssertionError\n",
            }.items():
                (root / "src/tools" / module).write_text(body)
            ident = "B-control-cpu-plain"
            rec = {
                "id": ident, "tier": "B", "backend": "cpu", "arm": "plain", "group": "fixture",
                "exit": 0, "dc_witness": "", "wall_s_unqualified": 0.0,
                "cwd": "/path/from/original/host/that/must/not/be-read",
            }
            (root / "runs" / ident / "RUN.json").write_text(json.dumps(rec))
            receipt = root / "fixture-receipts" / ident / "RECEIPT.json"
            receipt.write_text(json.dumps({"recipe": {"mapped": True}}))
            child = subprocess.run(
                [sys.executable, "-B", str(AMENDED), "B", str(root)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
            )
            self.assertEqual(child.returncode, 0, child.stderr)
            result = json.loads((root / "eval/B" / f"{ident}.json").read_text())
            self.assertEqual(result["status"], "CONTROL_ONLY")
            self.assertEqual(result["id"], ident)


if __name__ == "__main__":
    unittest.main()
