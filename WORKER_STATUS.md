# WORKER_STATUS — issue #95

| field | value |
| --- | --- |
| issue | #95 — Design and prototype bounded frame/chunk loading without retaining every host frame |
| model | `claude-opus-5` (high effort), routed as `claude-opus-5[1m]` |
| task class | architecture (ADR + one bounded component prototype) |
| phase | 5/5 — reviewed, review fixes applied and re-verified at final head |
| base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main) |
| head | see `git log`; 4 commits on top of base |
| branch | `round96/95-claude-opus-5` |
| worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-48564b12` |
| PR | [#104](https://github.com/KingAlejandro/MotionCorr-standalone/pull/104) (draft) |

## Declared changed-file whitelist

This task does **not** change the behaviour of any existing target. Runner
integration stays with #94 per the #66 execution plan. Precisely:
`src/frame_staging_plan.cpp` is compiled into `motioncorr_core` by the existing
glob and therefore linked into the `motioncorr` binary, but it has zero call
sites and no namespace-scope dynamic initialisers.

| path | status | kind |
| --- | --- | --- |
| `agents/designs/issue_95_bounded_frame_staging.md` | new | ADR |
| `src/frame_staging_plan.h` | new | component, not wired into the runner |
| `src/frame_staging_plan.cpp` | new | component, not wired into the runner |
| `tests/test_frame_staging.cpp` | new | CTest executable |
| `CMakeLists.txt` | edit | +5 (3 functional, 2 comment): register the test target. The source is picked up by the existing glob, so `motioncorr_core` gains an unreferenced object file with zero call sites. |
| `docs/issue95_staging_evidence/REPORT.md` | new | evidence |
| `docs/issue95_staging_evidence/raw/*` | new | raw unedited run logs |
| `WORKER_STATUS.md` | new | handoff |

Explicitly **not** touched: `src/motioncorr_runner.cpp`, `src/acc/cuda/*`,
`src/rwTIFF.h`, `src/image.h`, any existing test, any gate or tolerance.

## Tests

Final head, cpu64, CPU-only `Release` (`-O3 -DNDEBUG`), cmake 4.4.3, g++ 13.3.0.
Cores `48-55` (inside the required 32-63; 0-31 left free for #26), `--membind=1`,
`-j8` build and single-threaded test — both inside the ≤16 cap. Inherited cpuset
was `0-63` (no cgroup restriction); the effective in-process policy was captured
rather than asserted: `physcpubind: 48-55; cpubind: 1; membind: 1`. Serialised
with `flock /tmp/motioncorr-issue96-cpu-validation.lock`. Full provenance, hashes
and raw logs in `docs/issue95_staging_evidence/`.

| command | result |
| --- | --- |
| `cmake -S . -B build-cpu -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON` | exit 0 |
| `cmake --build build-cpu -j8` | exit 0 |
| `./build-cpu/frame_staging` | exit 0 — **256 checks, 0 failures** |
| `ctest --output-on-failure` | exit 0 — **14/14 passed** |
| mutation control, 4 bugs targeting the confirmed review findings | all 4 caught (exit 1); source hash restored |

**Earlier runs used `/tmp/motioncorr-issue96-cpu.lock`, which did not serialise
against the other workers in this round.** They are retained in
`docs/issue95_staging_evidence/raw/` as old-lock, non-timing evidence for a
source tree that no longer exists on this branch, and are **not** restamped with
the validation lock. No result from them is quoted for the final head. Nothing
in this task claims a timing, so no claim depends on exclusivity in either epoch.

Unrun, not passing: every CUDA-labelled test (CPU-only build), any pipeline run
of the staging idea (none exists), any memory measurement, any timing.

## Compute

- No job running. No allocation held. All jobs finished and released the lock.
- Read `WORKER_RESOURCE_UPDATE.md` (dropped into this worktree by Alex) and
  applied it: cpu64 is exclusively ours, the eight-core cap is superseded, runs
  are node-local. Observed topology: 2 NUMA nodes, node0 = cpu 0–31, node1 =
  cpu 32–63, ~115.8 GB each. All work bound to node1 with
  `numactl --cpunodebind=1 --membind=1`, `-j8`, under
  `flock /tmp/motioncorr-issue96-cpu.lock`. That file is left untracked: it is
  an instruction artifact, not a deliverable of this issue.
- Interference recorded and not altered: two foreign `ctffind` processes at
  ~100% CPU each (load avg 2.37 at 2026-09-27T23:47Z). No timing is claimed, so
  nothing reported here depends on them.
- **NEEDS_GPU: no.** The component prototype and its tests are CPU-only and do not
  need a device. The GPU-facing claims in the ADR are declared *calculated*, not
  measured, and are handed to #26 as a measurement request rather than run here.

## Result

**Partial no-go**, evidence-backed. ADR §8:

- **No-go** on bounded frame/chunk input staging as a peak-memory measure, on
  both paths. On the CPU path it is structural: input staging shrinks a phase
  that is not the high-water. On the GPU path it removes a real 1.273 GiB host
  mirror but leaves the device at `real + r2c`, needs a device-side repair
  gather and a changed fallback contract first, and does not touch the 40.0 GiB
  VRAM constraint that motivates the work.
- **Conditional go** on the compact `uint16` upload, pending #26 answering
  whether H2D is on the critical path. It halves H2D for one declared format
  with no residency change.
- **Go, delivered here**: the repair draw schedule, which converts "the RNG
  order forbids chunking" from an assumption into a tested fact.
- **Recommended next, not implemented here**: fuse `Irefframes` into one scratch
  frame. **Calculated** 1.273 GiB, 33% of the **calculated** CPU high-water;
  **argued bit-exact from the source but not built and not run**. It edits the
  shared runner, so it belongs to whoever holds the integration slot, and it
  needs its own test and 24-movie evidence before the claim is more than an
  argument.

## Independent review

Both reviews COMMON.md requires were obtained, read-only, at the pre-fix head.

| review | verdict | outcome |
| --- | --- | --- |
| code | `CHANGES_REQUESTED` | 2 high, 3 medium, 3 low. All fixed; see the fix commits. The reviewer independently re-derived and **confirmed** the central ordering claim and found the overflow arithmetic clean. |
| spec + licence | `SPEC_CONFORMANCE_PASSED` / `LICENCE_CLEAN` | 3 required follow-ups (undeclared spec gaps, unqualified "bit-exact", missing raw artefacts) — all three addressed. Scope isolation clean; all arithmetic verified exact. |

The two high-severity findings were real defects, both confirmed against the
source before fixing: the replacement buffer was transposed relative to all
three production consumers of `resident_bad_replacements`, and the gain multiply
at `motioncorr_runner.cpp:1752` was missing from both the component and the
test's transcription — so the test could not have caught it. Each now has a
mutation control proving the fix is covered, not just applied.

## Blockers

- None. Nothing here waits on another task.
- Coordination, not a blocker: ADR §9 asks #94 for two properties in the
  ownership interface (a movie record that can describe a partial frame range;
  reservations charged per live allocation). Both are already compatible with
  #94's corrected position.

## Next step

Draft PR opened for review. If #26 reports H2D is material, the compact-upload
prototype is the follow-up; otherwise the ADR's recommendation is `Irefframes`
fusion under someone else's integration slot.
