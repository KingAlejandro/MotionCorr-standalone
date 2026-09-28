#!/usr/bin/env python3
"""Negative controls for the issue #83 gate contracts.

Every gate added in response to review on PR #89 is asserted to *fail* on an
input that should fail it, and to pass on the matching good input. A gate that
has never been observed rejecting anything is not evidence, and each of the
defects these cover was of exactly that shape: a check that was present, ran,
and could not have failed.

These run on CPU in seconds and need no GPU, no built binary and no tutorial
dataset -- the point is the contract, not the science. The gates that need a
real run (unity gain equalling no gain, a non-unity gain differing from it) are
exercised by ``run_matrix.py`` itself and are not simulated here.

    python3 tools/validation_issue83/negative_controls.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matrix as declared  # noqa: E402
import products as prod  # noqa: E402
import report as rep  # noqa: E402
import run_matrix as rm  # noqa: E402
import verify_fixtures as vf  # noqa: E402
import run_all24_schedules as all24  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]


class ControlFailure(AssertionError):
    """A control did not behave as its contract requires."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ControlFailure(message)


# --------------------------------------------------------------- ground truth

def control_ground_truth_mutation(tmp: Path, fixtures_dir: Optional[Path]) -> Dict[str, Any]:
    """A single flipped byte in a truth file must make the fixture set unverified.

    The motion-truth verdicts are read from ``*_ground_truth.json``. Before this
    control the verifier checked only ``movie_sha256``, so an edited truth file
    could move a gate between PASS and FAIL while the inputs still reported as
    fully verified.
    """
    if fixtures_dir is None:
        return {"status": "skipped",
                "reason": "no --fixtures-dir given; needs real generated fixtures"}

    def verify(where: Path) -> Dict[str, Any]:
        out = where.parent / f"{where.name}-verify.json"
        proc = subprocess.run(
            [sys.executable, str(HERE / "verify_fixtures.py"),
             "--fixtures-dir", str(where), "--repo", str(REPO_ROOT),
             "--allow-missing", "--json", str(out)],
            capture_output=True, text=True)
        return {"returncode": proc.returncode,
                "report": json.loads(out.read_text()) if out.exists() else None}

    good = tmp / "fixtures-good"
    shutil.copytree(fixtures_dir, good)
    before = verify(good)
    require(before["report"] is not None, "verifier produced no report")
    require(before["report"]["verified"],
            "positive control failed: unmodified fixtures did not verify, so a "
            "later NOT VERIFIED would not be attributable to the mutation")

    # Mutate the truth file only. The movie bytes are left untouched, which is
    # precisely the case the old verifier could not see.
    bad = tmp / "fixtures-mutated"
    shutil.copytree(fixtures_dir, bad)
    targets = sorted(bad.glob("*_ground_truth.json"))
    require(bool(targets), "no *_ground_truth.json present to mutate")
    target = targets[0]
    raw = target.read_text()

    # One character, but a deliberately chosen one. A blind byte flip could
    # land in the commit stamp or in the 17th significant digit of a float --
    # both of which the verifier now excuses on purpose, so the control would
    # be asserting the opposite of what it means to. Pick a float leaf that is
    # neither, and flip its leading significant digit.
    candidates = [(leaf, value) for leaf, value in vf.flatten(json.loads(raw)).items()
                  if type(value) is float and value
                  and leaf.rsplit("/", 1)[-1] not in vf.TRUTH_PROVENANCE_KEYS
                  and raw.count(json.dumps(value)) == 1]
    require(bool(candidates),
            f"no uniquely locatable float leaf to mutate in {target.name}")
    leaf, value = candidates[0]
    rendered = json.dumps(value)
    position = next((i for i, ch in enumerate(rendered) if ch in "123456789"), None)
    require(position is not None, f"no significant digit in {rendered}")
    mutated_text = (rendered[:position]
                    + ("9" if rendered[position] != "9" else "1")
                    + rendered[position + 1:])
    mutated_value = json.loads(mutated_text)
    require(len(mutated_text) == len(rendered),
            "the mutation changed the file length; it is meant to be one byte")
    require(not vf.within_ulps(value, mutated_value),
            f"the chosen mutation {value} -> {mutated_value} is inside the "
            f"rounding tolerance, so detecting it would prove nothing")
    target.write_text(raw.replace(rendered, mutated_text))
    after = verify(bad)

    require(after["report"] is not None, "verifier produced no report after mutation")
    require(not after["report"]["verified"],
            "MUTATION UNDETECTED: a modified ground-truth file still verified")
    require(after["returncode"] != 0, "verifier exited 0 on a mutated truth file")
    flagged = [m for m in after["report"]["mismatched"] if "ground_truth" in m]
    require(bool(flagged),
            f"mutation was not attributed to the truth file: "
            f"{after['report']['mismatched']}")
    require(after["report"]["mismatched"] == flagged,
            "the movie was also reported as mismatched; the mutation should "
            f"have touched the truth file alone: {after['report']['mismatched']}")
    return {"status": "pass", "mutated_file": target.name,
            "mutated_leaf": leaf, "from": value, "to": mutated_value,
            "detected_as": flagged, "clean_run_verified": True}


# ------------------------------------------------------------- power spectrum

def _write_ps(path: Path, nx: int, ny: int) -> None:
    rm.write_mrc(path, [[0.0] * nx for _ in range(ny)])


def control_ps_wrong_dimension(tmp: Path, _fixtures: Optional[Path]) -> Dict[str, Any]:
    """A ``_PS.mrc`` of the wrong size must fail the inventory.

    ``--ps_size 128`` asks for a 128x128 spectrum. Before this control the PS
    product was excluded from every geometry assertion, so a build that ignored
    the flag and wrote any readable, reproducible size passed both the
    inventory and all schedule comparisons.
    """
    row = declared.rows_by_id()["power_spectrum"]
    want = rm.expected_ps_geometry(row)
    require(want == (128, 128),
            f"the declared power-spectrum row no longer asks for 128x128: {want}")

    def inventory(ps_nx: int, ps_ny: int) -> Dict[str, Any]:
        out = tmp / f"ps-{ps_nx}x{ps_ny}"
        (out / "Movies").mkdir(parents=True, exist_ok=True)
        stem = "Movies/m01"
        _write_ps(out / f"{stem}.mrc", 64, 64)
        _write_ps(out / f"{stem}_PS.mrc", ps_nx, ps_ny)
        (out / f"{stem}.star").write_text("")
        return prod.check_products(out, [stem], [".mrc", ".star", "_PS.mrc"],
                                   {}, (64, 64), want)

    good = inventory(128, 128)
    ps_errors = [e for e in good["errors"] if "_PS.mrc" in e]
    require(not ps_errors,
            f"positive control failed: a correct 128x128 spectrum was rejected: {ps_errors}")
    require(any(name.endswith("_PS.mrc") for name in good["geometry_asserted"]),
            "the PS product was not covered by any geometry assertion at all")

    bad = inventory(256, 256)
    ps_errors = [e for e in bad["errors"] if "_PS.mrc" in e]
    require(bool(ps_errors),
            "WRONG DIMENSION UNDETECTED: a 256x256 spectrum satisfied a "
            "128x128 request")
    return {"status": "pass", "requested": list(want),
            "accepted": "128x128", "rejected": "256x256",
            "rejection_message": ps_errors[0]}


# ------------------------------------------------------------ native witness

def _stage_logs(where: Path, stems: List[str], marked: List[str]) -> None:
    where.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        log = where / f"{stem}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f"{rm.CUDA_COMPLETED}local] completed; converged=1\n"
                       if stem in marked else "cpu path\n")


def control_resume_witness(tmp: Path, _fixtures: Optional[Path]) -> Dict[str, Any]:
    """The schedule witness must cover the executed movies, and never nothing.

    The published resume entry recorded ``native_cuda_proven: false`` and still
    passed, because the witness demanded a kernel marker for all 24 movies
    while a seeded resume correctly executes only the ones it was not handed.
    Restricting the check to the executed set makes it answerable; the empty
    set must not then make it vacuously true.
    """
    stems = [f"Movies/m{i:02d}" for i in range(1, 7)]
    seeded, executed = stems[:2], stems[2:]
    startup = f"{rm.CUDA_STARTUP}0 for global alignment."
    cases = {}

    # Executed movies marked, seeded ones deliberately not: must prove.
    good = tmp / "resume-good"
    _stage_logs(good, stems, marked=executed)
    w = all24.schedule_witness([startup], good, executed, 0)
    require(w["native_cuda_proven"],
            "positive control failed: a resume that ran every unseeded movie "
            "natively was not accepted")
    require(sorted(w["executed_movies"]) == sorted(executed),
            "the witness did not restrict itself to the executed movies")
    cases["executed_only"] = {"native_cuda_proven": True,
                              "seeded_movies_not_required": seeded}

    # The old behaviour: demand a marker for all 24, including skipped ones.
    w_all = all24.schedule_witness([startup], good, stems, 0)
    require(not w_all["native_cuda_proven"],
            "asking for a marker on skipped movies should not be provable")
    cases["old_all_movies_behaviour"] = {"native_cuda_proven": False,
                                         "why": "seeded movies have no kernel marker"}

    # Vacuity: nothing executed must not certify.
    w_empty = all24.schedule_witness([startup], good, [], 0)
    require(not w_empty["native_cuda_proven"],
            "VACUOUS WITNESS: an empty executed set certified native CUDA")
    require(w_empty["vacuous"], "an empty executed set was not flagged vacuous")
    cases["empty_executed_set"] = {"native_cuda_proven": False, "vacuous": True}

    # No stdout at all must not certify.
    w_nostdout = all24.schedule_witness([], good, executed, 0)
    require(not w_nostdout["native_cuda_proven"],
            "VACUOUS WITNESS: no invocation output certified native CUDA")
    cases["no_invocations"] = {"native_cuda_proven": False, "vacuous": True}

    # One batch invocation that never announced the device must not certify:
    # previously only the last invocation's stdout was inspected.
    w_batch = all24.schedule_witness([startup, "no device here", startup],
                                     good, executed, 0)
    require(not w_batch["native_cuda_proven"],
            "an invocation with no device announcement was accepted anyway")
    cases["one_silent_invocation"] = {
        "native_cuda_proven": False,
        "startup_marker_per_invocation": w_batch["startup_marker_per_invocation"]}

    # A movie that ran without a kernel marker must not certify.
    partial = tmp / "resume-partial"
    _stage_logs(partial, stems, marked=executed[:-1])
    w_partial = all24.schedule_witness([startup], partial, executed, 0)
    require(not w_partial["native_cuda_proven"],
            "a movie executed without a kernel marker was accepted")
    cases["executed_movie_without_marker"] = {"native_cuda_proven": False}

    # A CPU request that produced a CUDA marker is a masquerade.
    w_cpu = all24.schedule_witness(["plain cpu run"], good, executed, None)
    require(w_cpu["unexpected_cuda_marker"],
            "a CPU run showing kernel markers was not flagged as a masquerade")
    cases["cpu_masquerade"] = {"unexpected_cuda_marker": True}
    return {"status": "pass", "cases": cases}


def control_witness_is_consumed(_tmp: Path, _fixtures: Optional[Path]) -> Dict[str, Any]:
    """Reproduces the published defect: a schedule that passed without a witness.

    ``all24-summary.json`` at 7098a6f records the resume schedule with
    ``native_cuda_proven: false`` and ``passed: true``, and the aggregate was
    published as certifying native-CUDA schedule support. The witness was
    collected and then never read. This asserts the pass condition now consumes
    it, and that it is only demanded when CUDA was actually requested.
    """
    equal = {"movies_compared": 24, "movies_passed": 24,
             "preserved_seeded_outputs": True}
    proven = {"native_cuda_proven": True}
    unproven = {"native_cuda_proven": False}

    require(all24.schedule_passed(dict(equal), proven, [], 24, 0),
            "positive control failed: a witnessed, fully equal schedule did not pass")

    require(not all24.schedule_passed(dict(equal), unproven, [], 24, 0),
            "PUBLISHED DEFECT REPRODUCED: a schedule with 24/24 equal movies and "
            "no native CUDA witness was still recorded as passing")

    # On a CPU run there is nothing to prove, but a CUDA marker is a masquerade.
    require(all24.schedule_passed(dict(equal), unproven, [], 24, None),
            "a CPU schedule was required to prove native CUDA execution")
    require(not all24.schedule_passed(dict(equal), {"unexpected_cuda_marker": True},
                                      [], 24, None),
            "a CPU schedule showing CUDA markers was recorded as passing")

    # The equality requirements must still bite independently of the witness.
    require(not all24.schedule_passed(dict(equal), proven, ["Movies/m07"], 24, 0),
            "a schedule missing an image/metadata pair was recorded as passing")
    require(not all24.schedule_passed({"movies_compared": 24, "movies_passed": 23,
                                       "preserved_seeded_outputs": True},
                                      proven, [], 24, 0),
            "a schedule with a non-exact movie was recorded as passing")
    require(not all24.schedule_passed({"movies_compared": 24, "movies_passed": 24,
                                       "preserved_seeded_outputs": False},
                                      proven, [], 24, 0),
            "a resume that clobbered completed outputs was recorded as passing")
    return {"status": "pass",
            "reproduced": "resume passed with native_cuda_proven=false at 7098a6f",
            "now": "witness is part of the pass condition when --gpu is given"}


HISTORICAL_ALL24 = (REPO_ROOT / "docs" / "issue83" / "raw" / "scarf-gn0005"
                    / "all24-summary.json")


def control_report_renders_witness(_tmp: Path, _fixtures: Optional[Path]) -> Dict[str, Any]:
    """The generator must not publish the contradiction it published once.

    Run against the preserved historical record rather than a synthetic one, so
    this control fails if that record is ever quietly edited to agree with the
    prose. The record states ``all24_equal: true`` and ``resume.passed: true``
    while resume's own evidence says ``native_cuda_proven: false``; the old
    renderer printed the witness for ``base`` only, so the table read ``resume
    ... pass`` and the aggregate read complete.
    """
    if not HISTORICAL_ALL24.exists():
        return {"status": "skipped", "why": f"{HISTORICAL_ALL24} not present"}
    historical = json.loads(HISTORICAL_ALL24.read_text())
    resume = historical["schedules"]["resume"]

    # The defect must still be present in the preserved raw record.
    require(historical.get("all24_equal") is True
            and resume.get("passed") is True
            and resume["backend_evidence"].get("native_cuda_proven") is False,
            "the preserved historical record no longer contains the published "
            "contradiction; raw reports must be preserved, not corrected")

    require(not rep.all24_witness_holds(historical),
            "PUBLISHED DEFECT REPRODUCED: the generator still treats a screen "
            "with an unproven schedule witness as establishing native CUDA")

    table = "\n".join(rep.render_all24(historical))
    require("native execution NOT established" in table,
            "the rendered table still shows resume as a plain pass")
    require("| resume | 1 | 24/24 | 0 | **no** |" in table,
            "the rendered table does not carry resume's own witness cell")

    # batch ran 24 invocations but the old witness read only the last stdout,
    # so 23 startup markers are simply not in the record. That gap must be
    # reported, not filled in with the one marker that was recorded.
    batch = historical["schedules"]["batch"]
    require(len(batch.get("runs", [])) > 1
            and "startup_marker_per_invocation" not in batch["backend_evidence"],
            "the preserved record no longer shows batch's per-invocation gap")
    require(rep.witness_coverage_gap(batch),
            "a 24-invocation schedule witnessed from one stdout was treated as covered")
    require("1 of 24 invocations examined" in table,
            "the rendered table does not disclose batch's per-invocation gap")

    # Positive control: every schedule witnessed is accepted.
    good = json.loads(json.dumps(historical))
    good["schedules"]["resume"]["backend_evidence"]["native_cuda_proven"] = True
    require(not rep.all24_witness_holds(good),
            "the batch per-invocation gap stopped blocking the aggregate")
    for entry in good["schedules"].values():
        entry["backend_evidence"]["startup_marker_per_invocation"] = \
            [True] * max(1, len(entry.get("runs", [])))
    require(rep.all24_witness_holds(good),
            "positive control failed: a fully witnessed GPU screen was rejected")
    require(not rep.witness_coverage_gap(good["schedules"]["batch"]),
            "a record carrying every invocation's marker was still called uncovered")

    # A CPU screen proves nothing and is not asked to -- unless it masquerades.
    cpu = {"provenance": {"gpu": None},
           "schedules": {"repeat": {"backend_evidence": {}}}}
    require(rep.all24_witness_holds(cpu),
            "a CPU screen was required to prove native CUDA execution")
    cpu["schedules"]["repeat"]["backend_evidence"] = {"unexpected_cuda_marker": True}
    require(not rep.all24_witness_holds(cpu),
            "a CPU screen emitting CUDA markers was accepted")

    # An absent record, or one with no schedules at all, is not a pass.
    require(not rep.all24_witness_holds(None), "a missing screen was accepted")
    require(not rep.all24_witness_holds({"provenance": {"gpu": 0}, "schedules": {}}),
            "an empty screen was accepted as witnessed")
    return {"status": "pass",
            "reproduced": "all24_equal:true published with resume unproven",
            "now": "generator recomputes the witness and renders it per schedule"}


def control_report_states_input_coverage(_tmp: Path,
                                         _fixtures: Optional[Path]) -> Dict[str, Any]:
    """The report must say which digests a fixture record actually checked.

    The published report rendered *Input provenance -- VERIFIED 5/5* from a
    record that had compared ``movie_sha256`` alone; the truth files the
    motion-truth verdicts are read from were never checked (W3). Rendering a
    `/4` record naively is the mirror defect: four cases classified
    ``content_equal`` count as zero ``match``, so the old line would have read
    "VERIFIED -- 0/5 cases match" and told the reader nothing true.
    """
    old = {"schema": "issue83-fixture-verify/1", "verified": True,
           "manifest_ref": "HEAD", "manifest_source_commit": "e07fdec",
           "verifier_numpy_version": "1.26.4",
           "cases": {f"km_{i}": {"status": "match"} for i in range(5)}}
    text = "\n".join(rep.render_fixture_verification(old))
    require("movie_sha256` only" in text,
            "a movie-only record was rendered without saying so; this is the "
            "published W3 overclaim reappearing")
    require("W3" in text, "the caveat did not point at the withdrawal")

    # The shape actually measured on cpu64: every movie byte-identical, every
    # truth content-equal. Counting per case would call this "0 byte-identical".
    new = {"schema": "issue83-fixture-verify/4", "verified": True,
           "manifest_ref": "HEAD", "manifest_source_commit": "e07fdec",
           "verifier_numpy_version": "1.26.4",
           "content_equal": ["km_a (ground_truth)", "km_b (ground_truth)"],
           "cases": {"km_a": {"status": "content_equal",
                              "movie": {"status": "match"},
                              "ground_truth": {"status": "content_equal"}},
                     "km_b": {"status": "content_equal",
                              "movie": {"status": "match"},
                              "ground_truth": {"status": "content_equal"}},
                     "km_c": {"status": "match",
                              "movie": {"status": "match"},
                              "ground_truth": {"status": "match"}}}}
    text = "\n".join(rep.render_fixture_verification(new))
    require("Movies (`movie_sha256`): 3 match" in text,
            f"three byte-identical movies were not reported as such: {text}")
    require("1 match, 2 content equal" in text,
            f"the truth files' two kinds of agreement were not distinguished: "
            f"{text}")
    require("km_a (ground_truth)" in text,
            "the content-equal cases were not named")
    require("movie_sha256` only" not in text,
            "a record that did check the truth files was captioned as if it "
            "had not")

    bad = dict(new, verified=False, mismatched=["km_c (ground_truth)"],
               content_equal=[])
    bad["cases"] = {"km_c": {"status": "MISMATCH",
                             "movie": {"status": "match"},
                             "ground_truth": {"status": "MISMATCH"}}}
    text = "\n".join(rep.render_fixture_verification(bad))
    require("NOT VERIFIED" in text and "km_c (ground_truth)" in text,
            f"a mismatched fixture set was not reported as such: {text}")
    require("1 MISMATCH" in text,
            f"the mismatch was not counted against the truth files: {text}")

    absent = "\n".join(rep.render_fixture_verification(None))
    require("Not checked" in absent,
            "an absent fixture record rendered as though the check had passed")
    return {"status": "pass",
            "reproduced": "VERIFIED 5/5 rendered from a movie-only record",
            "now": "schema is disclosed; byte-identical and content-equal are "
                   "counted separately and the excused cases are named"}


# ------------------------------------------------------- schedule completeness

def _all24_report(schedules: Dict[str, Any]) -> Dict[str, Any]:
    return {"schedules": dict(schedules), "movies_in_star": all24.EXPECTED_MOVIES,
            "errors": []}


def control_partial_schedules(_tmp: Path, _fixtures: Optional[Path]) -> Dict[str, Any]:
    """An incomplete or empty schedule set must not certify ``all24_equal``."""
    passing = {"passed": True}
    cases = {}

    full = all24.certify(_all24_report(
        {"base": passing, "repeat": passing, "batch": passing, "resume": passing}))
    require(full["all24_equal"],
            "positive control failed: a complete, fully passing screen did not certify")
    require(not full["partial_screen"], "a complete screen was labelled partial")
    cases["complete"] = {"all24_equal": True, "partial_screen": False}

    for name, present in (("repeat_only", {"base": passing, "repeat": passing}),
                          ("empty", {}),
                          ("missing_resume", {"base": passing, "repeat": passing,
                                              "batch": passing})):
        got = all24.certify(_all24_report(present))
        require(not got["all24_equal"],
                f"VACUOUS CERTIFICATION: '{name}' certified all24_equal with "
                f"schedules {sorted(present)}")
        require(got["partial_screen"], f"'{name}' was not labelled a partial screen")
        require(bool(got["missing_required_schedules"]),
                f"'{name}' did not name the schedules it was missing")
        cases[name] = {"all24_equal": False, "partial_screen": True,
                       "missing": got["missing_required_schedules"],
                       "schedules_passed": got["schedules_passed"]}

    # A present-but-failing schedule must also block certification.
    failing = all24.certify(_all24_report(
        {"base": passing, "repeat": passing, "batch": passing,
         "resume": {"passed": False}}))
    require(not failing["all24_equal"], "a failing required schedule still certified")
    cases["resume_failed"] = {"all24_equal": False, "partial_screen": False}
    return {"status": "pass", "cases": cases}


# ---------------------------------------------------------- input provenance

def control_input_hashes(tmp: Path, _fixtures: Optional[Path]) -> Dict[str, Any]:
    """Differing input bytes must produce a differing provenance record."""
    runroot = tmp / "runroot"
    (runroot / "Movies").mkdir(parents=True, exist_ok=True)
    star = runroot / "movies.star"
    star.write_text("data_movies\nloop_\n_rlnMicrographMovieName #1\n"
                    "Movies/a.mrcs\nMovies/b.mrcs\n")
    (runroot / "Movies" / "a.mrcs").write_bytes(b"movie-a")
    (runroot / "Movies" / "b.mrcs").write_bytes(b"movie-b")
    (runroot / "Movies" / "gain.mrc").write_bytes(b"gain-v1")

    names = all24.read_movie_names(star)
    require(names == ["Movies/a.mrcs", "Movies/b.mrcs"],
            f"movie names were not read from the STAR: {names}")
    first = all24.input_hashes(runroot, star, names, "Movies/gain.mrc")
    require(first["movies_hashed"] == 2, "not every movie was hashed")
    require(first["star"]["sha256"] and first["gainref"]["sha256"],
            "the STAR or the gain reference went unhashed")
    require(all(first["harness"].values()), "the harness itself went unhashed")

    # Same paths, different bytes: the record must not be identical.
    (runroot / "Movies" / "b.mrcs").write_bytes(b"movie-b-CHANGED")
    (runroot / "Movies" / "gain.mrc").write_bytes(b"gain-v2")
    second = all24.input_hashes(runroot, star, names, "Movies/gain.mrc")
    require(first["movies"]["Movies/b.mrcs"]["sha256"]
            != second["movies"]["Movies/b.mrcs"]["sha256"],
            "CHANGED INPUT UNDETECTED: a rewritten movie produced the same record")
    require(first["gainref"]["sha256"] != second["gainref"]["sha256"],
            "CHANGED INPUT UNDETECTED: a rewritten gain produced the same record")
    require(first["movies"]["Movies/a.mrcs"]["sha256"]
            == second["movies"]["Movies/a.mrcs"]["sha256"],
            "an untouched movie's digest changed")

    # A movie named in the STAR but absent must be reported, not skipped.
    (runroot / "Movies" / "b.mrcs").unlink()
    third = all24.input_hashes(runroot, star, names, "Movies/gain.mrc")
    require(third["movies_missing"] == ["Movies/b.mrcs"],
            f"a missing movie was not reported: {third['movies_missing']}")
    return {"status": "pass",
            "detected": ["rewritten movie", "rewritten gain", "missing movie"],
            "harness_files_hashed": sorted(first["harness"])}


# ------------------------------------------------------- cross-row equalities

def control_cross_row_consumed(_tmp: Path, _fixtures: Optional[Path]) -> Dict[str, Any]:
    """Every declared neutral equivalence must have a consumer and a control."""
    require(bool(declared.NEUTRAL_EQUIVALENCES), "no neutral equivalence is declared")
    require(bool(declared.NEUTRAL_NEGATIVE_CONTROLS),
            "no negative control is declared, so the equivalence cannot fail")

    known = set(declared.rows_by_id())
    for a, b, allowed, rationale in declared.NEUTRAL_EQUIVALENCES:
        require({a, b} <= known, f"equivalence names an undeclared row: {a}, {b}")
        require(bool(rationale),
                f"equivalence {a} == {b} states no reason for its allowance")
        require(all(f.startswith("_rln") for f in allowed),
                f"equivalence {a} == {b} allows something that is not a STAR "
                f"field: {list(allowed)}")
    for a, b, _why in declared.NEUTRAL_NEGATIVE_CONTROLS:
        require({a, b} <= known, f"negative control names an undeclared row: {a}, {b}")

    # Absent rows must make the pair unrun and noisy, never silently equal.
    out = rm.check_cross_row_equalities([], Path("/nonexistent"), Path("/nonexistent"))
    require(not out["holds"],
            "SILENT PASS: cross-row relations held with no rows attempted at all")
    require(all(e["status"] == "unrun" for e in out["equal"] + out["differ"]),
            "an uncomparable pair was not reported as unrun")
    require(len(out["errors"]) >= len(declared.NEUTRAL_EQUIVALENCES)
            + len(declared.NEUTRAL_NEGATIVE_CONTROLS),
            "not every unrun relation was reported")

    # A row that failed is not a basis for comparison either.
    failed = [{"row_id": "gain_unity", "status": "fail"},
              {"row_id": "gain_none", "status": "pass",
               "dataset": {"movies": ["Movies/m01"]}}]
    out2 = rm.check_cross_row_equalities(failed, Path("/nonexistent"),
                                         Path("/nonexistent"))
    require(not out2["holds"], "a failed row was silently treated as comparable")
    return {"status": "pass",
            "declared_equalities": [[a, b, list(allowed)] for a, b, allowed, _
                                    in declared.NEUTRAL_EQUIVALENCES],
            "declared_negative_controls": [[a, b] for a, b, _ in
                                           declared.NEUTRAL_NEGATIVE_CONTROLS]}


def control_truth_provenance(tmp: Path, _fixtures: Optional[Path]) -> Dict[str, Any]:
    """A regenerated truth is excused for the stamp and the last bit, nothing more.

    Two excuses, both measured. The generator writes the current commit into
    every truth file, so a regenerated fixture cannot match a digest recorded at
    another commit even when the motion is bit-identical -- cpu64 at 93d427e,
    four cases, exactly one differing leaf of 4132. And a derived float can
    round differently between NumPy builds -- cpu64 at 8298158, km_local_hisnr,
    two noise statistics 1 ULP apart while the movie digest matched exactly.

    Excusing either is correct. Excusing a changed motion value would make the
    digest check ornamental, so this asserts neither allowance stretches: not
    by name, not by magnitude, and not at the boundary.
    """
    base = {"case": "km_x", "source_commit": "a" * 40,
            "injected_motion_field": [[0.5, -1.25], [2.0, 3.5]],
            "geometry": {"nx": 512, "ny": 512}}
    committed = json.dumps(base)

    def observed(doc: Dict[str, Any]) -> Path:
        path = tmp / "truth.json"
        path.write_text(json.dumps(doc))
        return path

    moved = json.loads(committed)
    moved["source_commit"] = "b" * 40
    got = vf.truth_difference(committed, observed(moved))
    require(got["content_equivalent"],
            f"a truth differing only in source_commit was called drift: {got}")
    require(got["differing_leaves"] == ["/source_commit"],
            f"the allowance named the wrong leaf: {got['differing_leaves']}")
    require(not got["float_rounding_leaves"],
            "a changed commit stamp was attributed to float rounding")

    drifted = json.loads(committed)
    drifted["injected_motion_field"][1][0] = 2.0000001
    got = vf.truth_difference(committed, observed(drifted))
    require(not got["content_equivalent"],
            "MUTATED MOTION EXCUSED: a changed motion value was treated as a "
            "content-equivalent difference")
    require(any("injected_motion_field" in leaf for leaf in got["unexpected_leaves"]),
            f"the drifted motion leaf was not named: {got['unexpected_leaves']}")

    both = json.loads(committed)
    both["source_commit"] = "b" * 40
    both["injected_motion_field"][0][0] = 0.6
    got = vf.truth_difference(committed, observed(both))
    require(not got["content_equivalent"],
            "a changed motion value was excused because the commit also changed")

    added = json.loads(committed)
    added["source_commit"] = "b" * 40
    added["extra_key"] = 1
    require(not vf.truth_difference(committed, observed(added))["content_equivalent"],
            "an added leaf was excused as provenance")

    removed = json.loads(committed)
    del removed["geometry"]
    require(not vf.truth_difference(committed, observed(removed))["content_equivalent"],
            "a removed leaf was excused as provenance")

    identical = vf.truth_difference(committed, observed(json.loads(committed)))
    require(not identical["content_equivalent"],
            "an identical pair was reported as a difference")

    (tmp / "bad.json").write_text("{not json")
    require(not vf.truth_difference(committed, tmp / "bad.json")["content_equivalent"],
            "an unparseable truth file was excused as provenance")

    # --- the rounding allowance, at and past its boundary -------------------
    motion = 2.0
    one_ulp = math.nextafter(motion, math.inf)
    nudged = json.loads(committed)
    nudged["injected_motion_field"][1][0] = one_ulp
    got = vf.truth_difference(committed, observed(nudged))
    require(got["content_equivalent"],
            f"a float one ULP away ({motion} vs {one_ulp}) was called drift")
    require(got["float_rounding_leaves"] == ["/injected_motion_field[1][0]"],
            f"the rounding allowance named the wrong leaf: "
            f"{got['float_rounding_leaves']}")
    require(got["float_rounding_max_relative"] < 1e-15,
            f"a difference of {got['float_rounding_max_relative']:.2e} relative "
            f"was accepted as rounding")

    far = motion
    for _ in range(vf.TRUTH_FLOAT_ULPS + 1):
        far = math.nextafter(far, math.inf)
    beyond = json.loads(committed)
    beyond["injected_motion_field"][1][0] = far
    require(not vf.truth_difference(committed, observed(beyond))["content_equivalent"],
            f"a float {vf.TRUTH_FLOAT_ULPS + 1} ULP away was excused; the "
            f"tolerance does not actually end where it says it does")

    # The step above is expressed in ULP, so it moves with the constant and
    # would still pass if the constant were raised to something absurd. This
    # one does not: 1e-12 relative is thousands of ULP and must never be
    # rounding, whatever TRUTH_FLOAT_ULPS says.
    absolute = json.loads(committed)
    absolute["injected_motion_field"][1][0] = motion * (1 + 1e-12)
    require(not vf.truth_difference(committed,
                                    observed(absolute))["content_equivalent"],
            "a difference of 1e-12 relative was accepted as rounding; that is "
            "a numerical tolerance, not a rendering artefact")

    # A tolerance that only ever sees tiny numbers is easy to get wrong in the
    # other direction: at 1e9 a "small" absolute slop of 1e-6 is still ~8 ULP.
    scaled = json.loads(committed)
    scaled["geometry"] = {"nx": 1e9, "ny": 512}
    scaled_committed = json.dumps(scaled)
    slipped = json.loads(scaled_committed)
    slipped["geometry"]["nx"] = 1e9 + 1e-6
    require(not vf.truth_difference(scaled_committed,
                                    observed(slipped))["content_equivalent"],
            "an absolute slop was accepted at large magnitude; the tolerance "
            "must be relative to the value")

    integral = json.loads(committed)
    integral["geometry"]["nx"] = 513
    require(not vf.truth_difference(committed, observed(integral))["content_equivalent"],
            "an integer that changed by one was excused as float rounding")

    retyped = json.loads(committed)
    retyped["geometry"]["nx"] = 512.0
    require(not vf.truth_difference(committed, observed(retyped))["content_equivalent"],
            "an int retyped as a float was excused; the truth file's types are "
            "part of what the digest covers")

    # Two denormals of opposite sign are a handful of ULP apart in absolute
    # terms, but a motion that reversed direction is drift at any magnitude.
    tiny = json.loads(committed)
    tiny["injected_motion_field"][0][1] = 5e-324
    tiny_committed = json.dumps(tiny)
    crossed = json.loads(tiny_committed)
    crossed["injected_motion_field"][0][1] = -5e-324
    require(not vf.truth_difference(tiny_committed,
                                    observed(crossed))["content_equivalent"],
            "a value that changed sign was excused as float rounding")

    require(vf.TRUTH_PROVENANCE_KEYS == ("source_commit",),
            f"the allowance widened beyond the single stamp it was measured "
            f"for: {vf.TRUTH_PROVENANCE_KEYS}")
    require(vf.TRUTH_FLOAT_ULPS <= 8,
            f"the rounding tolerance widened to {vf.TRUTH_FLOAT_ULPS} ULP, well "
            f"past the 1 ULP actually observed")
    return {"status": "pass", "allowance": list(vf.TRUTH_PROVENANCE_KEYS),
            "float_tolerance_ulps": vf.TRUTH_FLOAT_ULPS,
            "observed_on": ["cpu64 93d427e, 4 cases, 1 differing leaf of 4132",
                            "cpu64 8298158, km_local_hisnr, 2 noise leaves 1 ULP "
                            "apart with the movie digest matching"]}


def _verdict(image=True, trajectory=True, star=True, star_diffs=(),
             status="PASS", coverage=True) -> Dict[str, Any]:
    """A comparator result in the shape ``compare_pair`` produces."""
    checks = {"corrected_image": image, "motion_trajectory": trajectory,
              "star_fields": star}
    entry: Dict[str, Any] = {
        "checks": checks, "overall_status": status,
        "coverage_complete": coverage,
        "differences": {"star_fields": list(star_diffs)} if star is False else {},
        "passed": status == "PASS" and all(checks.values())}
    return entry


def control_provenance_allowance(_tmp: Path, _fixtures: Optional[Path]) -> Dict[str, Any]:
    """The neutral-equivalence allowance absorbs exactly what it declares.

    Measured on cpu64 at 93d427e, ``gain_unity`` and ``gain_none`` agree on the
    corrected image and the motion trajectory and differ in exactly one STAR
    field, ``_rlnMicrographGainName``, which is present only when a gain
    reference was supplied. Tolerating that is correct; tolerating STAR
    differences as a class would be a gate that cannot fail, so this asserts the
    allowance is narrow, and that the must-differ control still demands a
    numerical difference rather than a metadata one.
    """
    allowed = ("_rlnMicrographGainName",)
    gain_name = "Field '_rlnMicrographGainName' presence mismatch in block 'general'"
    other = "Field '_rlnMicrographDoseRate' value mismatch in block 'general'"

    ok, why = rm.numerically_equal(_verdict(), allowed)
    require(ok and not why, "positive control failed: an exact match was not equal")

    ok, why = rm.numerically_equal(
        _verdict(star=False, star_diffs=[gain_name], status="FAIL"), allowed)
    require(ok, f"the declared provenance difference was not tolerated: {why}")

    ok, why = rm.numerically_equal(
        _verdict(star=False, star_diffs=[gain_name, other], status="FAIL"), allowed)
    require(not ok and any("DoseRate" in w for w in why),
            "an undeclared STAR difference was absorbed by the allowance")

    ok, _ = rm.numerically_equal(
        _verdict(star=False, star_diffs=[gain_name], status="FAIL"), ())
    require(not ok, "an empty allowance still tolerated a STAR difference")

    for bad in (_verdict(image=False, star=False, star_diffs=[gain_name],
                         status="FAIL"),
                _verdict(trajectory=False, star=False, star_diffs=[gain_name],
                         status="FAIL")):
        ok, _ = rm.numerically_equal(bad, allowed)
        require(not ok, "a numerical difference was excused as provenance")

    # A comparator that named nothing, gave no verdict, or covered nothing is
    # not a basis for calling two rows equal.
    for broken, label in (
            (_verdict(star=False, star_diffs=[], status="FAIL"), "named no field"),
            (_verdict(status=None), "gave no verdict"),
            (_verdict(coverage=False, status="FAIL"), "incomplete coverage")):
        ok, _ = rm.numerically_equal(broken, allowed)
        require(not ok, f"a comparator that {label} was read as equal")
    incomplete = {"checks": {"corrected_image": True}, "overall_status": "FAIL",
                  "coverage_complete": True, "differences": {}}
    ok, _ = rm.numerically_equal(incomplete, allowed)
    require(not ok, "a comparator that never reported the trajectory was read as equal")

    # must-differ must bite on the science, not on metadata.
    require(rm.numerically_differs(_verdict(image=False, status="FAIL")),
            "a differing corrected image was not counted as a numerical difference")
    require(rm.numerically_differs(_verdict(trajectory=False, status="FAIL")),
            "a differing trajectory was not counted as a numerical difference")
    require(not rm.numerically_differs(
        _verdict(star=False, star_diffs=[gain_name], status="FAIL")),
        "VACUOUS CONTROL: two rows with identical pixels differing only in the "
        "gain-name field counted as a numerical difference, so the must-differ "
        "control would pass against a build that ignores --gainref")
    require(not rm.numerically_differs(_verdict()),
            "an exact match was counted as differing")
    require(not rm.numerically_differs({"checks": {}, "overall_status": None}),
            "a missing verdict was counted as differing")
    return {"status": "pass", "allowance": list(allowed),
            "observed_on": "cpu64 93d427e, gain_unity vs gain_none, 3/3 movies"}


CONTROLS: Dict[str, Callable[[Path, Optional[Path]], Dict[str, Any]]] = {
    "ground_truth_mutation": control_ground_truth_mutation,
    "ps_wrong_dimension": control_ps_wrong_dimension,
    "resume_native_witness": control_resume_witness,
    "witness_is_consumed": control_witness_is_consumed,
    "report_renders_witness": control_report_renders_witness,
    "report_states_input_coverage": control_report_states_input_coverage,
    "partial_schedules": control_partial_schedules,
    "input_hashes": control_input_hashes,
    "cross_row_consumed": control_cross_row_consumed,
    "provenance_allowance": control_provenance_allowance,
    "truth_provenance": control_truth_provenance,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fixtures-dir", type=Path,
                        help="Real generated fixtures, for the truth-mutation "
                             "control; that control is skipped without them")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--only", help="Comma-separated control names")
    opts = parser.parse_args()

    wanted = ([s.strip() for s in opts.only.split(",") if s.strip()]
              if opts.only else list(CONTROLS))
    unknown = [name for name in wanted if name not in CONTROLS]
    if unknown:
        parser.error(f"unknown controls: {', '.join(unknown)}")

    results: Dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="issue83-negctl-") as raw:
        tmp = Path(raw)
        for name in wanted:
            case_dir = tmp / name
            case_dir.mkdir(parents=True, exist_ok=True)
            try:
                results[name] = CONTROLS[name](case_dir, opts.fixtures_dir)
            except ControlFailure as exc:
                results[name] = {"status": "FAILED", "reason": str(exc)}
            except Exception as exc:  # a broken control is not a passing control
                results[name] = {"status": "ERROR", "reason": repr(exc)}
            print(f"{results[name]['status']:>8}  {name}"
                  + (f"  -- {results[name].get('reason', '')}"
                     if results[name]["status"] != "pass" else ""))

    report = {
        "schema": "issue83-negative-controls/1",
        "harness_sha256": rm.sha256(Path(__file__).resolve()),
        "controls": results,
        "counts": {
            "pass": sum(1 for r in results.values() if r["status"] == "pass"),
            "skipped": sum(1 for r in results.values() if r["status"] == "skipped"),
            "failed": sum(1 for r in results.values()
                          if r["status"] in ("FAILED", "ERROR")),
        },
    }
    # A skipped control is not a passing control, and is never counted as one.
    report["all_controls_pass"] = (report["counts"]["failed"] == 0
                                   and report["counts"]["pass"] == len(CONTROLS))
    if opts.json:
        opts.json.parent.mkdir(parents=True, exist_ok=True)
        opts.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["counts"], indent=2))
    if report["counts"]["skipped"]:
        print("NOTE: skipped controls are not passes; rerun with --fixtures-dir")
    return 0 if report["counts"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
