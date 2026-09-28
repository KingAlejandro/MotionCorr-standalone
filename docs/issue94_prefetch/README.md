# Issue #94 bounded next-movie prefetch — validation evidence

What this directory contains, and equally what it does not: **no timing, no GPU run and no
speedup.** The overlap this change makes possible has not been measured. #26 owns this round's
initial GPU benchmark slot, so the screening script is prepared and unrun.

## Provenance

| item | value |
|---|---|
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (main after #90/#91) |
| Validated source | `08c87bb653a3970639dd0699eaa479eb2fc795a9` (Codex review fixes) |
| Branch | `round96/94-claude-opus-5` |
| Host | `small-refmac-machine` (ssh alias `cpu64`), 2026-09-28T00:33Z |
| Build | GCC 13.3.0, CMake 4.4.3, `-DCMAKE_BUILD_TYPE=Release` → `CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp` |
| `motioncorr` sha256 | `c28c023a3b826c5312b5f1e10be09d6e043d32d8a0c5fe41dde8d79b3be05782` |
| `prefetch_lifecycle` sha256 | `a2d8c8315ae7fd0a756698cbccc7af016a353272b63ee122ff38bfc60be0f702` |

Per-file source and fixture hashes are in `cpu_validation_08c87bb653a3.log`. The build type is
recorded because this project's `CMakeLists.txt` sets no default: an unqualified configure
produces `-O0` and inflates every host-side number.

| file | what it is |
|---|---|
| `cpu_validation_08c87bb653a3.log` | current head: topology, hashes, build, full `ctest` |
| `prefetch_equivalence_stdout_08c87bb653a3.txt` | per-case output of `PrefetchEquivalence` |
| `prefetch_lifecycle_stdout_08c87bb653a3.txt` | output of `PrefetchLifecycle` |
| `negative_controls_08c87bb653a3.log` | each Codex fix reverted in turn; the test must fail |
| `cpu_validation_eb022aff151c.log` | previous head, retained: it carries the ThreadSanitizer run |
| `tsan_*_eb022aff151c.txt` | stdout of the three sanitizer runs |
| `cli_contract_eb022aff151c.txt` | option documentation and validation exit codes |
| `cuda_syntax_check/` | parse-only check of the `_CUDA_ENABLED` branches, with stubs |
| `superseded/` | earlier heads' runs, retained; see its README for why |

## Placement, and the interference that was present

Lane `32-47`, taken with a **top-level** `taskset` so every descendant inherits it, under
`flock /tmp/motioncorr-issue96-cpu-validation.lock` (the round's shared validation lock; #26
measures separately on `0-31`). Build `-j16`, runtime `<= 16`.

- Inherited `Cpus_allowed_list`: `32-47` — read from `/proc/self/status` inside the lane, not
  assumed from the mask.
- `lscpu -p` shows those 16 logical CPUs map to **16 distinct physical cores** on socket 1 — no
  SMT sibling pairs inside the lane.
- `numactl --show`: `cpubind: 1, nodebind: 1, membind: 0 1`. CPUs are node-local to node 1;
  **memory is not pinned**, so this is a node-local *CPU* lane and nothing here claims NUMA
  memory locality.
- Interference present throughout and deliberately not altered: two long-running `ctffind`
  processes at ~100% CPU each with `Cpus_allowed_list=0-63`, i.e. unrestricted and therefore
  able to land inside this lane, plus other round workers. Load averages are in the log.

None of that perturbs a correctness result, which is what was measured. It would matter for a
timing result, and no timing result is claimed here.

## What was checked

`ctest` full suite: **15/15 passed**. The 13 pre-existing tests are unchanged and still pass,
which is the regression evidence that the shared-loader refactor did not disturb the serial
path — *on the CPU path*. The same refactor also sits inside `executeOwnMotionCorrection` on
the CUDA path, which no test here compiles or runs; see `cuda_syntax_check/` for how far that
was taken.

### `PrefetchLifecycle`

Admission and lifecycle, no filesystem, no GPU: record destruction order, degenerate geometry,
both sides of override counting, exact-fit / just-below / oversized budgets,
blocked-then-woken reserve, transfer-on-move, release-once and no-op second release,
cancellation while the producer waits for memory, while it waits for a queue slot and while
the consumer waits for data, producer error tagged to its movie, mixed geometry charged per
movie, format routing, and a stress check that `active + queued + producer-current` never
exceeds the limit.

Several assertions are explicit **controls** — they establish that the case was genuinely
exercised, because a bound is trivially satisfied by a pipeline that never gets ahead, and
"cancel returned" proves nothing against a producer that had already exited. Every blocking
case carries a watchdog, so a deadlock fails the test rather than hanging the suite. The four
`RelionError` reports in its stdout are expected: one case deliberately probes absent files.

### `PrefetchEquivalence`

Serial vs prefetched, same movies, requiring identical corrected pixels, identical STAR
metadata and identical frame selection:

```
normal:  4/4 movies identical; budget=466944 B, peak_reserved=466944 B, peak_queue=1
control: a changed option does change the pixels (the checks can fail)
mixed:   4/4 identical across differing geometry and frame counts (decoded=4, inline=0)
queue2:  4/4 identical, automatic budget still 466944 B, peak_reserved=466944 B
queue8:  4/4 identical, automatic budget still 466944 B, peak_reserved=466944 B
tight:   3/3 identical with a 9 MiB budget holding one movie (unit=8413184 B,
         peak_reserved=8413184 B)
starved: 3/3 identical with a 8 MiB budget, all via the counted in-line fallback
         (over_budget_grants=3)
gain:    4/4 identical with a gain reference applied, all 4 prefetched
frames:  4/4 identical with --first_frame_sum 2 --last_frame_sum 7, all 4 prefetched,
         start frame recorded as 2
damaged-first: exit 1 matches serial, both healthy movies retained and identical
damaged-last: exit 1 matches serial, both healthy movies retained and identical
resume:  non-prefix resume identical, full 4/4 coverage, 3 movies prefetched
```

Three of those lines carry weight rather than decorate:

- `peak_reserved == budget == 466944 B` in `normal` is exactly `3 x` the per-movie estimate,
  recomputed independently in the test from the ADR formula. Producer-current, queued and
  consumer-active were all charged **simultaneously**, so overlap really happened and the
  bound is not satisfied vacuously by a pipeline that never got ahead.
- `tight` and `starved` place a whole-MiB budget one MiB either side of a single movie's
  8413184 B estimate, which pins the estimate arithmetic itself: 9 MiB admits exactly one
  movie at a time, 8 MiB admits none.
- `frames` checks an **absolute** value, not merely that the two arms agree. Selected and
  original frame indices are different spaces, and exposures are written from the original
  one, so a record that lost it would produce correct pixels with wrong exposures — invisible
  to any pixel or header comparison, and both arms could be identically wrong. The per-movie
  STAR must record start frame 2. (Index-space trap traced by the #95 agent.)

Four cases — `gain`, `frames` and both damaged ones — additionally assert the decoded and
failed counts, because without that they would all have passed unchanged had prefetch silently
degraded to loading every movie in line.

## Negative controls for the three Codex review fixes

A control that passes whether or not the defect is present is not evidence. Each fix was
therefore **reverted in turn**, in a fresh copy of the tree with a fresh build directory (a
copied CMake build dir caches the original absolute source path and would silently rebuild the
unmutated sources), and the suite re-run. Every revert must fail.
`negative_controls_08c87bb653a3.log`:

| reverted fix | `prefetch_lifecycle` | failures |
|---|---|---|
| positive format whitelist → old negative check | exit 1 | **11** — `spi`, `stk`, `xmp`, `vol`, `img`, `hed`, `st`, `map`, `dm4`, no-extension and raw all wrongly admitted to the producer |
| automatic budget → `queue_capacity + 2` estimates | exit 1 | **8** — capacities 2, 3, 8 and 64 each give a different ceiling where the CLI promises `3 x` |
| explicit move assignment → `= default` | exit 1 | **2** — old frames still live when their bytes were returned, *and* self-move destroys the frames |

The third revert surfaced something the review did not mention: a defaulted move assignment is
also **not self-move safe** here, so `record = std::move(record)` loses the frames. The
explicit operator returns early on self-assignment.

## ThreadSanitizer

Run at the previous head `eb022aff`, whose `src/` differs from the current head only by the
three review fixes above; **not** re-run at `08c87bb6`. `-fsanitize=thread`,
`OMP_NUM_THREADS=1` throughout: GCC's libgomp is not TSan-annotated, so
OpenMP workers generate false positives that would bury a real finding, and with one OpenMP
thread the only concurrency left is exactly what this PR adds — the producer running alongside
the consumer.

- `PrefetchLifecycle`: exit 0, **0 warnings**.
- A real serial run and a real prefetched run over four synthetic MRCs and two TIFF fixtures,
  so the actual TIFF and MRC readers execute on the producer thread: both exit 0, **0 warnings
  each**, all **6 corrected images byte-identical** between the arms, none empty.

The prefetched run's own accounting from that pass is in the log: `decoded = 4`,
`inline_loaded = 2`, `over_budget_grants = 2` (the two TIFF fixtures exceed the 430080 B
automatic budget derived from the small synthetic movies, so they take the counted in-line
fallback), and `peak_reserved_bytes = 9469952` above the limit — which is what an override is
supposed to look like: visible, not hidden.

## The one CUDA-side check possible without a slot

`cuda_syntax_check/` holds a `-fsyntax-only` parse of both changed translation units with
`-D_CUDA_ENABLED`, against minimal stub runtime/cuFFT/cuRAND headers (the project's own
`src/acc/cuda/*.h` are the real ones). Both exit 0, and a deliberately broken copy produces an
error, so the harness really does reach the CUDA-only branches. **It is not a CUDA build**: no
`.cu` compilation, no link, no execution.

## Explicitly unrun

- Anything on a GPU. No real CUDA toolkit build, no CUDA test, no timing, no overlap
  measurement, no same-backend comparison on the 24 tutorial movies.
  `scripts/prefetch_gpu_screen.sh` refuses to start without an assigned slot.
- EER and compressed-MRC inputs through the prefetch path. They are routed to the in-line
  serial loader by design and are **unrun**, not "supported". The mixed EER/TIFF case that
  motivated pre-setting libtiff's warning handler is likewise unrun for lack of an EER fixture.
- Multi-worker (2/3/4 GPU process) schedules.
- Real host RSS at tutorial movie scale. `process_peak_rss_bytes` is printed by the run, but
  nothing here exercises it at a size where it would be informative.
- TSan with OpenMP decode threads (`OMP_NUM_THREADS > 1`), which needs a TSan-annotated OpenMP
  runtime to be readable.
- ThreadSanitizer **at the current head**. It was run at `eb022aff`; the three review fixes
  since then change admission, a constant and a move assignment, none of which adds
  synchronisation, but that is an argument, not a measurement.
- An end-to-end unsupported-format case. The whitelist control is unit-level because the
  repository has no SPIDER or IMAGIC movie fixture, and inventing one that the inline path
  then fails to decode would test nothing useful.
