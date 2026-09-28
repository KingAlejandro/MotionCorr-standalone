#!/usr/bin/env python3
"""Render the compact issue #83 support table from raw per-case reports.

Implementation coverage and numerical gates are printed as separate tables and
separate verdicts. A declared row with no raw result is printed as ``unrun``;
it is never folded into a pass, and the presence of any unrun row suppresses
the aggregate "supported" claim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matrix as declared  # noqa: E402

STATUS_CELL = {"pass": "pass", "fail": "**FAIL**", "error": "**ERROR**",
               "unrun": "_unrun_"}


def load(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text())


def schedule_cell(entry: Dict[str, Any], schedule: str, on_gpu: bool) -> str:
    """One matrix schedule cell: equal pixels *and* who produced them.

    A cell that reports only equality is the defect withdrawn as W1, one level
    down: the matrix collected a witness for each of its three schedules and
    then neither consumed nor printed it, so a repeat, batch or resume that
    ran on the CPU during a ``--gpu`` job read as ``exact``.
    """
    sched = entry.get("schedules", {}).get(schedule)
    if sched is None:
        return "_unrun_"
    if "passed" not in sched:
        return "n/a"
    if sched.get("passed") is not True:
        return "**FAIL**"
    moved, total = sched.get("movies_passed"), sched.get("movies_compared")
    cell = f"exact {moved}/{total}" if total else "exact"
    if not on_gpu:
        return cell
    witness = sched.get("backend_evidence", {})
    if witness.get("vacuous"):
        return f"{cell}, witness **vacuous**"
    if "startup_marker_per_invocation" not in witness:
        # Written by the harness that examined the last invocation only. The
        # markers of the earlier invocations are not in the record and cannot
        # be recovered from it.
        n = len(sched.get("runs", []) or [])
        return (f"{cell}, witness **not covered**"
                + (f" (1 of {n} invocations examined)" if n > 1 else ""))
    if not witness.get("native_cuda_proven"):
        return f"{cell}, native execution **NOT established**"
    executed = witness.get("executed_movies") or []
    return f"{cell}, native ({len(executed)} executed)"


def render_matrix(report: Optional[Dict[str, Any]]) -> List[str]:
    # On a CPU run the absence of a CUDA marker is the required result, not a
    # failure, so the witness column is labelled by the backend that was used.
    device = (report or {}).get("provenance", {}).get("gpu")
    on_gpu = device is not None
    heading = (f"### Implementation coverage (native CUDA, device {device})" if on_gpu
               else "### Implementation coverage (CPU backend — separate diagnostic)")
    # Named for the run it describes. The schedule columns carry their own
    # witness, because the base run's says nothing about them.
    witness_column = "Native witness (base)" if on_gpu else "CUDA marker absent"
    lines = [heading, "",
             "Exact = every movie identical to the uninterrupted run under "
             "`compare_motioncorr.py --gate exact`.", ""]
    if not on_gpu:
        lines += ["This run used the CPU backend. A CUDA marker here would mean "
                  "a masquerading run, so the column below requires its "
                  "**absence**.", ""]
    lines += [f"| Row | Axes | {witness_column} | Products | Repeat | Batch "
              "| Resume (non-prefix) | Verdict |",
              "|---|---|---|---|---|---|---|---|"]
    by_id: Dict[str, Dict[str, Any]] = {}
    if report:
        by_id = {r["row_id"]: r for r in report.get("results", [])}

    for row in declared.ROWS:
        entry = by_id.get(row.row_id)
        axes = ", ".join(f"{k}={v}" for k, v in row.axes.items())
        if entry is None:
            lines.append(f"| `{row.row_id}` | {axes} | _unrun_ | _unrun_ | _unrun_ "
                         f"| _unrun_ | _unrun_ | {STATUS_CELL['unrun']} |")
            continue
        base = entry.get("schedules", {}).get("base", {})
        witness = base.get("backend_evidence", {})
        if row.expect_reject:
            reject = entry.get("schedules", {}).get("reject", {})
            native = "n/a (rejected)"
            productcell = (f"rc={reject.get('returncode')}, "
                           f"named={reject.get('option_named')}")
            repeat = batch = resume = "n/a"
        else:
            if on_gpu:
                native = "yes" if witness.get("native_cuda_proven") else "**no**"
            else:
                native = ("**masquerade**" if witness.get("unexpected_cuda_marker")
                          else "confirmed absent")
            inventory = base.get("inventory", {})
            productcell = ("complete" if inventory.get("inventory_complete")
                           else "**incomplete**")
            repeat = schedule_cell(entry, "repeat", on_gpu)
            batch = schedule_cell(entry, "batch", on_gpu)
            resume = schedule_cell(entry, "resume", on_gpu)
        lines.append(f"| `{row.row_id}` | {axes} | {native} | {productcell} | "
                     f"{repeat} | {batch} | {resume} | "
                     f"{STATUS_CELL.get(entry.get('status'), entry.get('status'))} |")

    gaps = matrix_witness_gaps(report)
    if gaps:
        lines += ["",
                  f"**Per-schedule native execution is not established for "
                  f"{len(gaps)} of these rows.** The `Verdict` column is the "
                  f"verdict the harness that produced this record wrote, and "
                  f"that harness collected a witness for each schedule without "
                  f"reading it. The evidence for the repeat, batch and resume "
                  f"cells above is not in the record and cannot be recovered "
                  f"from it; only a fresh run of the fixed harness can supply "
                  f"it. Rows affected: " + ", ".join(f"`{g}`" for g in gaps)
                  + "."]
    return lines


def matrix_witness_gaps(report: Optional[Dict[str, Any]]) -> List[str]:
    """Rows of a GPU matrix whose per-schedule native execution is unproven.

    A row's ``status`` was written by a harness that collected a witness for
    repeat, batch and resume and then consumed none of it, so ``pass`` there
    covers pixel equality and the *base* run's backend, and nothing about the
    backend the other three schedules used. Recomputed here rather than read
    off the record, because the record has no field for it.
    """
    if not report or report.get("provenance", {}).get("gpu") is None:
        return []
    gaps = []
    for entry in report.get("results", []):
        schedules = entry.get("schedules", {})
        if any(name in schedules
               and ("startup_marker_per_invocation"
                    not in schedules[name].get("backend_evidence", {})
                    or not schedules[name].get("backend_evidence", {})
                    .get("native_cuda_proven"))
               for name in REQUIRED_SCHEDULES):
            gaps.append(entry["row_id"])
    return gaps


#: The schedules an integrated screen must contain before it certifies
#: anything. Mirrors ``run_all24_schedules.REQUIRED_SCHEDULES``; repeated here
#: because the renderer must be able to judge a record written by any harness,
#: including one from before that list existed.
REQUIRED_SCHEDULES = ("repeat", "batch", "resume")


def missing_schedules(report: Optional[Dict[str, Any]]) -> List[str]:
    """Required schedules this screen does not contain.

    Recomputed from the schedules present whenever the record does not name
    them itself. A record written before ``missing_required_schedules`` existed
    carries no such field, and reading it as "nothing missing" is how a screen
    with only ``base`` and ``repeat`` could render **PARTIAL** in its own table
    and still be counted complete by the aggregate at the foot of the same
    document.
    """
    if not report:
        return []
    named = report.get("missing_required_schedules")
    if named is not None:
        return list(named)
    schedules = report.get("schedules", {})
    return [s for s in REQUIRED_SCHEDULES if s not in schedules]


def all24_witness_holds(report: Optional[Dict[str, Any]]) -> bool:
    """Every schedule of a GPU integrated screen proved native execution.

    Recomputed here from the per-schedule evidence rather than trusting the
    record's own ``all24_equal``, because a report written by an older harness
    can carry ``all24_equal: true`` alongside a schedule whose
    ``native_cuda_proven`` is false -- the contradiction this generator
    published once already. On a CPU record there is nothing to prove and the
    absence of a CUDA marker is the expected result, so this is vacuously true;
    a masquerading CUDA marker is not, and fails here.
    """
    if not report:
        return False
    schedules = report.get("schedules", {})
    if not schedules:
        return False
    if report.get("provenance", {}).get("gpu") is None:
        return not any(e.get("backend_evidence", {}).get("unexpected_cuda_marker")
                       for e in schedules.values())
    if missing_schedules(report):
        return False
    return all(e.get("backend_evidence", {}).get("native_cuda_proven")
               and not witness_coverage_gap(e)
               for e in schedules.values())


def witness_coverage_gap(entry: Dict[str, Any]) -> bool:
    """A multi-invocation schedule whose record covers only one invocation.

    Before the fix the witness was computed from the *last* invocation's stdout
    alone, so a 24-invocation batch had 23 startup markers that were never
    looked at. Those markers are not in the record and cannot be recovered from
    it, so such a schedule is reported as not covered rather than credited with
    a witness it never earned. Records written by the fixed harness carry
    ``startup_marker_per_invocation`` and close this gap.
    """
    evidence = entry.get("backend_evidence", {})
    if "startup_marker_per_invocation" in evidence:
        return False
    return len(entry.get("runs", []) or []) > 1


def record_source(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Where one section's numbers came from, whatever shape the record has.

    ``run_known_motion_gates.py`` is a merged tool and is not modified here; it
    names its binary and device at the top level rather than in a provenance
    block, so both shapes are read. Its ``binary`` is a path rather than a
    digest, and it is the only field separating that tool's output on one host
    from its output on another -- dropping it left five gate verdicts
    attributable to neither job.
    """
    if not record:
        return {}
    prov = record.get("provenance") or {}
    return {"hostname": prov.get("hostname"),
            "gpu": prov.get("gpu", record.get("gpu")),
            "binary_sha256": prov.get("binary_sha256"),
            "binary_path": prov.get("binary", record.get("binary")),
            "started_utc": prov.get("started_utc"),
            "finished_utc": record.get("finished_utc")}


def source_attribution(record: Optional[Dict[str, Any]],
                       reference: Optional[Dict[str, Any]] = None,
                       label: str = "Source record") -> List[str]:
    """Name the run a section came from, and say when it is not the same run.

    The provenance block at the top of the report is the matrix record's. A
    report may legitimately be assembled from more than one job -- the first
    native allocation generated its fixtures with the wrong interpreter, so its
    integrated screen and its fixture-dependent legs come from different jobs --
    and a single header would then present two measurements as one. Each
    section states its own host, device and binary, and any divergence from the
    header is named rather than left for the reader to notice.
    """
    src = record_source(record)
    # ``finished_utc`` alone identifies nothing -- it is carried only so this
    # record can serve as the reference window for another section.
    if not any(src.get(k) is not None
               for k in ("hostname", "gpu", "binary_sha256", "binary_path",
                         "started_utc")):
        return []
    bits = [f"`{src['hostname']}`" if src.get("hostname") else "host not recorded",
            "CPU" if src.get("gpu") is None else f"device {src['gpu']}"]
    if src.get("binary_sha256"):
        bits.append(f"binary `{src['binary_sha256'][:12]}…`")
    elif src.get("binary_path"):
        # A path is weaker than a digest, but it is what this record has, and
        # it is enough to show a section was produced by a different build.
        bits.append(f"binary path `{src['binary_path']}` (no digest recorded)")
    if src.get("started_utc"):
        bits.append(f"started {src['started_utc']}")
    lines = [f"- {label}: " + ", ".join(bits)]
    ref = record_source(reference)
    differs = diverging_fields(src, ref)
    if differs:
        lines.append("- **Not the run named in the provenance block above** — "
                     + ", ".join(differs)
                     + " differ, so these two sections are not one measurement.")
    elif outside_reference_window(src, ref):
        # Two jobs on the same node reusing the same binary agree on every
        # field above, so the header's identity check cannot separate them.
        # The header states a run window; a section measured outside it was
        # not produced by the run the header describes.
        lines.append(f"- **Outside the run window named above** — measured at "
                     f"{src['started_utc']}, but the provenance block describes "
                     f"{ref['started_utc']} to {ref['finished_utc']}. Same host "
                     f"and same binary, different run.")
    return lines


def diverging_fields(src: Dict[str, Any], ref: Dict[str, Any]) -> List[str]:
    """Identity fields on which two records disagree, ignoring unknowns."""
    return [key for key in ("hostname", "gpu", "binary_sha256", "binary_path")
            if ref.get(key) is not None and src.get(key) is not None
            and ref[key] != src[key]]


def is_other_run(record: Optional[Dict[str, Any]],
                 reference: Optional[Dict[str, Any]]) -> bool:
    """Was this section measured by a run other than the header's?"""
    src, ref = record_source(record), record_source(reference)
    return bool(diverging_fields(src, ref) or outside_reference_window(src, ref))


def outside_reference_window(src: Dict[str, Any],
                             ref: Dict[str, Any]) -> bool:
    """Did this section start outside the window the header declares?

    Timestamps are the harness's own ISO-8601 UTC strings, which sort
    lexicographically, so no parsing is needed and a malformed or missing
    stamp is simply not evidence of divergence.
    """
    start, lo, hi = (src.get("started_utc"), ref.get("started_utc"),
                     ref.get("finished_utc"))
    if not (start and lo and hi):
        return False
    return start < lo or start > hi


def render_all24(report: Optional[Dict[str, Any]],
                 reference: Optional[Dict[str, Any]] = None) -> List[str]:
    """Render the integrated screen with the native witness on every row.

    The witness used to be printed for ``base`` only, so a schedule could be
    published as ``pass`` while the very same raw record carried
    ``native_cuda_proven: false`` for it -- which is what happened to ``resume``
    in the first published report. A per-schedule witness cell makes that
    contradiction impossible to render, and a schedule missing from a GPU run
    is called unproven rather than quietly omitted from the table.
    """
    lines = ["", "### Integrated candidate: all 24 tutorial movies", ""]
    if report is None:
        lines += ["_unrun_: no all-24 schedule-equality report was produced.", ""]
        return lines
    on_gpu = report.get("provenance", {}).get("gpu") is not None
    schedules = report.get("schedules", {})
    absent = missing_schedules(report)
    aggregate = "pass" if report.get("all24_equal") else "**FAIL**"
    if absent:
        aggregate = ("**PARTIAL** -- required schedule(s) "
                     + ", ".join(sorted(absent)) + " did not run, so this "
                     "dataset does not certify schedule equality")
    native = ("established for every schedule" if all24_witness_holds(report)
              else "**NOT established** -- see the witness column")
    lines += source_attribution(report, reference)
    asserted = report.get("star_metadata_asserted")
    unasserted = report.get("metadata_not_asserted")
    lines += [f"- Movies in STAR: {report.get('movies_in_star')} "
              f"(expected {report.get('expected_movies')})",
              f"- Aggregate pixel equality across schedules: {aggregate}",
              f"- Native {'CUDA' if on_gpu else 'CPU'} execution: {native}"]
    # What the screen checked about the metadata, rather than leaving the
    # reader to assume it checked the same fields the declared matrix does.
    if asserted:
        lines.append("- Metadata asserted on the base products: "
                     + ", ".join(f"`{k}`={v}" for k, v in sorted(asserted.items())
                                 if v is not None))
    elif asserted is not None:
        lines.append("- Metadata asserted on the base products: none")
    else:
        lines.append("- **This record asserted no STAR metadata.** It checked "
                     "product presence and cross-schedule equality only, so a "
                     "field wrong in the same way under every schedule would "
                     "not have been caught.")
    if unasserted:
        lines.append("- Not asserted here: " + ", ".join(f"`{u}`" for u in unasserted)
                     + " — the tutorial movies are not MRC, so this harness "
                       "cannot read the values a guess would have to match.")
    lines += ["",
              "Pixel equality and native execution are separate claims: equal "
              "pixels across schedules say nothing about which backend produced "
              "them.",
              "",
              "| Schedule | Runs | Movies exact | Missing pairs | "
              "Native witness | Verdict |",
              "|---|---:|---|---|---|---|"]
    for name, entry in schedules.items():
        witness = entry.get("backend_evidence", {})
        if not on_gpu:
            cell = ("**masquerade**" if witness.get("unexpected_cuda_marker")
                    else "n/a (CPU)")
        elif witness.get("vacuous"):
            cell = "**vacuous**"
        elif witness_coverage_gap(entry):
            cell = (f"**not covered** (1 of "
                    f"{len(entry.get('runs', []))} invocations examined)")
        elif witness.get("native_cuda_proven"):
            executed = witness.get("executed_movies")
            cell = f"yes ({len(executed)} executed)" if executed else "yes"
        else:
            cell = "**no**"
        if name == "base":
            lines.append(f"| base (uninterrupted) | 1 | "
                         f"{entry.get('movies_present')} present | "
                         f"{'0' if not entry.get('inventory_errors') else 'see raw'} | "
                         f"{cell} | n/a |")
            continue
        missing = entry.get("missing_pairs") or []
        verdict = "pass" if entry.get("passed") else "**FAIL**"
        # A row is never published as a pass on a GPU run whose witness did not
        # prove native execution: equal pixels across schedules say nothing
        # about which backend produced them.
        if entry.get("passed") and on_gpu and (not witness.get("native_cuda_proven")
                                               or witness_coverage_gap(entry)):
            verdict = "**pass (pixels) / native execution NOT established**"
        lines.append(f"| {name} | {len(entry.get('runs', []))} | "
                     f"{entry.get('movies_passed')}/{entry.get('movies_compared')} | "
                     f"{len(missing)} | {cell} | {verdict} |")
    for name in sorted(absent):
        lines.append(f"| {name} | 0 | _unrun_ | _unrun_ | _unrun_ | **UNRUN** |")
    if report.get("errors"):
        lines += ["", "Errors:"] + [f"- {e}" for e in report["errors"][:20]]
    return lines


#: Per-artefact statuses that mean a digest was actually computed and
#: compared. ``missing`` and ``undeclared_in_manifest`` mean the opposite.
COMPARED_STATUSES = ("match", "content_equal", "MISMATCH")


def fixture_coverage(verify: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """How many digests of each kind this record actually compared.

    Recomputed from the cases rather than read from ``compared``, so records
    written before that field existed are measured the same way. A record that
    compared nothing cannot support a verified verdict however its own
    ``verified`` flag reads: ``all()`` over no artefacts is true, which is the
    empty-set quantification withdrawn elsewhere in this harness.

    Schemas /1 to /3 recorded the movie digest at case level with no
    per-artefact block and no ground truth at all; that shape is read as one
    movie comparison and no truth comparison, which is what it was.
    """
    counts = {"movie": 0, "ground_truth": 0}
    for case in ((verify or {}).get("cases") or {}).values():
        for kind in counts:
            entry = case.get(kind)
            if entry is None and kind == "movie" and "movie" not in case \
                    and "ground_truth" not in case:
                entry = case
            if (entry or {}).get("status") in COMPARED_STATUSES:
                counts[kind] += 1
    return counts


def inputs_verified(verify: Optional[Dict[str, Any]]) -> bool:
    """The declared inputs were used, and that was established by comparison."""
    if not (verify and verify.get("verified")):
        return False
    coverage = fixture_coverage(verify)
    return bool(coverage["movie"] and coverage["ground_truth"])


def render_fixture_verification(verify: Optional[Dict[str, Any]]) -> List[str]:
    """State whether the inputs were the declared ones, before any verdict.

    Printed near the top because every row below is only as good as its input.
    An unverified or unchecked fixture set is said so plainly rather than
    omitted, since a missing section reads as though the check passed.
    """
    lines = ["", "### Input provenance", ""]
    if verify is None:
        lines += ["**Not checked in this report.** Fixture bytes were not "
                  "verified against the committed manifest, so no claim is "
                  "made that the declared inputs were used.", ""]
        return lines
    ok = inputs_verified(verify)
    cases = verify.get("cases", {})
    coverage = fixture_coverage(verify)
    lines += [f"- Fixtures checked against `test-data/known_motion/MANIFEST.json` "
              f"as tracked in git (ref `{verify.get('manifest_ref')}`, source "
              f"commit `{verify.get('manifest_source_commit')}`)",
              f"- Result: **{'VERIFIED' if ok else 'NOT VERIFIED'}** over "
              f"{len(cases)} declared case(s)",
              f"- Digests actually compared: {coverage['movie']} movie, "
              f"{coverage['ground_truth']} ground truth"]
    if not (coverage["movie"] and coverage["ground_truth"]):
        lines.append("- **Nothing was compared for at least one artefact kind, "
                     "so this record cannot verify the inputs** — a check that "
                     "compares no digests reports no mismatch.")
    # Per artefact, not per case. A case whose movie is byte-identical and
    # whose truth is content-equal is not "0 byte-identical"; rolling the two
    # into one status would understate what actually matched.
    for kind, label in (("movie", "Movies (`movie_sha256`)"),
                        ("ground_truth", "Ground truths (`ground_truth_sha256`)")):
        seen = [c[kind].get("status") for c in cases.values() if kind in c]
        if not seen:
            continue
        counts = {name: seen.count(name) for name in
                  ("match", "content_equal", "MISMATCH", "missing",
                   "undeclared_in_manifest") if seen.count(name)}
        lines.append(f"  - {label}: " + ", ".join(
            f"{n} {name.replace('_', ' ')}" for name, n in counts.items()))
    if coverage["movie"] and not coverage["ground_truth"]:
        # Keyed on what the record shows was checked, not on its schema
        # string. Schemas /1 and /2 checked movie_sha256 only, but a later
        # schema whose cases happen to carry no ground-truth status is in
        # exactly the same position, and would otherwise print no caveat.
        lines.append("- **This record checked `movie_sha256` only.** The "
                     "`*_ground_truth.json` files, from which the motion-truth "
                     "verdicts are computed, were not checked by it. "
                     "See `withdrawals.md` W3.")
    if verify.get("content_equal"):
        lines.append(f"- Content-equal (digest differs, every value the same "
                     f"number — commit stamp and/or last-bit float rendering): "
                     f"{', '.join(verify['content_equal'])}")
    if verify.get("mismatched"):
        lines.append(f"- **Mismatched: {', '.join(verify['mismatched'])}**")
    if verify.get("missing"):
        lines.append(f"- Not generated (not attempted): "
                     f"{', '.join(verify['missing'])}")
    lines += [f"- NumPy in the verifying process: "
              f"{verify.get('verifier_numpy_version')} (the hashes above are "
              f"of bytes on disk, so this does not affect the comparison; the "
              f"generating environment is recorded in `provenance.md`)",
              "",
              "The manifest is read from git, never from the copy the generator "
              "writes beside its own output — that copy agrees by construction "
              "and concealed a real cross-host divergence during this work.", ""]
    return lines


def sampled_binary(capacity: Optional[Dict[str, Any]]) -> Optional[str]:
    """The binary the capacity sampler was pointed at, if its command says."""
    command = (capacity or {}).get("command") or []
    if "--binary" in command:
        index = command.index("--binary") + 1
        if index < len(command):
            return str(command[index])
    return None


def render_capacity(capacity: Optional[Dict[str, Any]],
                    reference: Optional[Dict[str, Any]] = None) -> List[str]:
    """One measured capacity datapoint, stated only for what was measured."""
    lines = ["", "### Memory capacity (measured, single datapoint)", ""]
    if capacity is None:
        lines += ["_unrun_: no capacity measurement was taken. No capacity "
                  "claim is made.", ""]
        return lines
    # The measurement records no host, no start time and no binary digest, so
    # "device 0" here cannot be tied to the device 0 of the run in the header.
    # Its sampled command does name a binary path, though, and saying "no
    # binary recorded" while the record shows a different build understates
    # the gap: it is not merely unattributed, it is attributable elsewhere.
    lines += source_attribution(capacity, reference) or [
        "- Source record: **no host, no start time and no binary digest are "
        "recorded in this measurement**, so the device index below cannot be "
        "attributed to the run named in the provenance block."]
    sampled = sampled_binary(capacity)
    if sampled:
        header_binary = record_source(reference).get("binary_path")
        lines.append(
            f"- The sampled command names binary `{sampled}`"
            + (f", which is **not** the binary in the provenance block "
               f"(`{header_binary}`) — a different build"
               if header_binary and header_binary != sampled else "")
            + ".")
    lines += [f"- Configuration: `{capacity.get('row_id')}` — "
              f"{capacity.get('note') or 'no description recorded'}",
              f"- Device: {capacity.get('device')} "
              f"({capacity.get('device_total_mib')} MiB total)",
              f"- **Peak device memory observed: "
              f"{capacity.get('peak_used_mib')} MiB**, sampled every "
              f"{capacity.get('sample_interval_sec')} s over "
              f"{capacity.get('samples')} samples",
              f"- Exit status of the sampled command: "
              f"{capacity.get('returncode')} — recorded, not interpreted. The "
              f"row's own verdict is in the matrix table above; an exit status "
              f"is never read here as evidence of success, failure or fallback.",
              "",
              "This is a measurement of one configuration on one device, not a "
              "capacity claim for other geometries, frame counts or devices. "
              "No universal CPU-fallback behaviour is claimed.", ""]
    return lines


def render_deferred() -> List[str]:
    lines = ["", "### Deliberately not attempted here", "",
             "Named rather than implied, so the table is not read as broader "
             "than it is.", "",
             "| Coverage | Owner | Why |", "|---|---|---|"]
    for title, owner, why in declared.DEFERRED:
        lines.append(f"| {title} | {owner} | {why} |")
    return lines


def render_numerical(truth: Optional[Dict[str, Any]],
                     cpu_diag: Optional[Dict[str, Any]],
                     reference: Optional[Dict[str, Any]] = None) -> List[str]:
    lines = ["", "### Numerical gates (separate verdicts)", "",
             "These are not implied by any implementation row above.", ""]
    if truth is None:
        lines.append("- Motion truth (`run_known_motion_gates.py`): _unrun_.")
    else:
        lines += source_attribution(truth, reference,
                                    "Source record for the motion-truth gates")
        results = truth.get("results", {})
        items = results.items() if isinstance(results, dict) else \
            ((r.get("case"), r) for r in results)
        for case, entry in items:
            verdict = entry.get("verdict") or entry.get("status") or entry.get("result")
            role = entry.get("role", "")
            lines.append(f"- Motion truth `{case}` ({role}): **{verdict}**")
    if cpu_diag is None:
        lines.append("- CPU-backend diagnostic: _unrun_ in this report.")
    else:
        counts = cpu_diag.get("counts", {})
        unrun = cpu_diag.get("unrun_rows", [])
        host = cpu_diag.get("provenance", {}).get("hostname", "unknown host")
        # The CPU diagnostic is a different host, a different binary and, in
        # every report so far, a different day. It sat under the motion-truth
        # attribution above with no source of its own, which is the very thing
        # per-section attribution exists to prevent.
        lines += source_attribution(cpu_diag, reference,
                                    "Source record for the CPU diagnostic")
        lines.append(
            f"- CPU-backend diagnostic (`{host}`): {counts.get('pass')} pass, "
            f"{counts.get('fail')} fail, {counts.get('error')} error of "
            f"{counts.get('attempted')} attempted"
            + (f"; unrun: {', '.join(unrun)}" if unrun else "")
            + ". This is a separate verdict: it neither establishes nor "
              "overrides any native CUDA result above.")
    lines += ["",
              "Historical CPU/RELION Gate 2 failures remain failures. An exact "
              "schedule comparison never converts one into a pass."]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-json", type=Path)
    parser.add_argument("--all24-json", type=Path)
    parser.add_argument("--truth-json", type=Path)
    parser.add_argument("--cpu-diagnostic-json", type=Path)
    parser.add_argument("--capacity-json", type=Path)
    parser.add_argument("--fixture-verify-json", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    opts = parser.parse_args()

    matrix_report = load(opts.matrix_json)
    all24 = load(opts.all24_json)
    truth = load(opts.truth_json)
    cpu_diag = load(opts.cpu_diagnostic_json)
    capacity = load(opts.capacity_json)
    fixture_verify = load(opts.fixture_verify_json)

    lines = ["# Issue 83 support report", "",
             "Generated by `tools/validation_issue83/report.py` from raw per-case "
             "reports. Rows without a raw result are named `unrun`.", ""]
    if matrix_report:
        prov = matrix_report.get("provenance", {})
        lines += ["## Provenance", "",
                  "This block describes the **declared-matrix** run. Sections "
                  "below name their own source record, and say so when it is a "
                  "different run.", "",
                  f"- Host: `{prov.get('hostname')}`, device `{prov.get('gpu')}`",
                  f"- Binary: `{prov.get('binary')}`",
                  f"- Binary SHA256: `{prov.get('binary_sha256')}`",
                  f"- Comparator SHA256: `{prov.get('comparator_sha256')}`",
                  f"- Harness SHA256: matrix `{prov.get('matrix_sha256')}`, "
                  f"runner `{prov.get('runner_sha256')}`",
                  f"- Run: {prov.get('started_utc')} to "
                  f"{matrix_report.get('finished_utc')}", ""]
        counts = matrix_report.get("counts", {})
        unrun = matrix_report.get("unrun_rows", [])
        lines += [f"- Declared rows {counts.get('declared')}; attempted "
                  f"{counts.get('attempted')}; pass {counts.get('pass')}; "
                  f"fail {counts.get('fail')}; error {counts.get('error')}",
                  f"- Unrun rows: {', '.join(unrun) if unrun else 'none'}", ""]

    lines += render_fixture_verification(fixture_verify)
    lines += render_matrix(matrix_report)
    lines += render_all24(all24, matrix_report)
    lines += render_capacity(capacity, matrix_report)
    lines += render_numerical(truth, cpu_diag, matrix_report)
    lines += render_deferred()

    # Every conjunct the record supplies is paired with one recomputed here:
    # a record's own ``matrix_complete`` / ``all24_equal`` is a summary written
    # by the harness that produced it, and a summary is not the measurement.
    inputs_ok = inputs_verified(fixture_verify)
    complete = bool(matrix_report and matrix_report.get("matrix_complete")
                    and not matrix_report.get("unrun_rows")
                    and all24 and all24.get("all24_equal") and inputs_ok
                    and not missing_schedules(all24)
                    and all24_witness_holds(all24))
    lines += ["", "## Aggregate", "",
              ("The declared matrix is complete, every attempted row passed, "
               "and the inputs were verified against the committed manifest."
               if complete else
               "**The declared matrix is not complete.** Unrun and failing rows "
               "are named above; this report does not claim the broad matrix "
               "passed."), ""]
    # Completeness and equality are not the same claim as "the native backend
    # ran". The matrix rows above pass on pixels; where their per-schedule
    # witness was never consumed, the native claim for those schedules is
    # withheld here rather than carried silently by the row verdict.
    gaps = matrix_witness_gaps(matrix_report)
    if gaps:
        lines += [f"**Withheld:** for {len(gaps)} of the declared rows this "
                  f"report does not claim that the repeat, batch and resume "
                  f"schedules ran natively on the GPU. Those runs happened, "
                  f"and their "
                  f"pixels are equal; the record that survives them does not "
                  f"say which backend produced them, so the claim is unrun "
                  f"until the fixed harness runs on a dedicated allocation.",
                  ""]
    # The aggregate sentence is the line most likely to be quoted on its own,
    # so it carries the multi-run caveat rather than relying on the reader
    # having read the section attributions above.
    assembled = [name for name, record in (("integrated all-24 screen", all24),
                                           ("capacity datapoint", capacity),
                                           ("motion-truth gates", truth),
                                           ("CPU-backend diagnostic", cpu_diag))
                 if record is not None and is_other_run(record, matrix_report)]
    if assembled:
        named = (assembled[0] if len(assembled) == 1
                 else ", the ".join(assembled[:-1]) + " and the " + assembled[-1])
        lines += ["This aggregate is assembled from more than one run: the "
                  + named + " did not come from the run named in the "
                  "provenance block. Each section says so above.", ""]

    opts.out.parent.mkdir(parents=True, exist_ok=True)
    opts.out.write_text("\n".join(lines) + "\n")
    print(f"wrote {opts.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
