"""Meta-checks: revert each gate at runtime and require its control to fail.

Every gate gets a negative control; every negative control gets a meta-check
that reverts the gate at runtime and confirms the control then FAILS. A
control that passes both with and without its gate is testing nothing.

This file was an untracked scratch script for two review rounds. Every other
claim in ``docs/issue83/`` is anchored to a preserved record; "thirteen
meta-checks pass" was anchored to a file that was not in the repository and
whose output was in no job log, which is exactly the shape of evidence this
issue exists to refuse. It is committed here so the claim can be re-run by
anyone and so its output can be preserved alongside the control suite's.

Imports ``negative_controls`` from the tools directory and reaches the other
modules through it (``nc.rep``, ``nc.rm``, ...). Importing
``tools.validation_issue83.report`` here instead would bind a *different*
module object than the one the controls call, and every patch below would
silently have no effect -- the trap this file exists to avoid.
"""
import json
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import negative_controls as nc  # noqa: E402

rep, rm, all24, vf, rec = nc.rep, nc.rm, nc.all24, nc.vf, nc.rec
tmp = Path("/tmp/i83-meta")
tmp.mkdir(exist_ok=True)

failures = []
checks = {}


def reverted(name, control, patches, why):
    """Revert a gate, run its control, require the control to fail."""
    saved = [(obj, attr, getattr(obj, attr)) for obj, attr, _ in patches]
    for obj, attr, value in patches:
        setattr(obj, attr, value)
    try:
        control(tmp, None)
    except Exception as exc:                      # noqa: BLE001
        checks[name] = {"kind": "reverted_gate", "control_failed": True,
                        "diagnostic": str(exc)[:200]}
        print(f"  ok   {name}: control failed as it must -- {str(exc)[:90]}")
        return
    finally:
        for obj, attr, value in saved:
            setattr(obj, attr, value)
    checks[name] = {"kind": "reverted_gate", "control_failed": False,
                    "why": why}
    failures.append(f"{name}: {why}")
    print(f"  FAIL {name}: control still passed with the gate reverted")


# --- 1. vacuous fixture verification -----------------------------------------
# The gate itself, in the producer: before the fix,
# `verified = not (mismatched or undeclared or missing)`, which is true of a
# record that compared nothing at all. Reverting only the report's consumer
# (below) leaves this one untested -- a checker willing to write VERIFIED over
# nothing is a defect whether or not a downstream reader catches it.
reverted("vacuous_fixture_verification",
         nc.control_fixture_verdict_vacuous,
         [(vf, "verdict",
           lambda result, allow_missing: dict(
               result,
               vacuous=not (result["compared"]["movie"]
                            and result["compared"]["ground_truth"]),
               verified=not (bool(result["mismatched"])
                             or bool(result["undeclared"])
                             or (bool(result["missing"])
                                 and not allow_missing))))],
         "a fixture record that compared no digest was verified")

# And the consumer: the report must not build an aggregate on such a record
# even when the producer hands it one.
reverted("aggregate_trusts_fixture_summary",
         nc.control_aggregate_needs_every_leg,
         [(rep, "inputs_verified", lambda v: bool((v or {}).get("verified")))],
         "a fixture record that compared no digest was accepted")

# --- 2. W3 caveat keyed on the schema string ---------------------------------
_real_coverage = rep.fixture_coverage
reverted("w3_caveat_keyed_on_schema",
         nc.control_report_states_input_coverage,
         [(rep, "fixture_coverage",
           lambda v: dict(_real_coverage(v), ground_truth=1))],
         "a record that checked no truth file was rendered without the caveat")

# --- 3. bare-substring rejection assertion -----------------------------------
# The published form, in the published shape: the declared token was `j`, not
# `--j`, and it was tested against the whole lowercased output.
reverted("substring_rejection",
         nc.control_rejection_names_option,
         [(rm, "rejection_names_option",
           lambda output, option: (
               option.lstrip("-") in output.lower(),
               next((l.strip() for l in output.splitlines()
                     if option.lstrip("-") in l.lower()), None)))],
         "a crash with no diagnostic satisfied the rejection contract")

# --- 4. matrix per-schedule witness, unconsumed and unprinted ----------------
reverted("matrix_witness_unrendered",
         nc.control_matrix_schedule_witness,
         [(rep, "schedule_cell",
           lambda entry, schedule, on_gpu: "exact 3/3")],
         "a schedule cell printed equality with no word about the backend")

# Before: the witness was computed from one stdout, so a 24-invocation batch
# had 23 markers nobody looked at. Same shape, one invocation of evidence.
_real_witness = rm.schedule_witness


def _last_invocation_only(stdouts, d, stems, gpu):
    return _real_witness(stdouts[-1:], d, stems, gpu)


# Patched in *both* modules. ``run_all24_schedules`` does
# ``from run_matrix import schedule_witness``, which binds the function object
# into its own namespace at import time; rebinding ``rm.schedule_witness``
# alone leaves the integrated screen calling the real one, and a revert that
# reaches only half its callers is not a revert.
reverted("matrix_witness_last_invocation_only",
         nc.control_matrix_schedule_witness,
         [(rm, "schedule_witness", _last_invocation_only),
          (all24, "schedule_witness", _last_invocation_only)],
         "a witness over the last invocation only was accepted")

# Before: the row verdict carried the native claim for all four schedules.
reverted("matrix_witness_gap_unreported",
         nc.control_matrix_schedule_witness,
         [(rep, "matrix_witness_gaps", lambda report: [])],
         "a record that cannot support its per-schedule native claim was "
         "published without withholding it")

# --- 5. aggregate quoting the record's own summary ---------------------------
reverted("aggregate_trusts_record_summary",
         nc.control_aggregate_needs_every_leg,
         [(rep, "missing_schedules",
           lambda r: list((r or {}).get("missing_required_schedules") or []))],
         "a record with no missing-schedule field was read as complete")

# --- 6. comparator coverage guard behind the passed shortcut -----------------
reverted("coverage_guard_shadowed",
         nc.control_comparator_coverage,
         [(rm, "numerically_equal",
           lambda entry, allowed: (bool(entry.get("passed")), []))],
         "a PASS over an incomplete set of checks was accepted")

# --- 7. integrated screen asserting no STAR metadata -------------------------
reverted("all24_asserts_nothing",
         nc.control_all24_asserts_metadata,
         [(all24, "expected_star_metadata", lambda args: {})],
         "the screen asserted no metadata and the control did not notice")

# --- 8. per-section attribution ----------------------------------------------
reverted("sections_share_one_attribution",
         nc.control_report_attributes_each_section,
         [(rep, "source_attribution",
           lambda record, reference=None, label="Source record": [])],
         "sections from three runs rendered under one provenance block")

# --- 9. gates added in the 7098a6f second round ------------------------------
# A CPU section records `gpu: null` as a measurement. Reading that as "device
# unknown" let a CPU section be folded into a GPU header with nothing said.
reverted("cpu_section_reads_as_unknown_device",
         nc.control_report_attributes_each_section,
         [(rep, "diverging_fields",
           lambda src, ref: [k for k in ("hostname", "binary_sha256",
                                         "binary_path")
                             if ref.get(k) is not None and src.get(k) is not None
                             and ref[k] != src[k]])],
         "a CPU section and a GPU header differed only in the device and the "
         "difference was not reported")

# A record with no identity fields at all inherited the header's silently.
reverted("identityless_section_inherits_header",
         nc.control_report_attributes_each_section,
         [(rep, "source_attribution",
           lambda record, reference=None, label="Source record",
           unattributable=None: [f"- {label}: (inherited)"])],
         "a section naming no host, device or binary was published under the "
         "header's provenance")

# The matrix's own completeness summary, trusted instead of recomputed against
# the declared row list. (This slot previously reverted ``missing_schedules``
# for a second time, with `sorted` where check 5 used `list` -- two names over
# one gate, which counts the same revert twice and leaves this one untested.)
reverted("matrix_completeness_taken_on_trust",
         nc.control_aggregate_needs_every_leg,
         [(rep, "matrix_complete",
           lambda r: bool((r or {}).get("matrix_complete")
                          and not (r or {}).get("unrun_rows")))],
         "a record holding one of twenty-five declared rows certified the "
         "matrix complete")

# The screen's own ``all24_equal``, trusted instead of recomputed from the
# per-movie numbers underneath it.
reverted("all24_equality_taken_on_trust",
         nc.control_aggregate_needs_every_leg,
         [(rep, "all24_equality_holds", lambda r: bool((r or {}).get("all24_equal")))],
         "a screen whose repeat compared no movie certified cross-schedule "
         "equality")

# The correction in the other direction: keying coverage on a field name that
# only the fixed runner writes withheld a claim the record does support.
reverted("coverage_keyed_on_field_name",
         nc.control_report_renders_witness,
         [(rep, "witness_coverage_gap",
           lambda entry: "startup_marker_per_invocation" not in
           entry.get("backend_evidence", {})
           and len(entry.get("runs", []) or []) > 1)],
         "a schedule whose every movie carries a kernel stage marker was "
         "withheld as unwitnessed, and the control did not notice")

# ...and the gate that keeps the weaker witness's gap visible once the
# stronger one no longer blocks the claim.
reverted("banner_gap_silently_dropped",
         nc.control_report_renders_witness,
         [(rep, "banner_coverage", lambda entry: (1, 1))],
         "the missing startup banners of 23 invocations stopped being reported")

# The recorder's substring match merged a helper's placement into the payload's.
reverted("payload_match_is_substring",
         nc.control_payload_recorder,
         [(rec, "matches", lambda exe, match, mode: match in exe)],
         "a helper under the deployment tree was sampled as the payload")


class _AlwaysZero:
    """``subprocess`` as the control would have seen the old recorder.

    The control runs the recorder as a real subprocess, so patching
    ``rec.main`` in this interpreter cannot reach it. What is reverted here is
    the behaviour the control actually observes: a recorder that exits 0 having
    written ``observed: false``. Rebinding the name inside
    ``negative_controls`` leaves the stdlib module itself untouched.
    """

    def __init__(self, real):
        self._real = real

    def run(self, *args, **kwargs):
        proc = self._real.run(*args, **kwargs)
        proc.returncode = 0
        return proc

    def __getattr__(self, name):
        return getattr(self._real, name)


# A recorder that never saw the payload exited 0, putting "success" in the
# job's exit-code table for a run whose placement is unknown.
reverted("recorder_exits_zero_unobserved",
         nc.control_payload_recorder,
         [(nc, "subprocess", _AlwaysZero(subprocess))],
         "a recorder that observed nothing reported success")


# --- 10. suite exit status ---------------------------------------------------
# A suite where every control skipped exited 0, so a job script reading the
# exit status recorded "controls passed" for a run that checked nothing.
def suite(args):
    return subprocess.run([sys.executable, str(TOOLS / "negative_controls.py")]
                          + args, capture_output=True, text=True).returncode


cases = [(["--only", "ground_truth_mutation"], 1, "every selected control skipped"),
         (["--only", "comparator_coverage"], 0, "the selected control passed"),
         ([], 1, "one control of the suite skipped")]
for args, want, why in cases:
    got = suite(args)
    tag = "ok  " if got == want else "FAIL"
    if got != want:
        failures.append(f"suite_exit {args}: wanted {want}, got {got} ({why})")
    checks[f"suite_exit{args or ['(full)']}"] = {
        "kind": "suite_exit_status", "args": args, "wanted": want, "got": got,
        "why": why, "held": got == want}
    print(f"  {tag} suite_exit {args or '(full)'}: exit={got} -- {why}")

summary = {"schema": "issue83-meta-controls/1",
           "total": len(checks),
           "reverted_gates": sum(1 for c in checks.values()
                                 if c["kind"] == "reverted_gate"),
           "suite_exit_cases": sum(1 for c in checks.values()
                                   if c["kind"] == "suite_exit_status"),
           "failed": len(failures),
           "checks": checks,
           "failures": failures}
# Written unconditionally: a meta-check run that failed must leave a record
# saying so, in the same place a passing one does.
for flag in ("--json",):
    if flag in sys.argv:
        out = Path(sys.argv[sys.argv.index(flag) + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(f"\nwrote {out}")

print()
if failures:
    print(f"{len(failures)} of {len(checks)} meta-check(s) FAILED:")
    for line in failures:
        print(f"  - {line}")
    sys.exit(1)
print(f"all {len(checks)} meta-checks passed "
      f"({summary['reverted_gates']} reverted gates + "
      f"{summary['suite_exit_cases']} suite exit-status cases): "
      f"every gate, reverted, makes its control fail")
