# Issue #94 bounded next-movie prefetch — CPU validation evidence

What this directory contains, and equally what it does not: **no timing, no GPU run and no
speedup.** The overlap this change makes possible has not been measured. #26 owns this round's
initial GPU benchmark slot, so the screening script here is prepared and unrun.

## Provenance

| item | value |
|---|---|
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (main after #90/#91) |
| Validated source | `412f2f98be401760aa2b336deaba3aa348cfafd7` |
| Branch | `round96/94-claude-opus-5` |
| Host | `cpu64` / `small-refmac-machine`, 2026-09-28T00:11:48Z |
| Build | GCC 13.3.0, CMake 4.4.3, `-DCMAKE_BUILD_TYPE=Release` → `CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp` |
| `motioncorr` sha256 | `b8f2907d92862f48c971ff63f226434f0efff2c841324fc6394ce40e17b3df52` |
| `prefetch_lifecycle` sha256 | `64eb92d3e753e9feadf29daf03af864a5d44ed7109558fbf1a120e9a5a08bf42` |
| Fixture `synthetic_movie.tiff` sha256 | `95b5f0d37d481355b8abe30f7380c33d9ea173a87bec6e8fc3e567c057622bd4` |

Per-file source hashes are in `cpu_validation_412f2f98be40.log`. The build type is recorded
because this project's `CMakeLists.txt` sets no default: an unqualified configure produces
`-O0` and inflates every host-side number.

## Placement, and the interference that was present

Lane `32-47`, taken with a **top-level** `taskset` so every descendant inherits it, under
`flock /tmp/motioncorr-issue96-cpu-validation.lock` (the round's shared validation lock;
#26 measures separately on `0-31`). Build `-j16`, runtime `<= 16`.

- Inherited `Cpus_allowed_list`: `32-47` — verified from `/proc/self/status` inside the lane,
  not assumed from the mask.
- `numactl --show`: `cpubind: 1; nodebind: 1; membind: 0 1`. CPUs are node-local to node 1;
  **memory is not pinned**, so this is a node-local *CPU* lane and nothing here claims NUMA
  memory locality.
- `lscpu -p` shows CPUs 32-47 map to 16 **distinct** physical cores on socket 1 — no SMT
  sibling pairs inside the lane.
- Interference present throughout and deliberately not altered: two long-running `ctffind`
  processes at ~100% CPU each (49 and 47 days old) with `Cpus_allowed_list=0-63`, i.e.
  unrestricted and therefore able to land inside this lane; and another round worker's
  `motioncorr` at 100% on CPU 3 (node 0). Load average 5.42 at start, 6.57 at end.

None of this perturbs a correctness result, which is what was measured. It would matter for a
timing result, and no timing result is claimed here.

## What was checked

`ctest` full suite: **15/15 passed**, 19.84 s total. The 13 pre-existing tests are unchanged
and still pass, which is the regression evidence that the shared loader refactor did not
disturb the serial path. The two new ones:

- **`PrefetchLifecycle`** (5.43 s) — admission and lifecycle, no filesystem, no GPU. Exact-fit,
  just-below and oversized budgets; blocked-then-woken reserve; transfer-on-move; release-once
  and no-op second release; cancellation while the producer waits for memory, while it waits
  for a queue slot, and while the consumer waits for data; producer error tagged to its movie;
  mixed geometry charged per movie; format routing; and an accounting stress check asserting
  `active + queued + producer-current` never exceeds the limit. Two assertions are controls
  that the case was genuinely exercised, because a bound is trivially satisfied by a pipeline
  that never gets ahead. Every blocking case carries a watchdog, so a deadlock fails the test
  rather than hanging the suite.
- **`PrefetchEquivalence`** (7.31 s) — serial vs prefetched, same movies, requiring identical
  corrected pixels, identical STAR metadata and identical frame selection:

  ```
  normal:  4/4 movies identical; budget=466944 B, peak_reserved=466944 B, peak_queue=1
  control: a changed option does change the pixels (the checks can fail)
  mixed:   4/4 identical across differing geometry and frame counts (decoded=4, inline=0)
  tight:   3/3 identical with a 9 MiB budget holding one movie (unit=8413184 B,
           peak_reserved=8413184 B)
  starved: 3/3 identical with an 8 MiB budget, all via the counted in-line fallback
           (forced_grants=3)
  gain:    4/4 identical with a gain reference applied
  frames:  4/4 identical with --first_frame_sum 2 --last_frame_sum 7
  damaged-first: exit 1 matches serial, both healthy movies retained and identical
  damaged-last:  exit 1 matches serial, both healthy movies retained and identical
  resume:  non-prefix resume identical, full 4/4 coverage, 3 movies prefetched
  ```

  Two numbers there are load-bearing. `peak_reserved == budget == 466944 B` in the normal case
  is `3 x` the documented per-movie estimate, recomputed independently in the test from the ADR
  formula: producer-current, queued and consumer-active were all charged simultaneously, so
  overlap really happened and the bound is not vacuous. And the `tight`/`starved` pair places a
  whole-MiB budget one MiB either side of a single movie's 8413184 B estimate, which pins the
  estimate arithmetic itself: 9 MiB admits exactly one movie at a time, 8 MiB admits none.

`cli_contract_412f2f98be40.txt` records that the three options are documented in the usage text
and that `--prefetch` without `--use_own`, a negative `--prefetch_mem_mb` and a zero
`--prefetch_queue` each exit 1 with a specific message.

## Two artifacts in the log that are not failures

- `bash: line 2: SRC: unbound variable` / `(probe rc=1)` near the lock section is a leftover
  no-op probe in the driver script, before the real work. The lock was acquired and the
  subsequent series ran with `rc=0`.
- `prefetch options in --help: 0` is a bad probe, not a missing option: the usage text is only
  emitted for `--use_own --help`. `cli_contract_412f2f98be40.txt` shows all three options
  present.

## The one CUDA-side check that was possible without a slot

`cuda_syntax_check/` holds a `-fsyntax-only` parse of both changed translation units with
`-D_CUDA_ENABLED`, against minimal stub runtime/cuFFT/cuRAND headers (the project's own
`src/acc/cuda/*.h` are the real ones). Both exit 0, and a deliberately broken copy produces an
error, so the harness really does reach the CUDA-only branches. This matters because a
CPU-only `ctest` run cannot see a broken `#ifdef _CUDA_ENABLED` branch, and the `Iframes`
alias and relocated read path sit right next to that code. **It is not a CUDA build**: no
`.cu` compilation, no link, no execution.

## Explicitly unrun

- Anything on a GPU. No real CUDA toolkit build, no CUDA test, no timing, no overlap
  measurement, no same-backend comparison on the 24 tutorial movies.
  `scripts/prefetch_gpu_screen.sh` refuses to start without an assigned slot.
- EER and compressed-MRC inputs through the prefetch path. They are routed to the in-line
  serial loader by design and are **unrun**, not "supported".
- Multi-worker (2/3/4 GPU process) schedules.
- Real host RSS under a tutorial-scale movie. `process_peak_rss_bytes` is printed by the run,
  but nothing here exercises it at a size where it would be informative.
