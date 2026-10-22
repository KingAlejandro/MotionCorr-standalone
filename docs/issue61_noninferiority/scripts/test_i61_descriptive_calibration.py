#!/usr/bin/env python3
"""Host-only synthetic/CLI controls; no cryo-EM truth or native validation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import i61_oc_summary as oc
import i61_thinning_plan as thinning


SCRIPTS = Path(__file__).resolve().parent
THREADS = {key: "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                              "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS")}


def encoded(value):
    return json.dumps(value, allow_nan=False).encode()


def fixture():
    movies = ["MotionCorr/movie 00022.mrc", "MotionCorr/movie_00023.mrc", "MotionCorr/movie_00024.mrc"]
    preamble = ("# SYNTHETIC host fixture\r\ndata_optics\r\nloop_\r\n_rlnOpticsGroup #1\r\n"
                "_rlnOpticsGroupName #2\r\n1 'optics group 1'\r\n\r\ndata_particles\r\nloop_\r\n"
                "_rlnImageName #1\r\n_rlnMicrographName #2\r\n_rlnRandomSubset #3\r\n"
                "_rlnAngleRot #4\r\n_rlnOriginXAngst #5\r\n_rlnOpticsGroup #6\r\n_rlnCustomMetadata #7\r\n")
    rows = []
    for movie_index, (movie, counts) in enumerate(zip(movies + ["dev_movie.mrc"], [(6, 8), (8, 10), (10, 12), (4, 6)])):
        for half, count in enumerate(counts, 1):
            for index in range(count):
                rows.append(f"{len(rows) + 1:06d}@stack.mrcs '{movie}' {half} {movie_index + .125} "
                            f"{index - .75} 1 'metadata {index}' # retained comment\r\n")
    suffix = "\r\n# keep particle comment\r\ndata_extra\r\n_rlnOtherMetadata 7\r\n"
    return (preamble + "".join(rows) + suffix).encode(), movies, preamble.encode(), suffix.encode()


class PlannerControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="i61-thinning-controls-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.movies, self.prefix, self.suffix = fixture()
        self.particles = self.root / "input.star"
        self.particles.write_bytes(self.source)
        self.design = self.root / "design.json"
        self.config = {"particles_sha256": thinning.sha256(self.source), "held_movies": self.movies}
        self.design.write_bytes(encoded(self.config))

    def plan(self, name="plan", **changes):
        options = dict(particles=self.particles, design=self.design, out=self.root / name,
                       seed=61, retain_fraction="0.4", project_root=self.root,
                       reconstruct_program="/explicit/unexecuted/relion_reconstruct", sym="D2", pad=2, ctf=True)
        options.update(changes)
        return thinning.plan(**options)

    def test_seed_reproducibility_and_strata(self):
        first, second, changed = self.plan("a"), self.plan("b"), self.plan("c", seed=62)
        self.assertEqual(first["selection"], second["selection"])
        self.assertEqual(first["subsets"], second["subsets"])
        self.assertNotEqual(first["selection"]["strata"], changed["selection"]["strata"])
        self.assertEqual([(s["input_count"], s["retained_count"]) for s in first["selection"]["strata"]],
                         [(6, 2), (8, 3), (8, 3), (10, 4), (10, 4), (12, 4)])
        for a, b in zip(first["selection"]["strata"], changed["selection"]["strata"]):
            self.assertEqual(a["retained_count"], b["retained_count"])
            self.assertEqual(a["actual_retained_fraction"], a["retained_count"] / a["input_count"])
        self.assertEqual(first["inputs"]["particles"]["count"], 64)
        self.assertEqual(first["inputs"]["particles"]["sha256"], hashlib.sha256(self.source).hexdigest())
        self.assertEqual(first["inputs"]["design"]["sha256"], hashlib.sha256(self.design.read_bytes()).hexdigest())

    def test_full_rows_metadata_halves_hashes_and_jackknife_pairing(self):
        manifest = self.plan()
        lines, _, rows = thinning.read_particles(self.source)
        selected = {r["index"] for s in manifest["selection"]["strata"] for r in s["selected_rows"]}
        for stratum in manifest["selection"]["strata"]:
            for selected_row in stratum["selected_rows"]:
                row = rows[selected_row["index"]]
                self.assertEqual(selected_row["sha256"], hashlib.sha256(lines[row["line_index"]]).hexdigest())
                self.assertEqual((row["movie"], int(row["half"])), (stratum["movie"], stratum["half"]))
        for subset in manifest["subsets"]:
            data = (self.root / "plan" / subset["star"]).read_bytes()
            self.assertTrue(data.startswith(self.prefix))
            self.assertTrue(data.endswith(self.suffix))
            expected = [r for r in rows if r["movie"] in self.movies and r["movie"] != subset["omitted_movie"]
                        and (subset["arm"] == "baseline" or r["index"] in selected)]
            removed = {r["line_index"] for r in rows if r not in expected}
            self.assertEqual(data, b"".join(line for i, line in enumerate(lines) if i not in removed))
            _, _, output = thinning.read_particles(data)
            self.assertEqual([r["values"] for r in output], [r["values"] for r in expected])
            self.assertEqual(hashlib.sha256(data).hexdigest(), subset["sha256"])
            self.assertEqual(subset["count"], len(expected))
            identities = [{"index": r["index"], "sha256": r["row_sha256"]} for r in expected]
            self.assertEqual(subset["selected_rows_sha256"], thinning.sha256(thinning.json_bytes(identities)))
            for half in (1, 2):
                values = subset["per_half"][str(half)]
                actual = sum(r["half"] == str(half) for r in expected)
                self.assertEqual(values["retained_count"], actual)
                self.assertEqual(values["actual_retained_fraction"], actual / values["baseline_count"])
        jobs_data = (self.root / "plan/jobs.json").read_bytes()
        jobs = json.loads(jobs_data)
        self.assertEqual(manifest["jobs_sha256"], thinning.sha256(jobs_data))
        self.assertEqual(manifest["job_count"], 16)  # 2 arms x (held + 3 JK) x 2 halves.
        for name in {j["subset"] for j in jobs}:
            pair = [j for j in jobs if j["subset"] == name]
            self.assertEqual({(j["arm"], j["half"]) for j in pair},
                             {(arm, half) for arm in ("baseline", "thinned") for half in (1, 2)})
            self.assertEqual(len({j["omitted_movie"] for j in pair}), 1)
        for job in jobs:
            self.assertEqual(job["status"], "UNRUN")
            self.assertEqual(job["cwd"], str(self.root.resolve()))
            self.assertIn("--ctf", job["argv"])
            star = Path(job["argv"][job["argv"].index("--i") + 1])
            self.assertEqual(job["input_star_sha256"], thinning.sha256(star.read_bytes()))
        self.assertFalse(list((self.root / "plan/rec").rglob("*.mrc")))
        self.assertEqual(manifest["design_truth_status"], "UNVALIDATED")
        self.assertFalse(manifest["scientific_certification_accepted"])
        self.assertEqual(manifest["scientific_verdict"], "INCONCLUSIVE")

    def test_overwrite_refused_and_evidence_unchanged(self):
        self.plan()
        before = {p: p.read_bytes() for p in (self.root / "plan").rglob("*") if p.is_file()}
        with self.assertRaises(FileExistsError):
            self.plan(seed=62)
        self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))

    def test_hash_binding_refuses_even_metadata_only_change(self):
        self.particles.write_bytes(self.source.replace(b"retained comment", b"changed comment", 1))
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.plan()
        self.assertFalse((self.root / "plan").exists())

    def test_duplicate_design_json_keys_refused(self):
        self.design.write_bytes(encoded(self.config)[:-1] + b', "held_movies": []}')
        with self.assertRaisesRegex(ValueError, "duplicate design JSON key"):
            self.plan()
        self.assertFalse((self.root / "plan").exists())

    def test_bad_design_and_empty_strata(self):
        for value in ([], {}, {**self.config, "held_movies": self.movies + [self.movies[0]]},
                      {**self.config, "held_movies": self.movies + ["absent"]},
                      {**self.config, "held_movies": self.movies[:1]},
                      {**self.config, "particles_sha256": "0" * 64}):
            with self.subTest(value=value):
                self.design.write_bytes(encoded(value))
                with self.assertRaises(ValueError):
                    self.plan()
                self.assertFalse((self.root / "plan").exists())
        self.design.write_bytes(encoded(self.config))
        for fraction in ("0", "-1", "1.1", "NaN", "0.01", "1/0"):
            with self.subTest(fraction=fraction), self.assertRaises((ValueError, ZeroDivisionError)):
                self.plan(retain_fraction=fraction)
        self.assertFalse((self.root / "plan").exists())

    def test_malformed_star_refused(self):
        mutations = [self.source.replace(b"data_particles", b"data_other", 1),
                     self.source + b"\ndata_particles\nloop_\n",
                     self.source + b"\ndata_particles # another particle block\nloop_\n",
                     self.source.replace(b"_rlnRandomSubset #3", b"_rlnMissing #3", 1),
                     self.source.replace(b"_rlnAngleRot #4", b"_rlnImageName #4", 1),
                     self.source.replace(b"_rlnAngleRot #4", b"_rlnAngleRot #8", 1),
                     self.source.replace(b" 1 0.125", b" 3 0.125", 1),
                     self.source.replace(b" 1 0.125", b" ? 0.125", 1),
                     self.source.replace(b"000002@", b"000001@", 1),
                     self.source.replace(b" 'metadata 0'", b"", 1),
                     self.source.replace(b"'metadata 0'", b"'unterminated", 1),
                     self.source.replace(b"000001@stack.mrcs", b";multiline", 1),
                     self.prefix + self.suffix]
        for source in mutations:
            with self.subTest(source=source[:30]), self.assertRaises(ValueError):
                thinning.read_particles(source)

    def test_empty_movie_half_refused_without_output(self):
        lines, _, rows = thinning.read_particles(self.source)
        removed = {row["line_index"] for row in rows if row["movie"] == self.movies[0] and row["half"] == "2"}
        source = b"".join(line for i, line in enumerate(lines) if i not in removed)
        self.particles.write_bytes(source)
        self.design.write_bytes(encoded({**self.config, "particles_sha256": thinning.sha256(source)}))
        with self.assertRaisesRegex(ValueError, "empty input/retained"):
            self.plan()
        self.assertFalse((self.root / "plan").exists())

    def test_actual_cli(self):
        command = [sys.executable, str(SCRIPTS / "i61_thinning_plan.py"),
                   "--particles", str(self.particles), "--design", str(self.design),
                   "--out", str(self.root / "cli"), "--seed", "61", "--retain-fraction", "0.4",
                   "--project-root", str(self.root), "--reconstruct-program", "/never/executed",
                   "--sym", "D2", "--pad", "2", "--ctf", "no"]
        result = subprocess.run(command, env={**os.environ, **THREADS}, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLAN_ONLY", result.stdout)
        self.assertNotIn("--ctf", json.loads((self.root / "cli/jobs.json").read_text())[0]["argv"])
        repeat = subprocess.run(command, env={**os.environ, **THREADS}, capture_output=True)
        self.assertEqual(repeat.returncode, 2)


class SummaryControls(unittest.TestCase):
    def setUp(self):
        self.protocol = {"protocol_id": "SYNTHETIC arithmetic control", "replication_unit": "independent synthetic draw",
                         "endpoints": [{"endpoint": name, "direction": direction, "margin": margin, "critical_value": 2.}
                                       for name, direction, margin in (("rho", "higher", .95), ("delta", "lower", .05))]}
        self.records = {"protocol_sha256": hashlib.sha256(encoded(self.protocol)).hexdigest(),
                        "replicate_ids": ["p", "f", "i"], "records": [
                            {"replicate_id": key, "endpoint": name, "estimate": value, "se": .01}
                            for name, values in (("rho", (1., .9, .95)), ("delta", (0., .1, .05)))
                            for key, value in zip(("p", "f", "i"), values)]}

    def summary(self, protocol=None, records=None):
        return oc.summarize(encoded(protocol if protocol is not None else self.protocol),
                            encoded(records if records is not None else self.records), .95)

    def test_decisions_bounds_and_closed_gate(self):
        result = self.summary()
        for endpoint in result["endpoints"].values():
            self.assertEqual(endpoint["n"], 3)
            for value in endpoint["decisions"].values():
                self.assertEqual(value["count"], 1)
                # For n=3,k=1: lower solves P(X>=1)=alpha; upper solves P(X<=1)=alpha.
                lower, upper = value["lower_one_sided"], value["upper_one_sided"]
                self.assertAlmostEqual(1 - (1 - lower) ** 3, .05)
                self.assertAlmostEqual((1 - upper) ** 3 + 3 * upper * (1 - upper) ** 2, .05)
        self.assertEqual(result["replication_unit"], self.protocol["replication_unit"])
        self.assertEqual(result["scientific_verdict"], "INCONCLUSIVE")
        self.assertIsNone(result["gate_policy"])
        self.assertFalse(result["scientific_certification_accepted"])

    def test_bound_extremes_and_decision_equality(self):
        self.assertAlmostEqual(oc.bounds(0, 10, .95)["upper_one_sided"], 1 - .05 ** .1)
        self.assertEqual(oc.bounds(0, 10, .95)["lower_one_sided"], 0)
        self.assertAlmostEqual(oc.bounds(10, 10, .95)["lower_one_sided"], .05 ** .1)
        self.assertEqual(oc.bounds(10, 10, .95)["upper_one_sided"], 1)
        for record in self.records["records"]:
            record["estimate"] = .95 if record["endpoint"] == "rho" else .05
            record["se"] = 0
        self.assertTrue(all(r["verdict"] == "PASS" for r in self.summary()["recomputed_records"]))

    def test_reject_duplicate_missing_inconsistent_and_nonfinite(self):
        mutations = []
        duplicate = copy.deepcopy(self.records)
        duplicate["records"].append(duplicate["records"][0])
        mutations.append(duplicate)
        for key, value in (("protocol_sha256", "0" * 64), ("replicate_ids", ["p", "p", "i"]),
                           ("replicate_ids", ["p", "f", "i", "missing"]), ("records", self.records["records"][:-1])):
            mutations.append({**self.records, key: value})
        for field, value in (("se", -1), ("se", True), ("estimate", "1.0"), ("verdict", "FAIL"),
                             ("endpoint", "absent"), ("replicate_id", "absent"), ("truth", .95)):
            bad = copy.deepcopy(self.records)
            bad["records"][0][field] = value
            mutations.append(bad)
        for bad in mutations:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.summary(records=bad)
        for number in (b"NaN", b"Infinity", b"1e999"):
            data = encoded(self.records).replace(b'"estimate": 1.0', b'"estimate": ' + number)
            with self.subTest(number=number), self.assertRaises(ValueError):
                oc.summarize(encoded(self.protocol), data, .95)
        with self.assertRaises(ValueError):
            oc.summarize(encoded(self.protocol), b'{"records": [], "records": []}', .95)
        for field in ("margin", "critical_value"):
            bad = copy.deepcopy(self.protocol)
            del bad["endpoints"][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.summary(protocol=bad)
        bad = copy.deepcopy(self.protocol)
        bad["endpoints"][0]["critical_value"] = 0
        with self.assertRaises(ValueError):
            self.summary(protocol=bad)
        for confidence in (0, 1, float("nan"), True):
            with self.subTest(confidence=confidence), self.assertRaises(ValueError):
                oc.summarize(encoded(self.protocol), encoded(self.records), confidence)

    def test_actual_cli_recompute_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="i61-oc-controls-") as temp:
            root = Path(temp)
            (root / "protocol.json").write_bytes(encoded(self.protocol))
            (root / "records.json").write_bytes(encoded(self.records))
            command = [sys.executable, str(SCRIPTS / "i61_oc_summary.py"), "--protocol", str(root / "protocol.json"),
                       "--records", str(root / "records.json"), "--confidence", ".95", "--out", str(root / "out.json")]
            result = subprocess.run(command, env={**os.environ, **THREADS}, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = (root / "out.json").read_bytes()
            self.assertEqual(json.loads(original)["endpoints"]["rho"]["decisions"]["PASS"]["count"], 1)
            again = subprocess.run(command, env={**os.environ, **THREADS}, capture_output=True)
            self.assertEqual(again.returncode, 2)
            self.assertEqual((root / "out.json").read_bytes(), original)
            self.records["records"][0]["verdict"] = "FAIL"
            (root / "records.json").write_bytes(encoded(self.records))
            refused = subprocess.run(command[:-1] + [str(root / "bad.json")],
                                     env={**os.environ, **THREADS}, capture_output=True)
            self.assertEqual(refused.returncode, 2)
            self.assertFalse((root / "bad.json").exists())


if __name__ == "__main__":
    unittest.main()
