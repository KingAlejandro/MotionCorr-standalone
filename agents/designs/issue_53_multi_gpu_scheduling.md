# Architectural Design Specification: static multi-GPU whole-movie scheduling (#53)

- Issue: #53; related #26 (measurement), #66 (execution plan), #96 (audit index), #94/#95 (loading), #99 (completion publication).
- Base: current main `4c952b3f54479653512c4d208e09c9a8c02f3726`. **Not** the `feat/issue-50-cuda-end-to-end-residency` lineage the issue body and PR55 were written against.
- Branch: `round96/53-claude-opus-5`.
- Author: implementation agent (claude-opus-5, high effort), 28 Sep 2026.
- Authorization: Alex's round-96 assignment, per `COMMON.md`. Narrow scope only; no merges, no closures, no scope expansion.
- Status: **PR A proposed**. Independent read-only code/spec/license review required before the draft PR is called reviewable.

## 0. What this document is for

PR55 (`t3code/issue53-movie-scheduling` @ `377cb30`) is a four-file tooling prototype on an
obsolete CUDA lineage. The audit handoff
(`pr55#issuecomment` marker `mc-audit-verified-20260927-pr55`, and issue-53 marker
`mc-audit-verified-20260927-issue53`) directs: port the *concept* onto current main, do not
import obsolete CUDA history, and split the work so the static launcher refresh lands
before any coordinator source change.

This ADR covers **PR A only**. PR B (coordinator-owned gain/merge C++ flags) and PR C
(bounded dynamic assignment) are deliberately excluded and are not designed here.

## 1. Scope of PR A

In scope:

1. **Native device-list honesty (production, small).** `--gpu` with `--use_own` currently
   accepts `0:1:2:3` and silently uses device `0`. Reject multi-device syntax with a
   clear error, and correct the help text. Leave the external MotionCor2 path's semantics
   untouched.
2. **Static whole-movie process workers (tooling).** Refresh `tools/multi_gpu/` onto
   current main: STAR-faithful partitioning, preflight collision detection, one stock
   binary process per selected GPU with distinct output directories, per-device physical
   UUID witnesses, and full child-exit capture.
3. **Deterministic metadata merge (tooling).** One aggregate `corrected_micrographs.star`
   in canonical input row order, reconstructed from the worker outputs, with lost and
   duplicate output detection that fails closed.
4. **Cheap CPU fixtures.** A fake-worker harness exercising optics/exposure preservation,
   quoted paths, duplicate and lost outputs, empty shards, output-name collisions, a
   killed worker, and non-prefix resume — with no GPU and no tutorial dataset.

Explicitly out of scope for PR A:

- Any dynamic coordinator or work queue (PR C).
- `prepareGainReference(false)` in workers, worker-mode aggregate suppression, or a
  merge-only C++ mode (PR B).
- Any intra-movie multi-GPU split. Deferred, not declared impossible.
- Any change to a numerical result, tolerance, or gate.
- Any throughput claim. No benchmark matrix is run here; #26 owns the one shared matrix.

## 2. Corrections to the issue body, verified against current main

The #53 body was written against `306bc67` on the residency branch. Three of its
statements are stale at `4c952b3f`:

- **§6.1 `pre_exposure_micrographs` is never re-filtered — already fixed.** The filter loop
  now pushes `pre_exposure_micrographs` alongside `fn_micrographs`
  (`src/motioncorr_runner.cpp:403-405`) and `pre_exposure_ori_micrographs` alongside
  `fn_ori_micrographs` (`:410-412`). This is no longer a resume correctness bug.
- **§5 "Existence-only checks" / "asymmetric even/odd check" — already fixed.**
  `isMovieComplete()` (`:535`) validates MRC header geometry and file length via
  `completeMrc()` (`:516`) and requires `_EVN.mrc` **and** `_ODD.mrc` symmetrically
  (`:543`).
- The line numbers cited throughout §1/§5/§7 no longer resolve; this ADR re-cites.

Statements that remain true at `4c952b3f` and motivate PR A:

- `gpu_id` is a single scalar (`src/motioncorr_runner.h:200`), set once from
  `allThreadIDs[0][0]` (`src/motioncorr_runner.cpp:259`). `--gpu 0:1:2:3` silently runs
  everything on device 0.
- Help text still reads "Device ids for each MPI-thread, e.g 0:1:2:3"
  (`src/motioncorr_runner.cpp:122`) although this repository has no MPI.
- `untangleDeviceIDs(std::string&, ...)` destructively erases its argument
  (`src/args.cpp:431-445`), so after parsing, the member `gpu_ids` holds only the last
  entry.
- The serial movie loop and its process-global state (per-movie
  `init_random_generator`, the file-scope CUDA frame cache in
  `src/acc/cuda/cuda_fft_prep.cu`) still make **process** isolation the correct first
  design, as a hypothesis to measure rather than a guaranteed speedup.

## 3. Design decisions

### D1 — Shards preserve original row bytes; parsing is for semantics only

Metadata preservation is achieved by copying the original data-block header bytes and the
original data-row bytes verbatim into each shard. A STAR parser is used **only** to
identify rows, optics groups, and output-name collisions — never to re-serialize a row.

Rationale: re-serializing risks changing quoting, column spacing, or numeric formatting.
Verbatim bytes make "preserve optics/exposure metadata" a structural property, not a
property of a serializer's fidelity. A round-trip assertion (re-parse each shard; require
the parsed rows to equal the selected source rows) is what proves it.

The Python parser deliberately mirrors the C++ reader's observable semantics so the
identification agrees with what the binary will actually see:
`simplify()` (`src/strings.cpp:122`) unescapes and collapses whitespace runs on the whole
line **before** tokenization, and `nextTokenInSTAR()` (`src/strings.cpp:595`) supports
single/double quoted tokens with `\a` as the escape byte, treats a leading `#` as a
comment, and explicitly does **not** support semicolon multiline blocks. The parser
refuses any input using a construct the C++ reader would mis-handle rather than guessing.

### D2 — Contiguous partition, canonical order preserved within a shard

PR55 used round-robin. PR A uses **contiguous** blocks, matching `divide_equally`
semantics and the existing `prepare_chunks` in
`tools/run_all_24_tutorial_benchmark.py`. Row order within each shard is the canonical
input order. Load balancing is a PR C question and must be decided by measurement, not by
picking a distribution here and calling it better.

### D3 — Distinct worker output directories

Retained from PR55 and endorsed by the audit handoff. Every fixed-name aggregate hazard
(`corrected_micrographs.star` and its `.tmp`, `logfile.pdf`, `header.pdf`, `batch.pdf`,
the read-modify-write `all_batches.pdf`, `<pdf>.lst` scratch, the six
`corrected_micrographs_*.eps`, and `gain.mrc`) is avoided structurally with zero
production change. Sharing one output root requires PR B.

### D4 — Physical device identity, not ordinal

A worker's log records both the visible ordinal and the physical GPU UUID resolved
through the same `CUDA_VISIBLE_DEVICES` view the worker will see. Four workers that all
believe they are "device 0" cannot be presented as four devices. The launcher fails
closed if the selected ordinals do not resolve to distinct UUIDs.

### D5 — No fork of an initialized CUDA context

Workers are `exec`'d fresh. The launcher itself never initializes CUDA; UUID resolution
runs in a separate short-lived `nvidia-smi` query, not in-process.

### D6 — Merge is verification-first

The merge fails closed on: a movie with no output, a movie claimed by two workers, an
output file present under two workers, a worker that exited non-zero, and a shard that was
never assigned. Aggregate row order is the canonical input order, independent of
completion order. The merged `logfile.pdf` is **not** produced and **not** claimed
equivalent; per the issue's §6.3 it is path-dependent by construction and needs PR B.

## 4. Changed-file whitelist for PR A

Production:

- `src/motioncorr_runner.cpp` — device-list rejection and help text only.

Tooling:

- `tools/multi_gpu/star_io.py` (new)
- `tools/multi_gpu/partition_star.py` (rewritten)
- `tools/multi_gpu/merge_workers.py` (rewritten)
- `tools/multi_gpu/gpu_witness.py` (new)
- `tools/multi_gpu/run_multi_gpu.py` (new; replaces `run_multi_gpu.sh`)
- `tools/multi_gpu/compare24.py` (salvaged, retargeted)

Tests:

- `tests/test_multi_gpu_scheduling.py` (new)
- `tests/fake_worker.py` (new)
- `CMakeLists.txt` — one `add_test` registration

Docs/evidence:

- `agents/designs/issue_53_multi_gpu_scheduling.md` (this file)
- `docs/multi_gpu/` (evidence)
- `WORKER_STATUS.md`

Nothing else. Any file outside this list appearing in the PR diff is a scope violation.

## 5. Acceptance for PR A

PR A is reviewable when, and only when:

- The device-list rejection compiles and its behaviour is witnessed by a run, not asserted.
- All cheap CPU fixtures pass and each one is shown to fail when its guard is removed
  (negative controls), so no fixture is a check that cannot observe what it asserts.
- The changed-file diff equals the whitelist.
- Independent read-only code, spec-conformance and license review are recorded.

PR A makes **no** throughput, memory, or numerical claim. The all-24 native
serial-versus-sharded exact equality run and the per-device UUID/stage witnesses are
prepared as scripts and published as a `NEEDS_GPU` request; they are **unrun** until the
#26-coordinated slot is assigned, and are reported as unrun until then.
