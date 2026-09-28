# WORKER_STATUS — issue #95

| field | value |
| --- | --- |
| issue | #95 — Design and prototype bounded frame/chunk loading without retaining every host frame |
| model | `claude-opus-5` (high effort), routed as `claude-opus-5[1m]` |
| task class | architecture (ADR + one bounded component prototype) |
| phase | 4/5 — ADR, component, tests and evidence committed; PR next |
| base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main) |
| head | see `git log`; 4 commits on top of base |
| branch | `round96/95-claude-opus-5` |
| worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-48564b12` |
| PR | opened as draft, URL below |

## Declared changed-file whitelist

This task does **not** modify the production pipeline. Runner integration stays
with #94 per the #66 execution plan.

| path | status | kind |
| --- | --- | --- |
| `agents/designs/issue_95_bounded_frame_staging.md` | new | ADR |
| `src/frame_staging_plan.h` | new | component, not wired into the runner |
| `src/frame_staging_plan.cpp` | new | component, not wired into the runner |
| `tests/test_frame_staging.cpp` | new | CTest executable |
| `CMakeLists.txt` | edit | 3 lines: register the new source + test |
| `docs/issue95_staging_evidence/REPORT.md` | new | evidence |
| `WORKER_STATUS.md` | new | handoff |

Explicitly **not** touched: `src/motioncorr_runner.cpp`, `src/acc/cuda/*`,
`src/rwTIFF.h`, `src/image.h`, any existing test, any gate or tolerance.

## Tests

All on cpu64, CPU-only `Release` build (`-O3 -DNDEBUG`), cmake 4.4.3,
g++ 13.3.0, `numactl --cpunodebind=1 --membind=1`, `-j8`, under
`flock /tmp/motioncorr-issue96-cpu.lock`. Full provenance and hashes in
`docs/issue95_staging_evidence/REPORT.md`.

| command | result |
| --- | --- |
| `cmake -S . -B build-cpu -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON` | exit 0 |
| `cmake --build build-cpu -j8` | exit 0 |
| `./build-cpu/frame_staging` | exit 0 — 235 checks, 0 failures |
| `ctest --output-on-failure` | exit 0 — 14/14 passed, 7.67 s |
| intentional-bug control, 3 injected bugs | all 3 caught (exit 1); source hash restored |

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
  frame. Calculated 1.273 GiB, 33% of the CPU high-water, bit-exact, no
  streaming. It edits the shared runner, so it belongs to whoever holds the
  integration slot.

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
