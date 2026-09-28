# WORKER_STATUS.md — Issue #97 round96/97-grok-4-3 (grok-4.3)

**Issue**: #97 Fix --interpolate_shifts recentering origin  
**Model**: mixed — grok-4.3 implementation (fix + planning), Opus 5 high review/fix (helper extraction, committed regression, cpu64 validation, corrections)  
**Task class**: correctness (scoped fix + CPU validation evidence)  
**Branch**: round96/97-grok-4-3 (isolated origin/main worktree)  
**Base commit**: 4c952b3f54479653512c4d208e09c9a8c02f3726 (main)  
**Phase**: CPU validation complete on cpu64. Unit regression committed and passing; default-off exactness proven on a real movie; option-on divergence quantified. Two read-only reviews requested. Draft PR #100 retained.
**Changed files**: `src/motioncorr_runner.cpp`, `src/motioncorr_runner.h`, `tests/test_runner_numerics.cpp`, `CMakeLists.txt`, `docs/issue97_cpu_evidence/*`, ADR, whitelist, this file.
**Blockers**: none blocking. The option-on path deliberately diverges from pinned RELION `ad0b230`; documented for the maintainer rather than gated on a second approval. GPU remains deferred to the #26 slot.
**NEEDS_GPU**: Yes, deferred — CUDA option-on path unverified. Request: one GPU slot to run the same 4-arm option-off/on comparison with `_CUDA_ENABLED`. Waiting on the #26 coordinated slot; no GPU submitted.
**Next step**: fold in the two read-only review verdicts, then hand to the maintainer. PR stays draft.

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
- No GPU submission until #26 slot.
- All per COMMON.md: WORKER_STATUS updates, progress comments, small commits, draft PR.

## Active PIDs / jobs
- None yet.

## Latest test commands / results
- `make -j8 motioncorr_core` (Release, forced fresh TU rebuild) — PASS, pre-existing warnings only.
- `/tmp/issue97_verify` — 4 witnesses against real `interpolateShifts`; W1 reproduces the archived control exactly; frame0==0 exact; relative displacements bit-exact. EXIT=0.
- `/tmp/issue97_control` — zero-origin control old==new bitwise (3 cases, 2 non-trivial); nonzero-origin control differs. EXIT=0.
- Upstream `ad0b230` fetched and diffed: defect inherited verbatim.
- NOT run: end-to-end movie, CUDA, RELION downstream. See ADR.

---
*Published at session start per task-97.md directive. Model kept as grok-4.3.*

## cpu64 validation summary (2026-09-28)

Full evidence: `docs/issue97_cpu_evidence/` (raw logs, script, comparator).

- Lane CPUs 40-55, verified node1/socket1-local, no SMT siblings; `membind=1`;
  `Cpus_allowed_list: 40-55` confirmed on a pinned child. Held constant across all arms.
- Serialized under `flock /tmp/motioncorr-issue96-cpu-validation.lock`.
- Interference recorded: `ctffind` ~100% on CPU 58 (node1, outside the cpuset).
  Host not idle. **No timing claim is made from these runs.**
- Two separate source trees (base `4c952b3`, fixed `792f1e6`), Release, `-j16`.
  Binaries: base `b27f7351...`, fixed `9fb0c0be...`.
- Unit: `RunnerInterpolateRecenter` passes on fixed, absent on base.
  Full suite 14/14 fixed, 13/13 base. Mutation test fails as required when reverted.
- Integration, default-off: output MRC pixel payload and per-movie STAR
  **byte-identical** between base and fixed, on both the synthetic fixture and the
  full-size real movie (56,955,920-byte payload).
- Integration, option-on: intentionally differs — 99.98% of pixels on the real movie
  (max abs 22.56 on range 51.42), 611/777 STAR value lines. Joint
  `corrected_micrographs.star` accumulated motion is **equal** in both arms.
- Not established: any scientific/downstream claim, timings, CUDA, >1 real movie.
