"""Actual CLI controls for imported traces and STAR loop/subset boundaries."""
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import fixture_db
import mcprof
from lib import provenance as prov, runner
from test_runner import make_binary, make_data


def cli(args):
    flags = ["-O"] if sys.flags.optimize else []
    return subprocess.run([sys.executable, *flags, mcprof.__file__, *args],
                          capture_output=True, text=True, timeout=30)


class ImportedTracePreflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        (self.work / "provenance.json").write_bytes(b'{"retained": true}\n')
        (self.work / "runs.jsonl").write_bytes(b"previous raw results\n")

    def tearDown(self):
        self.tmp.cleanup()

    def rejected(self, export):
        old = {p.name: p.read_bytes() for p in self.work.iterdir()}
        result = cli(["trace", "--from-sqlite", str(export), "--work", str(self.work), "--force"])
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual({p.name: p.read_bytes() for p in self.work.iterdir()}, old,
                         "invalid import cleared or changed previous raw evidence")

    def test_missing_export_preserves_existing_work(self):
        export = self.root / "missing.sqlite"
        self.rejected(export)
        self.assertFalse(export.exists())

    def test_malformed_export_preserves_existing_work(self):
        export = self.root / "malformed.sqlite"
        export.write_bytes(b"not a SQLite database\n")
        self.rejected(export)
        self.assertEqual(export.read_bytes(), b"not a SQLite database\n")

    def test_schema_invalid_export_preserves_existing_work(self):
        export = self.root / "empty.sqlite"
        with sqlite3.connect(export) as db:
            db.execute("create table unrelated (value text)")
        before = export.read_bytes()
        self.rejected(export)
        self.assertEqual(export.read_bytes(), before)

    def test_export_inside_replaced_work_is_preserved_and_rejected(self):
        export = self.work / "trace.sqlite"
        fixture_db.build(str(export))
        self.rejected(export)

    def test_external_symlink_to_export_inside_work_is_rejected(self):
        export = self.work / "trace.sqlite"
        fixture_db.build(str(export))
        link = self.root / "alias.sqlite"
        link.symlink_to(export)
        self.rejected(link)
        self.assertTrue(link.is_symlink())

    def test_input_symlink_inside_replaced_work_is_preserved(self):
        export = self.root / "external.sqlite"
        fixture_db.build(str(export))
        before = export.read_bytes()
        link = self.work / "alias.sqlite"
        link.symlink_to(export)
        self.rejected(link)
        self.assertTrue(link.is_symlink())
        self.assertEqual(export.read_bytes(), before)

    def test_valid_external_import_still_replaces_old_work(self):
        export = self.root / "trace.sqlite"
        fixture_db.build(str(export))
        before = export.read_bytes()
        result = cli(["trace", "--from-sqlite", str(export), "--work", str(self.work), "--force"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(export.read_bytes(), before)
        self.assertFalse((self.work / "runs.jsonl").exists())
        self.assertEqual(json.loads((self.work / "trace.json").read_text())["totals"]["busy_ns"], 450)
        self.assertTrue((self.work / "timeline.json").is_file())
        self.assertTrue((self.work / "report.md").is_file())

    def test_sampled_import_retains_analysis_and_folded_stacks(self):
        export = self.root / "sampled.sqlite"
        fixture_db.build(str(export))
        result = cli(["trace", "--from-sqlite", str(export), "--work", str(self.work), "--force", "--sample"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        trace = json.loads((self.work / "trace.json").read_text())
        self.assertGreater(trace["sampling"]["samples"], 0)
        self.assertTrue((self.work / "folded.txt").read_text())


STAR = """data_movies
loop_
_metadataBefore #1
before_alpha
loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/a.tiff 1
Movies/b.tiff 1
Movies/c.tiff 1
loop_
_metadataAfter #1
_metadataValue #2
after_alpha 41
after_beta 42
"""


class MultipleStarLoops(unittest.TestCase):
    def test_only_declared_movie_loops_supply_rows_and_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "movies.star"
            text = STAR + "loop_\n_rlnOpticsGroup #1\n_rlnMicrographMovieName #2\n2 Movies/d.tiff\n"
            source.write_text(text)
            movies, rows = runner.star_movies(str(source))
            self.assertEqual(movies, ["Movies/a.tiff", "Movies/b.tiff", "Movies/c.tiff", "Movies/d.tiff"])
            self.assertEqual([text.splitlines()[i] for i, _ in rows],
                             ["Movies/a.tiff 1", "Movies/b.tiff 1", "Movies/c.tiff 1", "2 Movies/d.tiff"])

    def run_cli(self, subset):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(make_data(str(Path(tmp) / "data")))
            source = data / "movies.star"
            source.write_text(STAR)
            before = prov.sha256_file(str(source))
            binary = make_binary(str(Path(tmp) / "binary"))
            work = Path(tmp) / "work"
            args = ["run", "A=" + binary, "--data", str(data), "--work", str(work), "--no-lock",
                    "--warmup", "0", "--rounds", "1", "--lane-wait", "0", "--keep-outputs"]
            if subset:
                args += ["--movies", "2"]
            compiler = None
            try:
                if Path("/proc").is_dir():
                    # A live compiler anywhere on Linux must not stall these
                    # fake-payload CLI tests inside their 30-second deadline.
                    cc1 = Path(tmp) / "cc1"
                    shutil.copy2(shutil.which("sleep"), cc1)
                    compiler = subprocess.Popen([str(cc1), "120"])
                    witness = "%s:cc1" % compiler.pid
                    for _ in range(100):
                        if witness in prov.compilers_running():
                            break
                        time.sleep(0.01)
                    self.assertIn(witness, prov.compilers_running())
                    print("compiler control active: " + witness, flush=True)
                result = cli(args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                if compiler is not None:
                    self.assertIsNone(compiler.poll())
                    settle = json.loads((work / "provenance.json").read_text())["settle"]
                    self.assertFalse(settle["settled"])
                    self.assertIn(witness, settle["compilers"])
            finally:
                if compiler is not None:
                    compiler.terminate()
                    compiler.wait(timeout=5)
            expected = ["Movies/a.tiff", "Movies/b.tiff"] + ([] if subset else ["Movies/c.tiff"])
            staged = json.loads((work / "provenance.json").read_text())["input"]
            self.assertEqual(staged["movies"], expected)
            self.assertEqual(prov.sha256_file(str(source)), before)
            staged_text = (Path(staged["cwd"]) / staged["star"]).read_text()
            self.assertEqual(staged_text, STAR.replace("Movies/c.tiff 1\n", "") if subset else STAR)
            self.assertEqual(len(list((work / "runs").rglob("*.mrc"))), len(expected))

    def test_actual_cli_full_input_does_not_expect_metadata_products(self):
        self.run_cli(False)

    def test_actual_cli_subset_preserves_all_other_loop_rows(self):
        self.run_cli(True)


if __name__ == "__main__":
    unittest.main()
