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
import run_matrix as rm  # noqa: E402
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
    raw = bytearray(target.read_bytes())
    # Flip one character inside the JSON body, keeping it the same length.
    index = max(raw.rfind(b"0"), raw.rfind(b"1"))
    require(index > 0, f"no digit to flip in {target.name}")
    original = raw[index]
    raw[index] = ord("9") if original != ord("9") else ord("8")
    target.write_bytes(bytes(raw))
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
            "byte_offset": index, "detected_as": flagged,
            "clean_run_verified": True}


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
    for a, b in declared.NEUTRAL_EQUIVALENCES:
        require({a, b} <= known, f"equivalence names an undeclared row: {a}, {b}")
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
            "declared_equalities": [list(p) for p in declared.NEUTRAL_EQUIVALENCES],
            "declared_negative_controls": [[a, b] for a, b, _ in
                                           declared.NEUTRAL_NEGATIVE_CONTROLS]}


CONTROLS: Dict[str, Callable[[Path, Optional[Path]], Dict[str, Any]]] = {
    "ground_truth_mutation": control_ground_truth_mutation,
    "ps_wrong_dimension": control_ps_wrong_dimension,
    "resume_native_witness": control_resume_witness,
    "witness_is_consumed": control_witness_is_consumed,
    "partial_schedules": control_partial_schedules,
    "input_hashes": control_input_hashes,
    "cross_row_consumed": control_cross_row_consumed,
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
