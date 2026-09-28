# WORKER_STATUS — issue #99, round 96

| Field | Value |
|---|---|
| Issue | #99 — fail-closed MRC image writes and completion |
| Model | `claude-opus-5` (high effort), Claude Code / T3 Code |
| Task class | correctness |
| Model routing | `claude-opus-5[1m]` as assigned; no routing error, no substitution |
| Phase | 6 — PR A reviewable; Codex PR105 review (`RLIMIT_FSIZE` hard limit) fixed, controlled and re-validated |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (current main) |
| Head | `33e2431` |
| Branch | `round96/99-claude-opus-5` (pushed) |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-a01709b1` |
| PR | https://github.com/KingAlejandro/MotionCorr-standalone/pull/105 (draft) |
| Progress comments | [plan](https://github.com/KingAlejandro/MotionCorr-standalone/issues/99#issuecomment-5860981003), [executed results](https://github.com/KingAlejandro/MotionCorr-standalone/issues/99#issuecomment-5861082448) |

## Scope delivered (PR A)

Reproduced, then propagated. Two defects, not one: `writeMRC` discarded every
`fwrite`/`fseek` result (and `_write` discarded `writeMRC`'s, so the existing `err < 0`
guard was dead on the MRC branches); and the only flush in the chain, `fclose` inside
`~fImageHandler`, reported by throwing from an implicitly `noexcept` destructor, i.e.
`std::terminate`. PR B (temporary paths, publication ordering, completion identity) is
designed and deliberately not started.

ADR and ownership trace: `agents/designs/issue_99_fail_closed_image_writes.md`.
Evidence: `docs/issue99_write_faults/REPORT.md`.

## Changed files (matches the ADR §6 whitelist)

- production: `src/rwMRC.h`, `src/image.h`, `src/micrograph_model.cpp`
- tests: `tests/test_image_write_faults.cpp`, `tests/test_write_faults.py`,
  `CMakeLists.txt` (one `add_executable`, two `add_test`)
- docs: `agents/designs/issue_99_fail_closed_image_writes.md`,
  `docs/issue99_write_faults/`, `WORKER_STATUS.md`

`src/motioncorr_runner.cpp` deliberately untouched — #91's per-movie failure contract
already provides what this needed to raise into, and #97/#98/#69 hold the other locks.

Diff vs base: 5 production/test files plus docs; `git diff --stat 4c952b3f..eda0350 -- src/`
is 3 files.

## Latest test commands and results

Host `small-refmac-machine` (cpu64), `taskset -c 32-63`, under
`flock /tmp/motioncorr-issue96-cpu-validation.lock`, Release `-O3 -DNDEBUG`, CUDA=OFF,
`--parallel 16`. Scripts as executed are committed at
`docs/issue99_write_faults/cpu_validation.sh` and `cpu_evidence.sh`.

| Run | Result |
|---|---|
| `ctest --output-on-failure -j 4`, candidate `f83a466` | **15/15 passed**, including the two new tests |
| `ctest -R 'ImageWriteFaults\|WriteFaults'`, negative control `dddc676` (pre-fix main + tests only) | **both fail**, exit 8 — one by assertion, one by `SIGABRT` from the destructor throw |
| Pre-fix end-to-end fault run | exit **0**, `b.mrc` truncated to 599040 B, `b.star` written, joint STAR and `logfile.pdf` published — the false completion, reproduced |
| Post-fix, same fault | exit **1** (status, not signal), names product/stage/movie, no `b.star`, healthy movie byte-identical, joint STAR withheld; repaired retry exit 0 |
| Healthy parity, pre- vs post-fix | `mov/p.mrc`, `mov/p.star`, `corrected_micrographs.star` byte-identical by whole-file SHA-256 |

Two files differ in the parity comparison and both are recorded rather than omitted: one
line of measured wall time in the per-movie `.log`, and the pre-existing ghostscript PDF
nondeterminism in `logfile.pdf`, which is preserved.

Binary hashes: candidate `motioncorr` `59936bbe…`, pre-fix `motioncorr` `b9d16a2d…`;
input `synthetic_movie.tiff` `95b5f0d3…`.

## Unrun / not claimed

- **Short header write as a distinct observation: unrun.** Measured, not assumed — with
  `st_blksize` 4096 a 1024-byte header never reaches `write(2)` inside its own `fwrite`, so
  even `RLIMIT_FSIZE=0` surfaces at the next flush point. Probe committed.
- **No crash-durability claim.** No `fsync` added.
- **No GPU run, no timing of any kind.**
- PR A leaves a truncated file on disk; safe today only via `completeMrc` resume
  validation, which the retry phase demonstrates.

## Bounded delta: inherited `RLIMIT_FSIZE` hard limit (Codex PR105 review)

[`discussion_r4119251206`](https://github.com/KingAlejandro/MotionCorr-standalone/pull/105#discussion_r4119251206)
at `910fcf43`. Both fault tests wrote `RLIM_INFINITY` as the **hard** limit. An
unprivileged process cannot raise a hard limit, so under the finite inherited hard
`RLIMIT_FSIZE` that CI and HPC systems set, the C++ suite died at `setrlimit` while
restoring and the Python `preexec_fn` failed in the forked child — MotionCorr never
`exec`'d. The harness dies before the fault is injected, which presents as "the fault did
not fire".

**Tests only; `1084269` changes no production source.** Both paths now read the inherited
`(soft, hard)`, lower only the soft limit, clamp the request to the hard limit, and restore
exactly what was inherited. Both also re-run the same injection under a hard limit they
lower themselves (unprivileged): the C++ suite forks and re-execs with `hard = 8 MiB`; the
Python test adds phase 4 driving MotionCorr through a `preexec_fn` that lowers the child's
hard limit, asserting on MotionCorr's own short-write text rather than an exit code, since
a failed spawn is also nonzero.

Both independent reviewers flagged the same blocking defect in the first revision, in the
exact environment class the delta exists for: the Python precheck demanded the literal
`FINITE_HARD_LIMIT`, so a host whose inherited hard limit was already finite but below
8 MiB failed with the self-contradicting *"the control did not actually get a finite hard
limit: 4194304"*. Fixed in `e96ba8c`, along with the C++ `(finite hard limit)` label being
env-derived rather than limit-derived, `execl` → `execlp`, `setenv` moved before the fork,
`waitpid` EINTR retry, the guard constant derived from `BIG_BYTES`, a matching Python
environment guard, and single-message regex matching of the writer's error. `57ba661`
makes phase 4 report the limit applied rather than the one requested.

| Run (cpu64, `taskset -c 32-63`, under the validation lock) | Result |
|---|---|
| Full CPU CTest, candidate `57ba661` | **15/15 passed** |
| Candidate, `ulimit -f 8192` → `(8388608, 8388608)` | **both pass**; phase 4 reached real MotionCorr |
| Candidate, `ulimit -f 4096` → `(4194304, 4194304)` | **both pass** — the mid-band case the reviewers flagged is not a spurious failure |
| Pre-delta tests on the **same fixed writer**, `ulimit -f 8192` (`fb2fab8`) | **exit 8** — `Exception occurred in preexec_fn.` and `setrlimit(RLIMIT_FSIZE) failed`, after phase 1 wrote a healthy product, so they die in the plumbing |
| Same pre-delta tests, **no** finite hard limit | **pass** — isolates the cause |
| Negative control, pre-fix main + new tests (`2101c3c`) | **exit 8, writer reason** — `a failed image write was treated as success`, `terminate called…` |
| Vacuity guard: stray `MC_WRITE_FAULTS_IN_CHILD`, no finite limit | **exit 1** — refuses to report a control that did not run |
| Healthy payload | `1a424122f6fd8f9b…`, 1 049 600 bytes — unchanged |

Payload-level provenance recorded: cpuset witnessed inside the build under `taskset` as
`Cpus_allowed_list: 32-63`, `Mems_allowed_list: 0-1`; two-node NUMA (node 0 = cpus 0-31,
115 839 MB; node 1 = cpus 32-63); `numactl --show` → `policy: default`, `cpubind: 1`; load
6.75 → 9.81 on the shared host; binary and input hashes. No GPU, no timing.

**The first attempt at the external control was void and is recorded as such.**
`ulimit -H -f N` fails with `EINVAL` — bash sets only the hard limit and leaves the soft
limit at infinity — so no limit was applied and *both* arms passed, which reads exactly
like "the delta was unnecessary". `ulimit -f N` sets both.

Integration mapping for PR110: `docs/issue99_write_faults/PR110_COMMIT_MAP.md`. Three
tests-only commits (`1084269`, `e96ba8c`, `57ba661`), same two files; all three replayed
onto a detached `refs/pull/110/head` and the resulting blobs are identical to this
branch's head. **PR110's tree was not modified and nothing was pushed there.**

## Independent review (COMMON.md requirement), both read-only

Two bounded read-only reviewers, run concurrently, neither able to modify anything.

**Code/correctness review.** Clean on leaks, double-frees, double-close, success-path and
read-path behaviour, `errno` handling, and — checked by brace nesting over all thirteen
`write(` sites in `src/` — on throws inside OpenMP structured blocks. Applied its
findings in `b0e10f5`: `strerror`'s static buffer replaced with
`std::generic_category().message()` (the only new shared state); the sticky `ferror`
check dropped from `mrcWriteBlock`; the handler-reuse close taught to name its file; the
reuse guard extended to `ftiff` (a pre-existing fd leak the rewritten `releaseHandles`
would otherwise have fixed); the per-slice label made lazy. Declined one: `writeIMAGIC`'s
unchecked return, because that function is a stub that unconditionally throws.

**Spec-conformance and license review.** `SPEC_CONFORMANCE_PASSED`, `LICENSE_PASSED`
(GPL-2.0, no vendored code, no new dependency, POSIX libc only). All eight changed files
inside the ADR §6 whitelist, nothing outside it, no CUDA/gate/default/perf change. Found
that the destructor test case was vacuous — fixed in `f83a466`, and fixing it exposed a
second fault the review had not seen: the paired form used a post-fix API, so the
negative control silently degraded to `Not Run` rather than failing. Both are now
corrected and the control demonstrably compiles and runs on the pre-fix tree.
It also corrected the ADR's claim that `micrograph_model.cpp` is collision-free with
respect to #98 (#98's defect-text detection lives in the same file, ~50 lines away).

## Observation for #66/#69, not fixed here

`src/motioncorr_runner.cpp:3207` — `REPORT_ERROR("Shouldn't happen.")` sits inside the
`#pragma omp parallel for` opened at `:3183`. An exception leaving an OpenMP structured
block is undefined behaviour and calls `std::terminate`, the same class of defect #91
fixed for the frame-read region. Pre-existing and untouched by this branch; that file is
out of this issue's whitelist and is held by sibling tasks.

## Active jobs / allocations

None. All cpu64 jobs completed; the validation lock is released.

## Blockers

None.

## NEEDS_GPU

**Not required.** Every fault is injected at the host stdio layer and is
backend-independent; the CUDA path reaches the same `Image::write`. No CUDA arithmetic,
gate or output default is touched, so the #90/#91 same-backend evidence still stands
unchanged and was not re-run. #26 owns this round's GPU slot.

## Next step

Hand the draft PR to integration for a maintainer decision. Do not merge, do not close.
PR B stays designed-and-unstarted in ADR §7. Existing limitations preserved: the
ghostscript PDF nondeterminism and the measured-unreachable MRC header-write injection.
