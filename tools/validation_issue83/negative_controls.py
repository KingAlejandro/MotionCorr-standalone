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
import record_payload_env as rec  # noqa: E402
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
    # so 23 startup *banners* are simply not in the record. That is a real gap
    # in the weaker witness and must be disclosed -- but every one of the 24
    # movies carries its own kernel stage marker, written into that movie's log
    # by the CUDA path, so the schedule's products are witnessed. Conflating
    # the two made the renderer withhold a measured claim, which is its own
    # misstatement; the two are asserted separately here.
    batch = historical["schedules"]["batch"]
    require(len(batch.get("runs", [])) == 24
            and "startup_marker_per_invocation" not in batch["backend_evidence"],
            "the preserved record no longer shows batch's per-invocation gap")
    require(rep.banner_coverage(batch) == (1, 24),
            f"batch's banner coverage reads {rep.banner_coverage(batch)}, not 1 of 24")
    require(not rep.witness_coverage_gap(batch),
            "a schedule whose every movie carries a kernel stage marker was "
            "withheld as unwitnessed because one field name was absent")
    require("banner 1/24" in table,
            "the rendered table does not disclose batch's per-invocation banner gap")

    # resume is a genuine gap, and of a different kind: 16 of its 24 movies are
    # marked and the record names no executed set, so eight movies skipped and
    # eight run on the CPU are indistinguishable in it.
    resume_ev = resume["backend_evidence"]
    require("executed_movies" not in resume_ev
            and sum(1 for m in resume_ev["per_movie"].values()
                    if m.get("cuda_stage_marker")) == 16,
            "the preserved record no longer shows resume's 16-of-24 ambiguity")
    require(rep.witness_coverage_gap(resume),
            "a schedule with eight unexplained unmarked movies was called covered")

    # Positive control: every schedule witnessed is accepted.
    good = json.loads(json.dumps(historical))
    good["schedules"]["resume"]["backend_evidence"]["native_cuda_proven"] = True
    require(not rep.all24_witness_holds(good),
            "resume's unresolved 16-of-24 gap stopped blocking the aggregate")
    # What the fixed runner records: which movies it actually executed. The
    # eight preserved seeded products are not re-executed and carry no new
    # marker, so naming the executed set is what resolves the ambiguity.
    good["schedules"]["resume"]["backend_evidence"]["executed_movies"] = [
        stem for stem, m in resume_ev["per_movie"].items()
        if m.get("cuda_stage_marker")]
    require(rep.all24_witness_holds(good),
            "positive control failed: a fully witnessed GPU screen was rejected")
    require(not rep.witness_coverage_gap(good["schedules"]["resume"]),
            "a record naming its executed movies was still called uncovered")
    # The banner gap alone must never block the aggregate -- nor vanish from it.
    require(rep.banner_coverage(good["schedules"]["batch"]) == (1, 24),
            "the banner gap disappeared once the aggregate was satisfied")

    # A CPU screen proves nothing and is not asked to -- unless it masquerades.
    # It must still have run every required schedule: "nothing to prove" is a
    # statement about the backend, not a licence to skip legs.
    cpu = {"provenance": {"gpu": None},
           "schedules": {name: {"backend_evidence": {}}
                         for name in rep.REQUIRED_SCHEDULES}}
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
    require("5 movie, 0 ground truth" in text,
            f"the record did not say how many digests of each kind it "
            f"actually compared: {text}")

    # The caveat was keyed on the schema string, so it printed for `/1` and
    # `/2` and for nothing else. A later schema whose cases happen to carry no
    # ground-truth status is in exactly the same position and said nothing.
    modern = {"schema": "issue83-fixture-verify/5", "verified": True,
              "manifest_ref": "HEAD", "manifest_source_commit": "e07fdec",
              "cases": {f"km_{i}": {"movie": {"status": "match"}}
                        for i in range(5)}}
    text = "\n".join(rep.render_fixture_verification(modern))
    require("movie_sha256` only" in text,
            f"a current-schema record that checked no truth file was rendered "
            f"without the caveat, because the caveat read the schema string "
            f"rather than what was compared: {text}")

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


def control_report_attributes_each_section(_tmp: Path,
                                           _fixtures: Optional[Path]) -> Dict[str, Any]:
    """Sections from different runs must not render under one provenance block.

    The first native allocation (SCARF job 3511139) generated its fixtures with
    the wrong interpreter, so its fixture-dependent legs are not attributable to
    the committed manifest and had to be re-run in a second job. A report
    assembled from both is legitimate -- the integrated screen reads the
    tutorial runroot, not those fixtures -- but the header names one run, and
    without per-section attribution the reader has no way to tell which numbers
    came from where.
    """
    matrix = {"provenance": {"hostname": "gn3000.scarf.rl.ac.uk", "gpu": 0,
                             "binary_sha256": "0c5246675175ba4d" + "0" * 48,
                             "started_utc": "2026-09-28T08:04:42Z"},
              "counts": {"declared": 25, "attempted": 25, "pass": 25,
                         "fail": 0, "error": 0},
              "matrix_complete": True, "unrun_rows": [], "results": {},
              "finished_utc": "2026-09-28T08:26:50Z"}
    same = {"provenance": dict(matrix["provenance"],
                               started_utc="2026-09-28T08:10:00Z"),
            "movies_in_star": 24, "expected_movies": 24, "all24_equal": True,
            "schedules": {}, "errors": []}
    text = "\n".join(rep.render_all24(same, matrix))
    require("Source record:" in text and "gn3000" in text,
            f"the integrated screen did not name the run it came from: {text}")
    require("Not the run named in the provenance block" not in text
            and "Outside the run window" not in text,
            f"a section measured inside the header's own run window was "
            f"reported as a different run: {text}")

    # Two jobs on one node reusing one binary agree on host, device and
    # binary digest, so the identity check above cannot separate them. This is
    # not hypothetical: jobs 3511139 and 3511154 are exactly that pair, and the
    # published report is assembled from both. The declared run window is what
    # tells them apart.
    for stamp in ("2026-09-28T08:03:00Z", "2026-09-28T08:40:00Z"):
        later = {"provenance": dict(matrix["provenance"], started_utc=stamp),
                 "movies_in_star": 24, "expected_movies": 24,
                 "all24_equal": True, "schedules": {}, "errors": []}
        text = "\n".join(rep.render_all24(later, matrix))
        require("Outside the run window" in text,
                f"a section measured at {stamp}, outside the header's "
                f"{matrix['provenance']['started_utc']} to "
                f"{matrix['finished_utc']} window, rendered as part of that "
                f"run: {text}")
        require(stamp in text and matrix["finished_utc"] in text,
                f"the window divergence was announced without naming the two "
                f"times it rests on: {text}")

    # An unknown window is not evidence of divergence. A record that never
    # recorded when it finished must not make every section look foreign.
    windowless = dict(matrix)
    windowless.pop("finished_utc")
    require("Outside the run window" not in "\n".join(
                rep.render_all24(later, windowless)),
            "a missing finish time was read as proof of a different run")

    other = json.loads(json.dumps(same))
    other["provenance"]["hostname"] = "gn0005.scarf.rl.ac.uk"
    other["provenance"]["binary_sha256"] = "3860bce6165974b9" + "0" * 48
    text = "\n".join(rep.render_all24(other, matrix))
    require("Not the run named in the provenance block" in text,
            f"a screen from another host and another binary rendered as though "
            f"it were part of the matrix run: {text}")
    require("hostname" in text and "binary_sha256" in text,
            f"the divergence was announced without naming which fields differ: "
            f"{text}")

    # A device difference matters as much as a host difference: the same node
    # can hold four GPUs and a section run on device 2 is not evidence about
    # device 0.
    dev = json.loads(json.dumps(same))
    dev["provenance"]["gpu"] = 2
    require("Not the run named in the provenance block"
            in "\n".join(rep.render_all24(dev, matrix)),
            "a screen from a different device was folded into the header's run")

    # The merged truth tool names its binary and device at the top level, not
    # in a provenance block; reading only `provenance` would silently drop it.
    truth = {"tool": "run_known_motion_gates.py", "gpu": 0,
             "binary": "/work4/.../build-cuda/motioncorr",
             "results": [{"case": "km_global_hisnr", "role": "gate",
                          "status": "PASS"}]}
    text = "\n".join(rep.render_numerical(truth, None, matrix))
    require("Source record for the motion-truth gates:" in text
            and "device 0" in text,
            f"the motion-truth section did not name its own source: {text}")

    # The CPU diagnostic is a third run -- another host, another binary, in
    # every report so far another day -- and it was rendered underneath the
    # motion-truth attribution with no source of its own, which is the exact
    # confusion per-section attribution exists to prevent.
    diag = {"tool": "run_known_motion_gates.py",
            "provenance": {"hostname": "small-refmac-machine", "gpu": None,
                           "started_utc": "2026-09-26T11:20:00Z"},
            "results": [{"case": "km_global_hisnr", "role": "diagnostic",
                         "status": "PASS"}]}
    text = "\n".join(rep.render_numerical(truth, diag, matrix))
    require("Source record for the CPU diagnostic:" in text,
            f"the CPU diagnostic was rendered under the motion-truth "
            f"attribution with no source of its own: {text}")
    require("small-refmac-machine" in text,
            f"the CPU diagnostic's own host was never named: {text}")
    require(text.count("Not the run named in the provenance block") >= 1,
            f"a diagnostic from another host under a GPU header was not "
            f"flagged as a different run: {text}")

    # A CPU record is a source too, and differs from a GPU header.
    cpu = {"provenance": {"hostname": "small-refmac-machine", "gpu": None},
           "movies_in_star": 24, "expected_movies": 24, "schedules": {},
           "errors": []}
    text = "\n".join(rep.render_all24(cpu, matrix))
    require("CPU" in text and "Not the run named in the provenance block" in text,
            f"a CPU screen under a GPU header was not flagged: {text}")

    # ...and the device must be what flags it. The case above is satisfied by
    # the hostname alone, so it would pass with `gpu` deleted from the identity
    # fields entirely. Here the *only* difference is `gpu: null` against
    # `gpu: 0` -- same node, same binary -- which is exactly the shape the
    # "ignore unknowns" rule swallowed: null there means CPU, not unrecorded.
    same_host_cpu = json.loads(json.dumps(same))
    same_host_cpu["provenance"]["gpu"] = None
    differs = rep.diverging_fields(rep.record_source(same_host_cpu),
                                   rep.record_source(matrix))
    require(differs == ["gpu"],
            f"a CPU record on the header's own host and binary diverged on "
            f"nothing, so it rendered as part of the GPU run: {differs}")
    require(rep.is_other_run(same_host_cpu, matrix),
            "a CPU section was folded into the GPU header's aggregate sentence")
    text = "\n".join(rep.render_all24(same_host_cpu, matrix))
    require("Not the run named in the provenance block" in text
            and "gpu" in text,
            f"the CPU/GPU divergence was not named in the section: {text}")

    # A record that genuinely never recorded a device is a different case and
    # must not be turned into a false divergence by the rule above.
    silent = json.loads(json.dumps(same))
    silent["provenance"].pop("gpu")
    require("gpu" not in rep.diverging_fields(rep.record_source(silent),
                                              rep.record_source(matrix)),
            "a record that recorded no device at all was reported as running "
            "on a different device")

    # Nothing to attribute is a third state: not the header's run, and not
    # demonstrably another one. Silence left the section sitting under the
    # header's provenance block, which is the inheritance this gate prevents.
    lines = rep.source_attribution({"schedules": {}}, matrix)
    require(lines, "a record with no provenance at all was given no source "
                   "line, so it inherited the header's")
    require("unattributable" in "\n".join(lines).lower(),
            f"a record with no provenance was attributed rather than named "
            f"unattributable: {lines}")
    require("Not the run named in the provenance block" not in "\n".join(lines),
            f"a record naming nothing was asserted to be a different run, "
            f"which the record cannot show either: {lines}")

    # The capacity measurement names a device but no host and no binary, so
    # "device 0" there is not the header's device 0 and must not read as it.
    capacity = {"schema": "issue83-capacity/1", "row_id": "realscale_local",
                "device": 0, "device_total_mib": 40960, "peak_used_mib": 1266,
                "sample_interval_sec": 0.5, "samples": 32, "returncode": 1}
    text = "\n".join(rep.render_capacity(capacity, matrix))
    require("no host, no start time and no binary digest" in text,
            f"an unattributable capacity datapoint was rendered under the "
            f"header's provenance as though it belonged to that run: {text}")

    # "No binary recorded" understates it when the sampled command names a
    # *different* build than the header's: the datapoint is not merely
    # unattributed, it is attributable elsewhere.
    sampled = dict(capacity,
                   command=["run_capacity.py", "--binary",
                            "/work4/.../build-cuda-rev2/motioncorr",
                            "--row", "realscale_local"])
    header = dict(matrix)
    header["provenance"] = dict(matrix["provenance"],
                                binary="/work4/.../build-cuda/motioncorr")
    text = "\n".join(rep.render_capacity(sampled, header))
    require("build-cuda-rev2" in text,
            f"the capacity datapoint's own binary was never named: {text}")
    require("a different build" in text,
            f"a capacity datapoint sampled from another build was described "
            f"as merely unrecorded: {text}")
    same_build = dict(sampled,
                      command=["run_capacity.py", "--binary",
                               "/work4/.../build-cuda/motioncorr"])
    require("a different build" not in "\n".join(
                rep.render_capacity(same_build, header)),
            "a capacity datapoint sampled from the header's own binary was "
            "announced as a different build")

    # A sampler that collected nothing writes a null peak and exits with the
    # wrapped command's status, so a clean exit with no measurement read as a
    # success. "Peak device memory observed: None MiB" is not a number.
    nothing = dict(capacity, peak_used_mib=None, samples=0)
    text = "\n".join(rep.render_capacity(nothing, matrix))
    require("_unrun_" in text and "None MiB" not in text,
            f"a capacity record that sampled nothing rendered a peak: {text}")
    require("1266" not in text, f"a peak appeared from nowhere: {text}")
    require("1266 MiB" in "\n".join(rep.render_capacity(capacity, matrix)),
            "positive control failed: a real peak was suppressed")

    # The aggregate sentence is the line most likely to be quoted on its own,
    # so the caveat has to survive being read without the sections above it.
    require(rep.is_other_run(other, matrix) and rep.is_other_run(later, matrix),
            "a section from another host, and one outside the run window, were "
            "both reported as belonging to the header's run")
    require(not rep.is_other_run(same, matrix),
            "a section from the header's own run was reported as foreign")
    require(not rep.is_other_run({"schedules": {}}, matrix),
            "a record with no provenance was asserted to be a different run, "
            "which is a claim its own emptiness cannot support")
    return {"status": "pass",
            "reproduced": "one header over sections from two different jobs",
            "now": "each section names its host, device and binary, and a "
                   "divergence from the header is stated"}


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


def control_matrix_schedule_witness(_tmp: Path,
                                    _fixtures: Optional[Path]) -> Dict[str, Any]:
    """The declared matrix must consume its own per-schedule witness too.

    ``run_matrix.py`` collected ``backend_evidence`` for repeat, batch and
    resume and then read none of it: not in the schedule's pass condition, not
    in the row status, and not in the rendered table, which printed the *base*
    run's witness only. That is W1 one level down -- a repeat, batch or resume
    executed on the CPU during a ``--gpu`` job would have been published as a
    native row. It also kept the last invocation's stdout only, so 23 of a
    24-invocation batch's startup markers were never examined.
    """
    cases = {}
    row = {"movies_compared": 3, "movies_passed": 3}
    marked = {"cuda_stage_marker": True}

    # The witness itself, over invocations rather than over one stdout.
    good = rm.schedule_witness(["Using CUDA acceleration on GPU device 0 for "
                                "global alignment."] * 3, Path("/nonexistent"),
                               [], 0)
    require(good["vacuous"],
            "an empty executed set produced a non-vacuous witness")
    require(not good["native_cuda_proven"],
            "VACUOUS WITNESS: a matrix schedule that executed no movie proved "
            "native CUDA execution")
    cases["empty_executed_set"] = {"vacuous": True, "native_cuda_proven": False}

    silent = rm.schedule_witness(
        ["Using CUDA acceleration on GPU device 0 for global alignment.", ""],
        Path("/nonexistent"), ["m1"], 0)
    require(silent["startup_marker_per_invocation"] == [True, False],
            "the per-invocation markers were not recorded one per invocation")
    require(not silent["native_cuda_proven"],
            "a schedule with an invocation that never announced the device "
            "was still credited with a native witness")
    cases["one_silent_invocation"] = {"native_cuda_proven": False}

    # The renderer must print it, and must not print "exact" alone.
    for name, witness, want in (
            ("cpu_executed", {"native_cuda_proven": False,
                              "startup_marker_per_invocation": [False]},
             "NOT established"),
            ("vacuous", {"vacuous": True,
                         "startup_marker_per_invocation": []}, "vacuous"),
            ("no_per_movie_record", {"native_cuda_proven": True}, "not covered"),
            ("half_marked", {"native_cuda_proven": True,
                             "per_movie": {"m1": marked,
                                           "m2": {"cuda_stage_marker": False}}},
             "**not covered** (1 of 2 movies marked)"),
            ("native", {"native_cuda_proven": True,
                        "startup_marker_per_invocation": [True, True],
                        "per_movie": {"m1": dict(marked, log_present=True),
                                      "m2": dict(marked, log_present=True)},
                        "executed_movies": ["m1", "m2"]}, "native (2 executed)"),
            # The shape the published GPU matrix actually has: every product
            # carries its own kernel stage marker, and only the last
            # invocation's startup banner was kept. The stage evidence is
            # measured and must be reported as such; the banner gap is
            # disclosed in the same cell rather than withholding the claim.
            ("stage_marked_banner_partial",
             {"native_cuda_proven": True, "startup_marker_found": True,
              "per_movie": {"m1": dict(marked, log_present=True),
                            "m2": dict(marked, log_present=True)}},
             "native (2/2 movies marked, banner 1/2)")):
        entry = {"schedules": {"repeat": dict(row, passed=True, runs=[{}, {}],
                                              backend_evidence=witness)}}
        cell = rep.schedule_cell(entry, "repeat", True)
        require(want in cell,
                f"UNCONSUMED WITNESS: a matrix schedule '{name}' rendered as "
                f"{cell!r}, which does not say {want!r}")
        require("exact 3/3" in cell,
                f"the equality result was dropped from the cell: {cell!r}")
        cases[name] = cell

    # The row verdict was written by a harness that never read the witness, so
    # a `pass` there covers pixels and the base run's backend and nothing
    # about the other three schedules. A record carrying no per-movie evidence
    # for those schedules must have the claim withheld rather than let the
    # verdict column carry it.
    published = {"provenance": {"gpu": 0},
                 "results": [{"row_id": "global_square", "status": "pass",
                              "schedules": {
                                  "base": {"backend_evidence":
                                           {"native_cuda_proven": True}},
                                  "repeat": dict(row, passed=True, runs=[{}],
                                                 backend_evidence={
                                                     "native_cuda_proven": True}),
                                  "batch": dict(row, passed=True,
                                                runs=[{}, {}, {}],
                                                backend_evidence={
                                                    "native_cuda_proven": True})}}]}
    require(rep.matrix_witness_gaps(published) == ["global_square"],
            "a row whose schedule witnesses cover one invocation each was not "
            "reported as a gap")
    text = "\n".join(rep.render_matrix(published))
    require("not established for 1 of these rows" in text,
            f"the table did not say the per-schedule native claim is "
            f"unsupported by this record: {text}")

    per_movie = {f"m{i}": {"cuda_stage_marker": True, "log_present": True}
                 for i in (1, 2, 3)}
    covered = json.loads(json.dumps(published))
    for name in ("repeat", "batch"):
        covered["results"][0]["schedules"][name]["backend_evidence"] = {
            "native_cuda_proven": True, "per_movie": per_movie,
            "startup_marker_per_invocation": [True, True, True]}
    covered["results"][0]["schedules"]["resume"] = dict(
        row, passed=True, runs=[{}],
        backend_evidence={"native_cuda_proven": True, "per_movie": per_movie,
                          "startup_marker_per_invocation": [True]})
    require(rep.matrix_witness_gaps(covered) == [],
            "positive control failed: a fully witnessed GPU matrix was "
            "reported as having a coverage gap")

    # Second positive control, on the shape the published records really have:
    # stage markers on every product, no per-invocation banner field. This is
    # the case the renderer used to withhold, and withholding a measured claim
    # is a misstatement in the other direction.
    stage_only = json.loads(json.dumps(covered))
    for entry in stage_only["results"][0]["schedules"].values():
        entry.get("backend_evidence", {}).pop("startup_marker_per_invocation", None)
    require(rep.matrix_witness_gaps(stage_only) == [],
            "WITHHELD A MEASURED CLAIM: a matrix whose every schedule marked "
            "every one of its own movies was reported as a coverage gap "
            "because one field name was absent")
    # ...but a schedule that drops a single movie's marker is a gap again.
    dropped = json.loads(json.dumps(stage_only))
    dropped["results"][0]["schedules"]["batch"]["backend_evidence"][
        "per_movie"]["m2"]["cuda_stage_marker"] = False
    require(rep.matrix_witness_gaps(dropped) == ["global_square"],
            "a schedule with an unmarked movie was accepted as covered")
    require(not rep.matrix_witness_gaps(dict(published,
                                             provenance={"gpu": None})),
            "a CPU matrix was asked to prove native execution")

    # On a CPU diagnostic there is no native claim to make, so the cell stays
    # as it was rather than acquiring an empty one.
    cpu_cell = rep.schedule_cell(
        {"schedules": {"repeat": dict(row, passed=True, runs=[{}],
                                      backend_evidence={})}}, "repeat", False)
    require(cpu_cell == "exact 3/3",
            f"a CPU schedule cell gained a native-witness claim: {cpu_cell!r}")
    cases["cpu"] = cpu_cell
    return {"status": "pass",
            "reproduced": "matrix repeat/batch/resume witnesses written at "
                          "7098a6f and consumed nowhere",
            "now": "per-invocation witness, consumed by the pass condition "
                   "and printed in every schedule cell"}


def control_rejection_names_option(_tmp: Path,
                                   _fixtures: Optional[Path]) -> Dict[str, Any]:
    """An option-rejection row must be satisfied by a diagnostic, not by luck.

    The declared token for ``threads_invalid`` was ``j``, tested with
    ``token in stdout+stderr`` over the lowercased output. Every run of that
    row happens to print a build path containing a ``j``-bearing directory or
    a hex frame address, so the assertion was satisfied by any nonzero exit --
    including a segfault before argument parsing.
    """
    real = ("in: /work4/scd/scarf1415/motioncorr/mc-i83b/src/"
            "motioncorr_runner.cpp, line 157\nERROR: \n--j must be positive.\n"
            "=== Backtrace  ===\n"
            "/work4/scd/scarf1415/motioncorr/mc-i83b/build-cuda/motioncorr() "
            "[0x457019]\n==================\n")
    named, line = rm.rejection_names_option(real, "--j")
    require(named and line == "--j must be positive.",
            f"positive control failed: the real rejection message was not "
            f"recognised as naming --j ({line!r})")

    crash = ("Segmentation fault\n=== Backtrace  ===\n"
             "/work4/scd/scarf1415/jobs/mc-i83b/build-cuda/motioncorr() "
             "[0x457019]\n==================\n")
    require(not rm.rejection_names_option(crash, "--j")[0],
            "SUBSTRING DEFECT REPRODUCED: a crash with no diagnostic satisfied "
            "the '--j must be rejected by name' contract")
    require(not rm.rejection_names_option(crash, "--group_frames")[0],
            "a crash satisfied the --group_frames rejection contract")

    # Neighbouring options must not satisfy each other.
    require(not rm.rejection_names_option("--j_extra must be positive.", "--j")[0],
            "a different option with the declared name as a prefix was accepted")
    require(not rm.rejection_names_option("ERROR: bad json in --i", "--j")[0],
            "the letter j inside another word satisfied the contract")
    require(not rm.rejection_names_option(
                "--group_frames_max must be positive.", "--group_frames")[0],
            "a longer option name containing the declared one was accepted")

    # Both declared rejection rows must name an option in its ``--name`` form.
    # ``--j`` is a real one-letter option, so the test is the leading dashes,
    # not the length: a bare ``j`` or ``group`` is what has to be rejected.
    for r in declared.ROWS:
        if r.expect_reject:
            require(r.expect_reject.startswith("--") and len(r.expect_reject) > 2,
                    f"row {r.row_id} declares a rejection token "
                    f"{r.expect_reject!r} that is not an option name")

    # Keeping the line is only worth anything if the report reads it. And a
    # record written by the substring harness carries `option_named: true` with
    # no line at all: rendering that identically to a record that earned it
    # republishes the old test's verdict as the new test's. Such a record
    # exists in this repository (`raw/cpu64/matrix-cpu-summary.json`).
    earned = {"returncode": 1, "option_named": True,
              "option_named_line": "--j must be positive."}
    cell = rep.reject_cell(earned)
    require("--j must be positive." in cell,
            f"the matched diagnostic line was recorded and never rendered, so "
            f"the assertion cannot be rechecked from the report: {cell}")

    legacy = {"returncode": 1, "option_named": True}
    cell = rep.reject_cell(legacy)
    require("not covered" in cell,
            f"a verdict from the bare-substring test rendered as though the "
            f"delimited matcher had produced it: {cell}")

    report = {"provenance": {"gpu": 0},
              "results": [{"row_id": "threads_invalid", "status": "pass",
                           "schedules": {"reject": dict(legacy)}}]}
    require(rep.rejection_coverage_gaps(report) == ["threads_invalid"],
            "a rejection row with no matched line was not named as uncovered")
    require("Rejection by name is not established"
            in "\n".join(rep.render_matrix(report)),
            "the report did not disclose that a rejection verdict predates "
            "the matcher it is presented as having passed")
    covered = {"provenance": {"gpu": 0},
               "results": [{"row_id": "threads_invalid", "status": "pass",
                            "schedules": {"reject": dict(earned)}}]}
    require(not rep.rejection_coverage_gaps(covered),
            "positive control failed: a row that kept its matched line was "
            "reported as uncovered")

    # A rejection row runs no payload, so it must not be counted as a row whose
    # per-schedule native witness is missing -- and a *payload* row whose
    # record holds no schedules must be.
    require(not rep.matrix_witness_gaps(covered),
            "a rejection row was counted as missing a native witness for "
            "schedules it never runs")
    bare = {"provenance": {"gpu": 0},
            "results": [{"row_id": "global_square", "status": "pass",
                         "schedules": {"base": {"backend_evidence": {
                             "native_cuda_proven": True,
                             "startup_marker_per_invocation": [True]}}}}]}
    require(rep.matrix_witness_gaps(bare) == ["global_square"],
            "a payload row whose record contains none of the three required "
            "schedules produced no gap, so its `pass` carried the native "
            "claim for schedules with no record at all")
    return {"status": "pass",
            "reproduced": "'j' in (stdout+stderr) accepted any nonzero exit",
            "now": "the option is matched delimited on a diagnostic line, the "
                   "matched line is kept in the record and rendered, and a "
                   "record without one is named as uncovered"}


def control_aggregate_needs_every_leg(_tmp: Path,
                                      _fixtures: Optional[Path]) -> Dict[str, Any]:
    """The closing aggregate must recompute, not quote the record's summary.

    ``missing_required_schedules`` postdates the first screens, so a record
    written without it fell through to "nothing missing" in the aggregate
    while the table above it -- which recomputes -- printed **PARTIAL**. One
    document, two answers.
    """
    complete = {"all24_equal": True, "missing_required_schedules": [],
                "schedules": {"base": {}, "repeat": {}, "batch": {}, "resume": {}}}
    require(rep.missing_schedules(complete) == [],
            "positive control failed: a complete screen was called partial")

    # ``missing_required_schedules`` postdates the first screens, so a record
    # written before it has no such key -- and reading the key would say
    # "nothing missing" for a screen that ran two of the four legs.
    proven = {"backend_evidence": {"native_cuda_proven": True,
                                   "startup_marker_per_invocation": [True]}}
    legacy = {"all24_equal": True, "provenance": {"gpu": 0},
              "schedules": {"base": dict(proven), "repeat": dict(proven)}}
    got = rep.missing_schedules(legacy)
    require(sorted(got) == ["batch", "resume"],
            f"a record with no missing-schedule field was read as complete: {got}")

    # Quoting the record's own list *instead of* recomputing has the same
    # shape one level up: a screen that says "nothing missing" while holding
    # one schedule certified itself. The named list is a claim to add to, not
    # the measurement.
    lying = {"all24_equal": True, "provenance": {"gpu": 0},
             "missing_required_schedules": [],
             "schedules": {"base": dict(proven)}}
    got = rep.missing_schedules(lying)
    require(sorted(got) == ["batch", "repeat", "resume"],
            f"a screen holding only `base` certified itself complete on the "
            f"strength of its own summary field: {got}")
    require(not rep.all24_witness_holds(lying),
            "a one-schedule screen held its native witness for every schedule")
    require("PARTIAL" in "\n".join(rep.render_all24(lying)),
            "a self-certified one-schedule screen was not rendered as partial")

    # And the union must not invent absences: a record naming a schedule the
    # recomputation cannot see is still missing it.
    both = dict(lying, missing_required_schedules=["repeat"],
                schedules={"base": dict(proven), "repeat": dict(proven),
                           "batch": dict(proven), "resume": dict(proven)})
    require(rep.missing_schedules(both) == ["repeat"],
            "a schedule the record itself reported missing was dropped "
            "because the recomputation found an entry for it")

    # The CPU branch of the witness skipped the missing-schedule gate, so a
    # CPU screen holding only `base` announced native execution "for every
    # schedule" -- every schedule being the one that ran.
    cpu_partial = {"all24_equal": True, "provenance": {"gpu": None},
                   "movies_in_star": all24.EXPECTED_MOVIES,
                   "schedules": {"base": {"backend_evidence": {}}}, "errors": []}
    require(not rep.all24_witness_holds(cpu_partial),
            "a CPU screen that ran one of four schedules established native "
            "execution for every schedule")
    require("NOT established" in "\n".join(rep.render_all24(cpu_partial)),
            "a one-schedule CPU screen rendered its witness as established")
    require(not rep.all24_witness_holds(legacy),
            "a screen missing two required schedules, each of the two it did "
            "run fully witnessed, still held its witness for the whole screen")
    text = "\n".join(rep.render_all24(legacy))
    require("PARTIAL" in text,
            f"a two-of-four screen was not rendered as partial: {text}")

    # And the same for the fixture leg: a record that compared nothing.
    empty = {"schema": "issue83-fixture-verify/5", "verified": True, "cases": {}}
    require(not rep.inputs_verified(empty),
            "VACUOUS VERIFICATION: a fixture record that compared no digest "
            "was accepted as verifying the inputs")
    text = "\n".join(rep.render_fixture_verification(empty))
    require("Nothing was compared" in text and "NOT VERIFIED" in text,
            f"an empty fixture record did not say it checked nothing: {text}")

    allowed = {"schema": "issue83-fixture-verify/5", "verified": True,
               "cases": {"km_a": {"movie": {"status": "match"},
                                  "ground_truth": {"status": "match"}}}}
    require(rep.inputs_verified(allowed),
            "positive control failed: a record that did compare both digests "
            "was rejected")

    # ...and the motion-truth leg. A record with no cases rendered a heading, a
    # source line and the closing "historical failures remain failures"
    # boilerplate: a section that reads as though gates ran and had nothing to
    # report. Nothing evaluated is its own verdict and it is not a pass.
    nogates = {"tool": "run_known_motion_gates.py", "gpu": 0,
               "binary": "/work4/.../build-cuda/motioncorr", "results": []}
    text = "\n".join(rep.render_numerical(nogates, None))
    require("nothing was evaluated" in text,
            f"a motion-truth record containing no gate results rendered as a "
            f"section with no findings rather than as an empty one: {text}")
    # A case whose record states no verdict at all must not print as one.
    silent = {"tool": "run_known_motion_gates.py", "gpu": 0,
              "results": [{"case": "km_global_hisnr", "role": "gate"}]}
    text = "\n".join(rep.render_numerical(silent, None))
    require("**None**" not in text and "verdict not stated" in text,
            f"a gate with no recorded verdict was rendered as one: {text}")
    return {"status": "pass",
            "reproduced": "aggregate trusted matrix_complete/all24_equal and a "
                          "verified flag that quantified over nothing",
            "now": "every record-supplied conjunct is paired with a recomputed "
                   "one"}


def control_comparator_coverage(_tmp: Path,
                                _fixtures: Optional[Path]) -> Dict[str, Any]:
    """A comparator PASS over a subset of checks is not a pass.

    The coverage guard sat *after* ``if entry["passed"]: return True``, so it
    could only ever downgrade a verdict that had already failed -- it was
    unreachable on exactly the records it was written for.
    """
    covered = {"passed": True, "overall_status": "PASS", "coverage_complete": True,
               "checks": {"corrected_image": True, "motion_trajectory": True}}
    ok, why = rm.numerically_equal(covered, [])
    require(ok and not why,
            f"positive control failed: a fully covered PASS was rejected {why}")

    partial = dict(covered, coverage_complete=False)
    ok, why = rm.numerically_equal(partial, [])
    require(not ok and "coverage incomplete" in " ".join(why),
            "SHADOWED GUARD REPRODUCED: a comparator PASS whose coverage was "
            "incomplete was accepted as numerically equal")

    missing_flag = {"passed": True, "overall_status": "PASS",
                    "checks": {"corrected_image": True}}
    require(not rm.numerically_equal(missing_flag, [])[0],
            "a record that never reported coverage at all was accepted")

    require(not rm.numerically_equal({"passed": True}, [])[0],
            "a PASS with no comparator verdict was accepted")
    return {"status": "pass",
            "reproduced": "coverage_complete checked after the passed shortcut",
            "now": "checked before it, so it can downgrade a PASS"}


def control_all24_asserts_metadata(_tmp: Path,
                                   _fixtures: Optional[Path]) -> Dict[str, Any]:
    """The integrated screen must assert the metadata its invocation entails.

    It passed ``{}`` as the expectation, so it checked product presence and
    cross-schedule equality and nothing else: a build ignoring
    ``--dose_per_frame`` produces 24 movies that are equal under every
    schedule, and the screen would have published them as a pass.
    """
    expect = all24.expected_star_metadata(
        ["--use_own", "--dose_weighting", "--dose_per_frame", "1.277",
         "--patch_x", "5", "--patch_y", "5"])
    require(expect, "EMPTY EXPECTATION REPRODUCED: the integrated screen "
                    "asserted no STAR metadata at all")
    require(expect.get("dose_per_frame") == 1.277,
            f"the requested dose was not asserted: {expect}")
    require(expect.get("binning") == 1.0 and expect.get("first_frame") == 1
            and expect.get("pre_exposure") == 0.0,
            f"the implied defaults were not asserted: {expect}")

    off = all24.expected_star_metadata(["--use_own"])
    require(off["dose_per_frame"] is None,
            "a dose was asserted for a run that did not request dose weighting")

    # The renderer must say when a record asserted nothing, and must not
    # silently present such a screen as equivalent to one that did.
    silent = {"provenance": {"gpu": 0}, "all24_equal": True,
              "missing_required_schedules": [],
              "schedules": {"base": {}, "repeat": {}, "batch": {}, "resume": {}}}
    text = "\n".join(rep.render_all24(silent))
    require("asserted no STAR metadata" in text,
            f"a screen that asserted no metadata was rendered as though it "
            f"had: {text}")

    stated = dict(silent, star_metadata_asserted=expect,
                  metadata_not_asserted=["original_pixel_size"])
    text = "\n".join(rep.render_all24(stated))
    require("`dose_per_frame`=1.277" in text,
            f"the asserted metadata was not published: {text}")
    require("Not asserted here" in text and "original_pixel_size" in text,
            f"what the screen could not assert was not named: {text}")
    return {"status": "pass",
            "reproduced": "check_products(base_dir, stems, suffixes, {}, None)",
            "now": "the invocation's implied metadata is asserted, and what "
                   "cannot be derived is named as not asserted"}


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


def control_payload_recorder(tmp: Path, _fixtures: Optional[Path]) -> Dict[str, Any]:
    """The placement recorder must not report success having seen nothing.

    It was written to stop placement being asserted of the unpinned launcher
    instead of measured on the payload, and it carried two instances of the
    defect it exists to close: a substring match that accepts any executable
    under the deployment tree, and exit 0 when the payload was never seen --
    so a job script recording ``$?`` per tool wrote "success" for a recorder
    whose record says ``observed: false``.
    """
    exe = "/home/ubuntu/mc-i83-cpu/build-cpu/motioncorr"
    require(rec.matches(exe, exe, "exact"),
            "positive control failed: the payload did not match its own path")
    for other in (exe + "-old", "/home/ubuntu/mc-i83-cpu/build-cpu/motioncorr2",
                  "/home/ubuntu/mc-i83-cpu/tools/motioncorr_helper"):
        require(not rec.matches(other, "motioncorr", "exact"),
                f"a different executable under the same tree was recorded as "
                f"the payload: {other}")
        require(rec.matches(other, "motioncorr", "substring"),
                f"positive control failed: the loose mode stopped being loose "
                f"({other})")

    out = tmp / "placement.json"
    proc = subprocess.run(
        [sys.executable, str(HERE / "record_payload_env.py"),
         "--match", "/nonexistent/payload/that/never/runs",
         "--json", str(out), "--interval", "0.01", "--timeout", "0.05"],
        capture_output=True, text=True)
    record = json.loads(out.read_text())
    require(record["observed"] is False,
            "positive control failed: a payload that never ran was observed")
    require(proc.returncode != 0,
            f"a recorder that never saw the payload exited "
            f"{proc.returncode}, so a job's exit-code table recorded success "
            f"for a run whose placement is unknown")
    require(record.get("warning"),
            "the record did not say the payload was never seen")
    return {"status": "pass",
            "reproduced": "exit 0 with observed:false, and a substring match "
                          "that accepted any executable under the tree",
            "now": "exit 2 when nothing was observed; --match is an exact path "
                   "by default and the mode is recorded in the file"}


def control_suite_selects_something(tmp: Path,
                                    _fixtures: Optional[Path]) -> Dict[str, Any]:
    """``--only`` must not be able to select nothing and exit 0.

    The suite's own exit status is quantified over the controls selected, so
    selecting none made ``pass == len(wanted)`` true of zero and the process
    exited 0 having checked nothing -- the empty-set pass this whole file
    exists to prevent, arriving through the argument parser.
    """
    for argument in (",", " , ", ",,"):
        proc = subprocess.run(
            [sys.executable, str(HERE / __file__.rsplit("/", 1)[-1]),
             "--only", argument, "--json", str(tmp / "empty.json")],
            capture_output=True, text=True, cwd=str(HERE))
        require(proc.returncode != 0,
                f"--only {argument!r} selected no controls and the suite "
                f"exited {proc.returncode}")
        require(not (tmp / "empty.json").exists(),
                f"--only {argument!r} wrote a control record for a run that "
                f"checked nothing")
    return {"status": "pass",
            "reproduced": "--only ',' ran zero controls and exited 0",
            "now": "an empty selection is a usage error"}


CONTROLS: Dict[str, Callable[[Path, Optional[Path]], Dict[str, Any]]] = {
    "ground_truth_mutation": control_ground_truth_mutation,
    "ps_wrong_dimension": control_ps_wrong_dimension,
    "resume_native_witness": control_resume_witness,
    "witness_is_consumed": control_witness_is_consumed,
    "report_renders_witness": control_report_renders_witness,
    "report_states_input_coverage": control_report_states_input_coverage,
    "report_attributes_each_section": control_report_attributes_each_section,
    "partial_schedules": control_partial_schedules,
    "matrix_schedule_witness": control_matrix_schedule_witness,
    "rejection_names_option": control_rejection_names_option,
    "aggregate_needs_every_leg": control_aggregate_needs_every_leg,
    "comparator_coverage": control_comparator_coverage,
    "all24_asserts_metadata": control_all24_asserts_metadata,
    "input_hashes": control_input_hashes,
    "cross_row_consumed": control_cross_row_consumed,
    "provenance_allowance": control_provenance_allowance,
    "truth_provenance": control_truth_provenance,
    "payload_recorder": control_payload_recorder,
    "suite_selects_something": control_suite_selects_something,
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
    # ``--only ","`` selects nothing and names nothing unknown, so the suite
    # would have run zero controls and exited 0 -- the empty-set pass this
    # whole file exists to prevent, reintroduced through the argument parser.
    if not wanted:
        parser.error("--only selected no controls; a suite that runs nothing "
                     "must not exit 0")

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
        print("NOTE: skipped controls are not passes; rerun with --fixtures-dir",
              file=sys.stderr)
    # A skipped control is not a passing control here either. Without fixtures
    # every control that needs them skips, and a suite where nothing ran used
    # to exit 0 -- so a job script reading the exit status recorded "controls
    # passed" for a run that checked nothing. Quantified over the controls
    # actually selected, so ``--only`` still exits 0 when its subset passes.
    ran = bool(wanted) and report["counts"]["pass"] == len(wanted)
    return 0 if (report["counts"]["failed"] == 0 and ran) else 1


if __name__ == "__main__":
    sys.exit(main())
