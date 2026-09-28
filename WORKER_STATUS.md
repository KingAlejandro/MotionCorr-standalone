# WORKER_STATUS — issue #95

| field | value |
| --- | --- |
| issue | #95 — Design and prototype bounded frame/chunk loading without retaining every host frame |
| model | `claude-opus-5` (high effort), routed as `claude-opus-5[1m]` |
| task class | architecture (ADR + one bounded component prototype) |
| phase | 5/5 — three review rounds plus a Codex capacity-accounting correction, re-verified at final head |
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
| `./build-cpu/frame_staging` | exit 0 — **283 checks, 0 failures** |
| `ctest --output-on-failure` | exit 0 — **14/14 passed** |
| old-model control, 3 mutants reverting each Codex fix | all 3 caught (exit 1), 6/6/4 failures; baseline and restore both 283/0; hashes restored |

Counts across rounds are **235 → 256 → 248 → 283 and are not comparable**:
assertions were replaced as well as added. The drop to 248 was the second
review finding four assertions that could not fail; they were replaced, not
supplemented. Do not read the sequence as growing coverage.

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

Two direct reviewers total, as required. The code reviewer was **resumed**, not
replaced, for the second pass, so no third reviewer was spawned.

| review | head | verdict | outcome |
| --- | --- | --- | --- |
| code, pass 1 | `1292439` | `CHANGES_REQUESTED` | 2 high, 3 medium, 3 low. All fixed. Independently re-derived and **confirmed** the central ordering claim; found the overflow arithmetic clean. |
| spec + licence | `1292439` | `SPEC_CONFORMANCE_PASSED` / `LICENCE_CLEAN` | 3 required follow-ups — all addressed. Scope isolation clean; all arithmetic verified exact. |
| code, pass 2 | `90a50c9` | `CHANGES_REQUESTED` | First independent review of `largestChunkWithin`, which was added after pass 1. Found it **correct** — monotonicity verified term by term, search sound, overflow-safe midpoint, `out_chunk` contract holds. Four items fixed (A, D, E, F); B, C, G, H, I, J carried as documented notes. |
| code, pass 3 | **`d2b75e0`** | **`READY_TO_MERGE`** | Bounded confirmation of the A/D/E/F fixes. All four confirmed correct and complete, no new defect in the delta. Independently re-derived the in-loop "overflow, not malformed" argument and the `out_error`/`out_chunk` contracts, and verified the mutation log's four source hashes against the tree rather than taking the claim. Two accepted limitations recorded, neither blocking. |

| code, pass 4 | `d3a1632` | in flight | bounded review of the Codex capacity-accounting delta |
| spec, pass 2 | `d3a1632` | in flight | bounded audit of the corrected accounting and supersession discipline |

Both existing reviewers were **resumed**, never replaced. **Two direct
reviewers total** across the whole task; no third agent was ever spawned.

`READY_TO_MERGE` is the reviewer's assessment of fitness to hand off. It is
**not** a recommendation to merge: this PR stays a draft, the decision stays a
partial no-go, and nothing here is promoted.

Pass 1's two high-severity findings were real defects: the replacement buffer
was transposed relative to all three production consumers of
`resident_bad_replacements`, and the gain multiply at
`motioncorr_runner.cpp:1752` was missing from the component **and** from the
test's transcription — so the test could not have caught it.

Pass 2's most useful findings were not about shipped logic but about the test
surface: four assertions that could not fail, two of them labelled as checking
the primary value property. It also found that `largestChunkWithin` reported a
malformed policy as an inadmissible movie — the same collapse of distinct
outcomes into one signal that the ADR argues against, reproduced inside the
function written to prevent it. It now returns a tri-state `Admission`.

Every fix in both passes has a mutation control proving it is covered, not just
applied.

## Codex review of `dba0891e`

Two P2 capacity-accounting defects, both confirmed against the source, both
fixed in `2bd1da8` / `5a553ab`:

1. The repair schedule — `n_bad × n_frames` `Draw` objects plus three `n_bad`
   int arrays — was a host allocation the component makes and its own budget
   omitted. Dense mask: admitted as `O(C·W·H)`, allocates `O(F·W·H)`.
2. The no-staging policy double-counted `Iframes`. The runner decodes straight
   into `Iframes`, so the staged and resident terms are one allocation.

Neither changes the decision. Both make the calculator honest about costs that
push the same way — and the fix exposes a new one: `n_bad` is unknowable at
admission, so a staged design must charge a worst case of `W·H` or re-check
after detection and be ready to fail an already-admitted movie.

Recorded in ADR §7a.4, including why they were not caught here: the double
count contradicted the ADR's own §4.1 phase table, gave the right number for
the wrong reason, and **an existing test asserted it as correct**.

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
