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
from typing import Any, Dict, List, Optional, Tuple

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
    witness = sched.get("backend_evidence", {})
    if not on_gpu:
        # The CPU run collects the same per-schedule witness and the required
        # result is its *absence*. Printing the equality alone dropped it: a
        # repeat schedule that emitted CUDA markers during a CPU run rendered
        # as a plain `exact 3/3`, which is W1 in the CPU direction.
        if witness.get("unexpected_cuda_marker"):
            return f"{cell}, **masquerade** (CUDA marker on a CPU run)"
        if not witness.get("per_movie"):
            return f"{cell}, marker absence **not recorded**"
        return f"{cell}, no CUDA marker"
    if witness.get("vacuous"):
        return f"{cell}, witness **vacuous**"
    if not native_established(sched):
        return f"{cell}, witness {unwitnessed_reason(sched)}"
    per_movie = witness.get("per_movie") or {}
    executed = witness.get("executed_movies")
    scope = (f"{len(executed)} executed" if executed is not None
             else f"{len(per_movie)}/{len(per_movie)} movies marked")
    seen, total = banner_coverage(sched)
    # The banner is the weaker, redundant witness; its gap is disclosed, not
    # used to withhold the stage evidence that is present.
    banner = "" if seen >= total else f", banner {seen}/{total}"
    return f"{cell}, native ({scope}{banner})"


def render_matrix(report: Optional[Dict[str, Any]]) -> List[str]:
    # On a CPU run the absence of a CUDA marker is the required result, not a
    # failure, so the witness column is labelled by the backend that was used.
    device = (report or {}).get("provenance", {}).get("gpu")
    recorded = device_recorded(report)
    on_gpu = recorded and device is not None
    on_cpu = recorded and device is None
    if on_gpu:
        heading = f"### Implementation coverage (native CUDA, device {device})"
    elif on_cpu:
        heading = "### Implementation coverage (CPU backend — separate diagnostic)"
    else:
        heading = "### Implementation coverage (**device not recorded**)"
    # Named for the run it describes. The schedule columns carry their own
    # witness, because the base run's says nothing about them.
    witness_column = ("Native witness (base)" if on_gpu
                      else "CUDA marker absent" if on_cpu
                      else "Backend (**not recorded**)")
    lines = [heading, "",
             "Exact = every movie identical to the uninterrupted run under "
             "`compare_motioncorr.py --gate exact`.", ""]
    if on_cpu:
        lines += ["This run used the CPU backend. A CUDA marker here would mean "
                  "a masquerading run, so the column below requires its "
                  "**absence**.", ""]
    elif not on_gpu:
        lines += ["**This record does not say which device it used.** Its "
                  "provenance block carries no `gpu` field at all, which is "
                  "silence, not the measurement `gpu: null`. Neither the "
                  "native-execution claim nor the CPU marker-absence claim is "
                  "available from it.", ""]
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
            productcell = reject_cell(reject)
            repeat = batch = resume = "n/a"
        else:
            if on_gpu:
                native = "yes" if native_established(base) else "**no**"
            elif on_cpu:
                # "Confirmed absent" is a claim about what was looked at. A
                # record carrying no per-movie evidence looked at nothing, and
                # printing the required answer from no evidence is the vacuity
                # this whole document exists to refuse.
                if witness.get("unexpected_cuda_marker"):
                    native = "**masquerade**"
                elif not witness.get("per_movie"):
                    native = "**not recorded**"
                else:
                    native = "confirmed absent"
            else:
                native = "**not recorded**"
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
    reject_gaps = rejection_coverage_gaps(report)
    if reject_gaps:
        lines += ["",
                  f"**Rejection by name is not established for "
                  f"{len(reject_gaps)} of these rows.** Their verdict was "
                  f"written by the bare-substring test, which any output "
                  f"containing the letters satisfied, and the line it matched "
                  f"was not kept. Rows affected: "
                  + ", ".join(f"`{g}`" for g in reject_gaps) + "."]
    return lines


def reject_cell(reject: Dict[str, Any]) -> str:
    """How an invalid-option row was rejected, and whether that was checked.

    The published claim is that the binary rejects the option *by name*. Before
    the fix that was a bare substring test over stdout and stderr, which any
    backtrace path containing the letters satisfied, and the matched text was
    not kept -- so a record from that harness cannot show which line, if any,
    named the option. Printing ``named=True`` for it would republish the old
    test's verdict as though it were the new one's.
    """
    rc = reject.get("returncode")
    if "option_named_line" not in reject:
        return (f"rc={rc}, named **not covered** — this record predates the "
                f"delimited matcher and kept no matched line")
    if not reject.get("option_named"):
        return f"rc={rc}, option **not named** on any diagnostic line"
    line = (reject.get("option_named_line") or "").strip().replace("|", "\\|")
    return f"rc={rc}, named by `{line}`"


def rejection_coverage_gaps(report: Optional[Dict[str, Any]]) -> List[str]:
    """Rejection rows whose record cannot show the option was named."""
    if not report:
        return []
    return [entry["row_id"] for entry in report.get("results", [])
            if "reject" in entry.get("schedules", {})
            and "option_named_line" not in entry["schedules"]["reject"]]


def matrix_complete(report: Optional[Dict[str, Any]]) -> bool:
    """Every declared row was attempted and passed, recomputed from the rows.

    ``matrix_complete`` and ``unrun_rows`` are the producing harness's summary
    of itself. A record listing four results, all passing, with
    ``matrix_complete: true`` and ``unrun_rows: []`` describes a complete
    matrix only if the declared set has four rows. The declared set is read
    from :mod:`declared`, which is the same list the runner works from, so the
    renderer answers the question the summary is a claim about.
    """
    if not report:
        return False
    by_id = {r.get("row_id"): r for r in report.get("results", [])}
    for row in declared.ROWS:
        entry = by_id.get(row.row_id)
        if entry is None or entry.get("status") != "pass":
            return False
    return True


def matrix_witness_gaps(report: Optional[Dict[str, Any]]) -> List[str]:
    """Rows of a GPU matrix whose per-schedule native execution is unproven.

    A row's ``status`` was written by a harness that collected a witness for
    repeat, batch and resume and then consumed none of it, so ``pass`` there
    covers pixel equality and the *base* run's backend, and nothing about the
    backend the other three schedules used. Recomputed here rather than read
    off the record, because the record has no field for it.

    A rejection row runs no payload and has only a ``reject`` entry, so it is
    excluded by looking for that entry rather than by tolerating absent
    schedules. Tolerating absence meant a payload row whose record held only
    ``base`` produced no gap at all, and its ``pass`` then carried the native
    claim for three schedules with no record whatsoever.

    The per-schedule test is :func:`native_established`, which asks whether
    every movie that schedule executed carries a kernel stage marker. It used
    to also demand the producer's ``native_cuda_proven``, and before that
    ``startup_marker_per_invocation`` -- field names only the newer runners
    write, which made every row of an otherwise fully witnessed record a gap
    and withheld a measured claim.
    """
    if not device_recorded(report) or report.get("provenance", {}).get("gpu") is None:
        return []
    gaps = []
    for entry in report.get("results", []):
        schedules = entry.get("schedules", {})
        if "reject" in schedules:
            continue
        if any(name not in schedules or not native_established(schedules[name])
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

    Always recomputed from the schedules present, and unioned with whatever the
    record names. A record written before ``missing_required_schedules`` existed
    carries no such field, and reading it as "nothing missing" is how a screen
    with only ``base`` and ``repeat`` could render **PARTIAL** in its own table
    and still be counted complete by the aggregate at the foot of the same
    document.

    Returning the record's own list *instead of* recomputing had the same shape
    of defect one level up: a screen carrying ``missing_required_schedules: []``
    and a ``schedules`` map holding only ``base`` would have been certified
    complete on the strength of its own summary. The renderer must be able to
    judge a record written by any harness, so the summary is read as a claim to
    be added to, never as the measurement.
    """
    if not report:
        return []
    named = report.get("missing_required_schedules") or []
    schedules = report.get("schedules", {})
    recomputed = [s for s in REQUIRED_SCHEDULES if s not in schedules]
    return sorted(set(named) | set(recomputed))


def all24_equality_holds(report: Optional[Dict[str, Any]]) -> bool:
    """Cross-schedule pixel equality, recomputed from the per-movie numbers.

    ``all24_equal`` is the producing harness's own summary. Reading it as the
    measurement is how a screen certifies equality it never established: a
    record whose ``repeat`` compared zero movies has nothing that can differ,
    and every ``all()`` in the producer over that empty set is true. The
    summary is honoured only where the numbers underneath it agree, so the
    claim is conjoined with a recomputation rather than replaced by one.

    Each required schedule must be present, be marked passed, have compared at
    least one movie, have every compared movie exact, and be missing no
    image/metadata pair.
    """
    if not report or not report.get("all24_equal"):
        return False
    schedules = report.get("schedules", {})
    if missing_schedules(report):
        return False
    for name in REQUIRED_SCHEDULES:
        entry = schedules.get(name) or {}
        compared = entry.get("movies_compared")
        if not entry.get("passed") or not compared:
            return False
        if entry.get("movies_passed") != compared:
            return False
        if entry.get("missing_pairs"):
            return False
    return True


def all24_witness_holds(report: Optional[Dict[str, Any]]) -> bool:
    """Every schedule of a GPU integrated screen proved native execution.

    Recomputed here from the per-schedule evidence rather than trusting the
    record's own ``all24_equal``, because a report written by an older harness
    can carry ``all24_equal: true`` alongside a schedule whose
    ``native_cuda_proven`` is false -- the contradiction this generator
    published once already.

    On a CPU record the required result is the *absence* of a CUDA marker, and
    that absence still has to have been looked for. Asking only "did nothing
    report a masquerade" was true of a record carrying no per-movie evidence at
    all, which is the same empty quantification in the CPU direction: a screen
    that inspected no logs cannot certify that no log named CUDA. Every
    schedule must therefore carry per-movie evidence, and none of it may show a
    marker.

    A record that does not say which device it used gets neither answer. The
    missing-schedule gate applies to every record. It used to sit below the CPU
    branch, so a CPU screen holding only ``base`` rendered "Native CPU
    execution: established for every schedule" -- every schedule being the one
    that ran.
    """
    if not report or not device_recorded(report):
        return False
    schedules = report.get("schedules", {})
    if not schedules:
        return False
    if missing_schedules(report):
        return False
    if report.get("provenance", {}).get("gpu") is None:
        return all(e.get("backend_evidence", {}).get("per_movie")
                   and not e.get("backend_evidence", {}).get("unexpected_cuda_marker")
                   for e in schedules.values())
    return all(native_established(e) for e in schedules.values())


def witness_coverage_gap(entry: Dict[str, Any]) -> bool:
    """This schedule's own products are not fully witnessed as native.

    There are two separate witnesses and they must not be conflated, which is
    the correction this function carries. The *startup banner* is printed once
    per invocation on stdout; only the last invocation's stdout was kept, so on
    a 24-invocation batch 23 banners are absent and unrecoverable. The *kernel
    stage marker* is written into each movie's own log in the schedule's own
    output directory, by the CUDA code path itself, and it is recorded per
    movie for every schedule.

    Keying coverage on the banner alone treated a schedule whose every product
    carried a stage marker as unwitnessed, and the report then withheld a
    per-schedule native claim that was in fact measured. Withholding something
    measured is as much a misstatement as publishing something unmeasured, so
    the gate now asks the question the claim actually rests on: was every movie
    whose pixels are being compared produced by the CUDA path?

    ``executed_movies``, where the record names it, is the set that was
    actually run -- a seeded resume preserves products it did not re-execute,
    and those carry no new marker. Where the record does *not* name it, every
    movie listed must be marked: a record showing 16 of 24 marked and no
    executed set cannot distinguish eight movies skipped from eight run on the
    CPU, and that ambiguity is a gap.

    The banner's partial coverage is still real and still missing. It is
    reported by :func:`banner_coverage` and disclosed in the cell rather than
    used to withhold the whole claim.
    """
    evidence = entry.get("backend_evidence", {})
    per_movie = evidence.get("per_movie") or {}
    if not per_movie:
        return True
    executed = evidence.get("executed_movies")
    names = list(executed) if executed is not None else list(per_movie)
    if not names:
        return True
    return not all(per_movie.get(name, {}).get("log_present")
                   and per_movie.get(name, {}).get("cuda_stage_marker")
                   for name in names)


def banner_coverage(entry: Dict[str, Any]) -> Tuple[int, int]:
    """(invocations whose startup banner is in the record, invocations run).

    A single-invocation schedule with its banner found is fully covered; the
    old renderer said "1 of 1" was a gap for nobody but printed "not covered"
    for it all the same, because it looked only for a field name.
    """
    evidence = entry.get("backend_evidence", {})
    total = len(entry.get("runs", []) or [])
    per = evidence.get("startup_marker_per_invocation")
    if per is not None:
        return sum(1 for seen in per if seen), max(total, len(per))
    return (1 if evidence.get("startup_marker_found") else 0), max(total, 1)


def stage_witness_holds(entry: Dict[str, Any]) -> bool:
    """The kernel's own per-movie markers establish native execution here.

    This is the witness the claim rests on: ``[CUDA <stage>] completed;`` is
    written into each movie's log by the CUDA code path itself, in this
    schedule's own output directory. It is not the startup banner.
    """
    evidence = entry.get("backend_evidence", {})
    if evidence.get("requested") == "cpu" or evidence.get("vacuous"):
        return False
    return bool(evidence.get("per_movie")) and not witness_coverage_gap(entry)


def native_established(entry: Dict[str, Any]) -> bool:
    """Did this schedule run natively, on the strongest witness available?

    The claim rests on this schedule's own per-movie kernel markers, and on
    nothing else. Two failure modes are being avoided at once, and they pull
    in opposite directions.

    Requiring the producer's ``native_cuda_proven`` withholds a measured
    claim: a producer that conjoined the *startup banner* into that field
    writes ``false`` for a schedule whose every executed movie carries a stage
    marker, because the banner of a non-final invocation is frequently not in
    the record at all -- only the last invocation's stdout was kept. Reading
    that ``false`` as "did not run natively" is the conflation withdrawn as
    W8a.

    Accepting the producer's ``true`` on its own is the opposite fault: a
    record can carry ``native_cuda_proven: true`` beside sixteen marked movies
    of twenty-four, and honouring the summary over the evidence beneath it is
    the whole failure this harness documents. So the field is consulted for
    neither verdict; the per-movie markers decide, and the banner's absence
    stays visible through :func:`banner_coverage`, disclosed in the cell
    rather than used to withhold the row.
    """
    evidence = entry.get("backend_evidence", {})
    if evidence.get("unexpected_cuda_marker"):
        return False
    return stage_witness_holds(entry)


def unwitnessed_reason(entry: Dict[str, Any]) -> str:
    """Why this schedule's native execution is not established, specifically.

    One phrasing, used by both the matrix cell and the integrated screen's
    cell, so the same record cannot be described two ways in one document.

    The per-movie account comes first where there is one: "16 of 24 movies
    marked" tells the reader what the record holds, while the producer's
    ``native_cuda_proven: false`` only tells them what it concluded -- and
    that conclusion is unreliable in the direction W8a withdraws, since a
    producer conjoining the startup banner writes false for a fully marked
    schedule. Only when there is no per-movie evidence at all does the
    explicit negative become the most informative thing available.
    """
    evidence = entry.get("backend_evidence", {})
    if evidence.get("unexpected_cuda_marker"):
        return "**masquerade** (CUDA marker where none was requested)"
    per_movie = evidence.get("per_movie") or {}
    if per_movie:
        marked = sum(1 for m in per_movie.values() if m.get("cuda_stage_marker"))
        return f"**not covered** ({marked} of {len(per_movie)} movies marked)"
    if evidence.get("native_cuda_proven") is False:
        return "**no** — native execution **NOT established**"
    return "**not covered** (no per-movie record)"


def device_recorded(report: Optional[Dict[str, Any]]) -> bool:
    """Does this record say which device it used, at all?

    ``gpu: null`` is a measurement -- the run used the CPU backend. A
    provenance block with **no** ``gpu`` key is not that statement; it is
    silence. Reading silence as ``null`` published a GPU record whose
    provenance was lost as a clean CPU diagnostic, with every row's missing
    CUDA marker rendered as the required absence.
    """
    return "gpu" in (report or {}).get("provenance", {})


def record_source(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Where one section's numbers came from, whatever shape the record has.

    ``run_known_motion_gates.py`` is a merged tool and is not modified here; it
    names its binary and device at the top level rather than in a provenance
    block, so both shapes are read. Its ``binary`` is a path rather than a
    digest, and it is the only field separating that tool's output on one host
    from its output on another -- dropping it left five gate verdicts
    attributable to neither job.

    ``gpu`` is the one field where ``None`` is a *measurement*: every runner
    writes the key, and a null there means the run used the CPU backend.
    ``gpu_recorded`` says whether the key was present, so a CPU section is not
    read as "device unknown" and folded into a GPU header.
    """
    if not record:
        return {}
    prov = record.get("provenance") or {}
    return {"hostname": prov.get("hostname"),
            "gpu": prov.get("gpu", record.get("gpu")),
            "gpu_recorded": "gpu" in prov or "gpu" in record,
            "binary_sha256": prov.get("binary_sha256"),
            "binary_path": prov.get("binary", record.get("binary")),
            "started_utc": prov.get("started_utc"),
            "finished_utc": record.get("finished_utc")}


def source_attribution(record: Optional[Dict[str, Any]],
                       reference: Optional[Dict[str, Any]] = None,
                       label: str = "Source record",
                       unattributable: Optional[str] = None) -> List[str]:
    """Name the run a section came from, and say when it is not the same run.

    The provenance block at the top of the report is the matrix record's. A
    report may legitimately be assembled from more than one job -- the first
    native allocation generated its fixtures with the wrong interpreter, so its
    integrated screen and its fixture-dependent legs come from different jobs --
    and a single header would then present two measurements as one. Each
    section states its own host, device and binary, and any divergence from the
    header is named rather than left for the reader to notice.

    There are three states, not two. A record may name a run that is the
    header's, name one that is not, or name nothing at all -- and the third is
    not the first. Returning no line for it left the section sitting silently
    under the header's provenance block, which is the inheritance this function
    exists to stop. It now says **unattributable** instead.
    """
    src = record_source(record)
    # ``finished_utc`` alone identifies nothing -- it is carried only so this
    # record can serve as the reference window for another section.
    if not any(src.get(k) is not None
               for k in ("hostname", "gpu", "binary_sha256", "binary_path",
                         "started_utc")):
        return [unattributable or
                f"- {label}: **unattributable** — this record carries no field "
                f"in its provenance block that could tie it to a run: no host, "
                f"no start time and no binary digest. (A record may still name "
                f"a bare device index elsewhere; an index is not an identity.) "
                f"It cannot be shown to be the run in the provenance block "
                f"above, and that block must not be read as describing it."]
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
    """Identity fields on which two records disagree, ignoring unknowns.

    ``gpu`` is excluded from the "ignore ``None``" rule. Skipping it there made
    ``gpu: null`` -- which means *this ran on the CPU* -- indistinguishable from
    a record that never said, so a CPU section under a GPU header diverged on
    nothing and was rendered as part of the header's run. It is compared
    whenever both records recorded the key, null included.
    """
    differs = []
    for key in ("hostname", "gpu", "binary_sha256", "binary_path"):
        if key == "gpu":
            if (src.get("gpu_recorded") and ref.get("gpu_recorded")
                    and src.get("gpu") != ref.get("gpu")):
                differs.append(key)
            continue
        if (ref.get(key) is not None and src.get(key) is not None
                and ref[key] != src[key]):
            differs.append(key)
    return differs


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
    recorded = device_recorded(report)
    on_gpu = recorded and report.get("provenance", {}).get("gpu") is not None
    on_cpu = recorded and report.get("provenance", {}).get("gpu") is None
    schedules = report.get("schedules", {})
    absent = missing_schedules(report)
    aggregate = "pass" if all24_equality_holds(report) else "**FAIL**"
    if absent:
        aggregate = ("**PARTIAL** -- required schedule(s) "
                     + ", ".join(sorted(absent)) + " did not run, so this "
                     "dataset does not certify schedule equality")
    native = ("established for every schedule" if all24_witness_holds(report)
              else "**NOT established** -- see the witness column")
    backend = "CUDA" if on_gpu else "CPU" if on_cpu else "(device not recorded)"
    lines += source_attribution(report, reference)
    asserted = report.get("star_metadata_asserted")
    unasserted = report.get("metadata_not_asserted")
    lines += [f"- Movies in STAR: {report.get('movies_in_star')} "
              f"(expected {report.get('expected_movies')})",
              f"- Aggregate pixel equality across schedules: {aggregate}",
              f"- Native {backend} execution: {native}"]
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
        if on_cpu:
            if witness.get("unexpected_cuda_marker"):
                cell = "**masquerade**"
            elif not witness.get("per_movie"):
                cell = "**marker absence not recorded**"
            else:
                cell = "n/a (CPU), no marker"
        elif not on_gpu:
            cell = "**device not recorded**"
        elif witness.get("vacuous"):
            cell = "**vacuous**"
        elif not native_established(entry):
            cell = unwitnessed_reason(entry)
        else:
            executed = witness.get("executed_movies")
            cell = f"yes ({len(executed)} executed)" if executed else "yes"
            seen, total = banner_coverage(entry)
            if seen < total:
                # Stage markers cover every product; the startup banner of the
                # earlier invocations is not in the record. Say which.
                cell += f", banner {seen}/{total}"
        if name == "base":
            # Both of these used to be literals. "1" was printed whatever the
            # base entry recorded, and the "Missing pairs" column was filled
            # from the *inventory* error list, which is a different
            # measurement -- a base record that compared no pairs at all read
            # as a base record that was missing none. Both are now read from
            # the record: a base entry recording one invocation command is one
            # run, and a record holding neither a run list nor a command says
            # so.
            if entry.get("runs"):
                runs = str(len(entry["runs"]))
            elif entry.get("command"):
                runs = "1"
            else:
                runs = "**not recorded**"
            errs = entry.get("inventory_errors")
            lines.append(f"| base (uninterrupted) | {runs} | "
                         f"{entry.get('movies_present')} present | "
                         f"{'n/a (inventory: 0 errors)' if errs == [] else 'see raw'} | "
                         f"{cell} | n/a |")
            continue
        missing = entry.get("missing_pairs") or []
        verdict = "pass" if entry.get("passed") else "**FAIL**"
        # A row is never published as a pass on a GPU run whose witness did not
        # prove native execution: equal pixels across schedules say nothing
        # about which backend produced them.
        if entry.get("passed") and on_gpu and not native_established(entry):
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
    """The declared inputs were used, and that was established by comparison.

    ``verified`` is the checker's own verdict; the mismatch dimension is
    recomputed here rather than taken from it, because a record can carry
    ``verified: true`` beside a per-artefact ``MISMATCH`` -- that is exactly
    the shape the fixture defect on SCARF produced before the checker was
    fixed, and a consumer that only reads the summary republishes it.
    """
    if not (verify and verify.get("verified")):
        return False
    if verify.get("vacuous"):
        return False
    coverage = fixture_coverage(verify)
    if not (coverage["movie"] and coverage["ground_truth"]):
        return False
    return not fixture_mismatches(verify)


def fixture_mismatches(verify: Optional[Dict[str, Any]]) -> List[str]:
    """Per-artefact statuses in this record that are not a clean comparison."""
    bad = []
    for case, body in ((verify or {}).get("cases") or {}).items():
        for kind in ("movie", "ground_truth"):
            entry = body.get(kind)
            if entry is None and kind == "movie" and "movie" not in body \
                    and "ground_truth" not in body:
                entry = body
            status = (entry or {}).get("status")
            if status is not None and status not in ("match", "content_equal"):
                bad.append(f"{case}/{kind}={status}")
    return sorted(bad)


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
    lines += source_attribution(
        capacity, reference,
        unattributable="- Source record: **no host, no start time and no "
                       "binary digest are recorded in this measurement**, so "
                       "the device index below cannot be attributed to the run "
                       "named in the provenance block.")
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
              # A sampler that collected nothing writes ``peak_used_mib: null``
              # and exits with the wrapped command's status, so a clean exit
              # with no measurement read as success. "None MiB" is not a
              # number; it is an unrun measurement and is named as one.
              (f"- **Peak device memory: _unrun_** — the sampler recorded "
               f"{capacity.get('samples')} samples and no peak, so this "
               f"datapoint measures nothing and no capacity figure is claimed "
               f"from it."
               if capacity.get("peak_used_mib") is None
               or not capacity.get("samples") else
               f"- **Peak device memory observed: "
               f"{capacity.get('peak_used_mib')} MiB**, sampled every "
               f"{capacity.get('sample_interval_sec')} s over "
               f"{capacity.get('samples')} samples"),
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
        items = list(results.items() if isinstance(results, dict) else
                     ((r.get("case"), r) for r in results))
        # A record holding no cases used to render as a heading, a source line
        # and the closing boilerplate -- a section that looked like gates had
        # been run and had nothing to report. Nothing evaluated is its own
        # verdict, and it is not a pass.
        if not items:
            lines.append("- Motion truth: **nothing was evaluated** — this "
                         "record contains no gate results, so it establishes "
                         "no numerical verdict either way.")
        for case, entry in items:
            verdict = entry.get("verdict") or entry.get("status") or entry.get("result")
            role = entry.get("role", "")
            if verdict is None:
                lines.append(f"- Motion truth `{case}` ({role}): **verdict not "
                             f"stated in the record**")
                continue
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
                    and matrix_complete(matrix_report)
                    and all24 and all24_equality_holds(all24) and inputs_ok
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
    sections = (("integrated all-24 screen", all24),
                ("capacity datapoint", capacity),
                ("motion-truth gates", truth),
                ("CPU-backend diagnostic", cpu_diag))
    assembled = [name for name, record in sections
                 if record is not None and is_other_run(record, matrix_report)]
    # A section that names nothing cannot be shown to be a different run, and
    # equally cannot be shown to be this one. Silence put it in the second
    # category by default; it is named here as neither.
    unattributed = [name for name, record in sections
                    if record is not None and not is_other_run(record, matrix_report)
                    and not any(record_source(record).get(k) is not None
                                for k in ("hostname", "gpu", "binary_sha256",
                                          "binary_path", "started_utc"))]
    if unattributed:
        # Do not enumerate the missing fields here. This summary once read
        # "names no host, device, binary or start time" of a record that does
        # record a device index and whose sampled command does name a binary
        # path -- understating a record in a summary is the same fault as
        # overstating it. Each such section states exactly what it holds.
        lines += ["Not attributable to any run: the "
                  + ", the ".join(unattributed)
                  + (" carries" if len(unattributed) == 1 else " carry")
                  + " no field that ties it to a run in this report, so "
                    "neither this provenance block nor any other can be shown "
                    "to describe it. Each such section states above exactly "
                    "what it does and does not record.", ""]
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
