# WORKER_STATUS.md — Issue #97 round96/97-grok-4-3 (grok-4.3)

**Issue**: #97 Fix --interpolate_shifts recentering origin  
**Model**: mixed — grok-4.3 implementation (fix + planning), Opus 5 high review/fix (helper extraction, committed regression, cpu64 validation, corrections)  
**Task class**: correctness (scoped fix + CPU validation evidence)  
**Branch**: round96/97-grok-4-3 (isolated origin/main worktree)  
**Base commit**: 4c952b3f54479653512c4d208e09c9a8c02f3726 (main)  
**Phase**: main merged in (`95c0cfb`); CPU re-validated against the new base `8323c55`; native CUDA A/B complete on 4GPUs. Draft PR #100 retained.
**Changed files**: `src/motioncorr_runner.cpp`, `src/motioncorr_runner.h`, `tests/test_runner_numerics.cpp`, `CMakeLists.txt`, `SOURCE_MANIFEST.txt`, `docs/issue97_cpu_evidence/*`, ADR, whitelist, this file.
**Blockers**: none blocking. The option-on path deliberately diverges from pinned RELION `ad0b230`; documented for the maintainer rather than gated on a second approval. GPU remains deferred to the coordinated shared-GPU slot, now owned by #53.
**NEEDS_GPU**: No — satisfied. Native CUDA A/B run on 4GPUs (see `docs/issue97_gpu_evidence/`): default-off byte-identical, option-on changed, CUDA patch path confirmed engaged. Correctness only; no timing, no benchmark slot consumed.
**Next step**: maintainer decision on the deliberate option-on divergence from pinned RELION `ad0b230` (fix as-is vs gate behind a separate flag). PR stays draft. GPU deferred; #53 owns the shared-GPU slot.

## Scoped plan (per issue-97.json + task-97.md + COMMON.md)
- Own ONLY the saved-first-frame-origin recentering fix.
- Read archived control/hash from issue-97.json, reproduce with deterministic nonzero first-frame offset on production path (not expression-only control).
- Verify exact simple relative displacement truth + justified float tolerance.
- Keep option-off CPU (and eventual CUDA) controls EXACT; option-on change explicit as bugfix.
- No peak-tie/noise/perf changes; check pinned RELION provenance.
- Tiny separate PR; independent review; bounded tests only.
- Preserve other tasks/worktrees; no merges; no scope creep.
- Record NUMA/CPU topology, actual Cpus_allowed_list etc. per COMMON addendum.
- Evidence: hashes, commands, outputs, intentional diff only on option-on.

## Evidence commitments
- Source hash of reproducer + actual MotionCorr build.
- CPU-only integration first.
- No GPU submission until the coordinated shared-GPU slot, now owned by #53 (previously #26).
- All per COMMON.md: WORKER_STATUS updates, progress comments, small commits, draft PR.

## Latest test commands / results

Superseded by "cpu64 validation summary" below, which is authoritative. The earlier
`/tmp/issue97_verify` and `/tmp/issue97_control` harnesses were deliberately not committed
and are replaced by the committed `RunnerInterpolateRecenter` regression; their results are
no longer cited anywhere. The one surviving item from that phase:

- Upstream `ad0b230` fetched and diffed: the defect is inherited verbatim. Recorded in
  `SOURCE_MANIFEST.txt` and in the ADR.

## Active PIDs / jobs
- None. The cpu64 validation job completed; its lock was released.

## cpu64 validation summary (2026-09-28)

Full evidence: `docs/issue97_cpu_evidence/` (raw logs, script, comparator).

- Lane CPUs 40-55, verified node1/socket1-local, no SMT siblings; `membind=1`;
  `Cpus_allowed_list: 40-55` confirmed on a pinned child. Held constant across all arms.
- Serialized under `flock /tmp/motioncorr-issue96-cpu-validation.lock`.
- Interference recorded: two `ctffind` at 99.9% on CPUs 32 and 33 (node1, outside the cpuset).
  Host not idle. **No timing claim is made from these runs.**
- Two separate source trees (base `4c952b3`, fixed `85dd1f9`), Release, `-j16`.
  Binaries: base `b27f7351...`, fixed `cd9a7316...`. HEAD differs from `85dd1f9` in docs
  only (re-verified at each subsequent commit), so the evidence describes the final
  production source.
- Unit: `RunnerInterpolateRecenter` passes on fixed, absent on base.
  Full suite 14/14 fixed, 13/13 base. Mutation test fails as required when reverted.
- Integration, default-off: output MRC pixel payload and per-movie STAR
  **byte-identical** between base and fixed, on both the synthetic fixture and the
  full-size real movie (56,955,920-byte payload).
- Integration, option-on: intentionally differs — 99.98% of pixels on the real movie
  (max abs 22.56 on range 51.42), 611/779 STAR lines (full-file denominator, corrected comparator). Joint `corrected_micrographs.star`
  accumulated motion is equal in both arms — **now measured** (`followup_measurements.log`)
  after review found the original comparator structurally could not see those values.
- Not established: any scientific/downstream claim, timings, CUDA, >1 real movie.

## Independent review (2026-09-28)

Two bounded read-only reviewers, run concurrently, no recursion.

Code/correctness reviewer: **CHANGES_REQUESTED**. Found no fault in `src/` — confirmed the
extracted method is semantically identical (the `size_t` bound provably equals `n_frames` at the
only call site), and independently recomputed all four witnesses from the source formula. It also
found corroboration I had missed: `motioncorr_runner.cpp:3122-3128` and
`acc/cuda/cuda_alignpatch.cu:393-398` already implement this same recentering as *descending*
loops with the comment `// do frame 0 last!`, so the intended semantics are unambiguous and the
ascending loop was the outlier.

Spec/license reviewer: **SPEC_CONFORMANCE_FAILED**, **LICENSE_COMPLIANCE_PASSED** (advisory).
Two of its findings were already resolved in `092b796` before it reported (whitelist amendment,
executed option-off control).

Applied from both:
- Added nonzero-origin-on-both-axes witnesses. This was the substantive one: every bug-exposing
  witness previously had `yshifts` all-zero, so the `origin_y` half of the fix was untested and a
  Y-only regression would have kept the suite green. Now mutation-proven per axis.
- Added negative X slope and unequal-last-group witnesses, and an empty-input case.
- Moved `RunnerInterpolateRecenter` out of the `if(Python3_Interpreter_FOUND)` block and switched
  to `$<TARGET_FILE:>`; it was a pure C++ test that would have silently vanished on a
  Python-less host.
- Reconciled the ADR, which still claimed at HEAD that no test was committed, and removed hashes
  pointing at a tree that no longer exists.
- Added the `Local change:` entry to `SOURCE_MANIFEST.txt` for the deliberate upstream divergence.
- Made `interpolateShifts` static and added a symmetric length guard to the now-public helper.

Not applied, with reasons:
- *Drop `WORKER_STATUS.md` / `issue97-whitelist.md` from the merge (no precedent at repo root).*
  Kept: COMMON.md mandates WORKER_STATUS for this round. Flagged for the maintainer to drop at
  merge if unwanted — they are process artifacts, not product.
- *`--first_frame_sum > 1` arm.* Not run; declared unrun in the ADR instead.

## Dual verification gate — final-source verdicts (2026-09-28)

AGENTS.md requires both `READY_TO_MERGE` and `SPEC_CONFORMANCE_PASSED`. A Codex bot review on
PR100 correctly objected that applying earlier findings is not a substitute for re-running the
audits, so both reviewers were resumed against the final source. **Two reviewers total, the same
two throughout; no third was created.**

| Audit | Verdict | Tree |
|---|---|---|
| Code / correctness | **READY_TO_MERGE** | `e8f1c562` |
| Spec conformance | **SPEC_CONFORMANCE_PASSED** | `97885ea` |
| License compliance | **LICENSE_COMPLIANCE_PASSED** | `97885ea` |

The code verdict was issued at `e8f1c562`. Everything committed since is documentation only;
the production-path diff over that range is empty, independently re-confirmed by the spec
reviewer at `97885ea`, which also verified the range from `85dd1f9` is docs-only so the cpu64
evidence still describes the production source at HEAD. The two non-blocking residuals the code
reviewer listed (stale `/tmp` harness citations in this file, the ADR's obsolete "1/3" tolerance
sentence) were fixed in `97885ea`.

### Verdict history, not overwritten

| Round | Tree | Code | Spec |
|---|---|---|---|
| 1 | `792f1e6` | CHANGES_REQUESTED | SPEC_CONFORMANCE_FAILED |
| 2 | `e8f1c562` | READY_TO_MERGE | SPEC_CONFORMANCE_FAILED |
| 3 | `97885ea` | (docs-only delta) | SPEC_CONFORMANCE_PASSED |

Round 2's spec failure was documentation fidelity only, with no defect in `src/`, `tests/` or
`CMakeLists.txt`. Its lead finding is worth keeping on the record: the evidence asserted the
joint-STAR accumulated motion was EQUAL while citing a comparator whose filter dropped the very
row those values live on. That was the third instance on this branch of a check that cannot
observe what it asserts. It was remedied by fixing the comparator and measuring the values, not
by softening the wording — and the reviewer then verified the remedy by a mechanism I had not
thought of: the comparison denominators moved 163 to 164 and 777 to 779, which are the full line
counts, proving no line is dropped any more.

### Still open, and not a conformance defect
Maintainer decision on the deliberate divergence from pinned RELION `ad0b230`, on the
experimental default-off `--interpolate_shifts` path only. Default-off is proven byte-identical.

## Post-merge re-validation and GPU (2026-09-28)

`origin/main` advanced `4c952b3` -> `8323c55` while this branch was open, so the earlier
byte-exactness evidence no longer described the current baseline. Merged main in (one
conflict, `CMakeLists.txt`, where main added `defect_parser` and a hard python+numpy gate at
the same line as this branch's test registration) and re-ran everything.

**CPU, cpu64, full machine (Alex authorised all 64 cores), new base `8323c55` vs `95c0cfb`:**
- Production delta between the two trees is exactly the issue-97 fix and nothing else.
- `RunnerInterpolateRecenter` passes on fixed, absent on base. Suite 19 vs 18 tests.
- `CiFailClosedControls` **fails on both trees**, i.e. it is pre-existing on main and not
  caused by this branch.
- Default-off: MRC payload and per-movie STAR byte-identical on synthetic and full-size real
  movie. Option-on differs as intended. `GATE: PASS`.
- The option-on difference figures are unchanged from the pre-merge run, so main's changes
  (incl. the #26 IFFT elision) did not perturb these outputs.
- Cross-NUMA placement used; acceptable because this is bit-exactness, not timing.

**GPU, 4GPUs, native CUDA:** see `docs/issue97_gpu_evidence/`. `GATE: PASS`.
Two build findings recorded there that are defects in main, not this PR: the project's
`CMAKE_CUDA_ARCHITECTURES` guard does not fire under CMake 3.28 + CUDA 12.8 (configure fails
with "CUDA_ARCHITECTURES is empty" unless `-DCMAKE_CUDA_ARCHITECTURES=80` is passed), and
`BUILD_TESTING=ON` is impossible on that host because main now hard-requires numpy.
