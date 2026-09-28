# Issue #94 bounded next-movie prefetch — validation evidence

What this directory contains, and equally what it does not: **no timing, no GPU run and no
speedup.** The overlap this change makes possible has not been measured. #26 owns this round's
initial GPU benchmark slot, so the screening script here is prepared and unrun.

## Provenance

| item | value |
|---|---|
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (main after #90/#91) |
| Validated source | `189ed1fc8e720dc374fdafa063bc9c4f0b98b6c6` |
| Branch | `round96/94-claude-opus-5` |
| Host | `small-refmac-machine` (ssh alias `cpu64`), 2026-09-28T00:26:52Z |
| Build | GCC 13.3.0, CMake 4.4.3, `-DCMAKE_BUILD_TYPE=Release` → `CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp` |
| `motioncorr` sha256 | `904501fd09f20706562998a587ee97a7da5aa48640b6313728bf3cddc034159d` |
| `prefetch_lifecycle` sha256 | `7c4623461c28e3674d8c7e73bf8315110ffa9d9607258438746b9cc522f37a44` |

Per-file source and fixture hashes are in `cpu_validation_189ed1fc8e72.log`. The build type is
recorded because this project's `CMakeLists.txt` sets no default: an unqualified configure
produces `-O0` and inflates every host-side number.

### Files here

| file | what it is |
|---|---|
| `cpu_validation_189ed1fc8e72.log` | the run: topology, hashes, build, full `ctest` |
| `prefetch_equivalence_stdout_189ed1fc8e72.txt` | per-case output of `PrefetchEquivalence` |
| `prefetch_lifecycle_stdout_189ed1fc8e72.txt` | output of `PrefetchLifecycle` |
| `cli_contract_189ed1fc8e72.txt` | option documentation and validation exits |
| `thread_sanitizer/` | TSan run, plus the attempt that hit a loader flake |
| `cuda_syntax_check/` | parse-only check of the `_CUDA_ENABLED` branches, with stubs |
| `*_412f2f98be40.*` | superseded earlier run, retained; its CLI file carries an appended correction |

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
  able to land inside this lane, and other round workers' processes. Load averages are in the
  log.

None of that perturbs a correctness result, which is what was measured. It would matter for a
timing result, and no timing result is claimed here.

## What was checked

`ctest` full suite: **15/15 passed**. The 13 pre-existing tests are unchanged and still pass,
which is the regression evidence that the shared-loader refactor did not disturb the serial
path — *on the CPU path*. The same refactor also sits inside `executeOwnMotionCorrection` on
the CUDA path, which no test here compiles or runs; see `cuda_syntax_check/` for how far that
was taken.

### `PrefetchLifecycle`

Admission and lifecycle, no filesystem, no GPU: exact-fit / just-below / oversized budgets,
blocked-then-woken reserve, transfer-on-move, release-once and no-op second release,
cancellation while the producer waits for memory, while it waits for a queue slot and while the
consumer waits for data, producer error tagged to its movie, mixed geometry charged per movie,
format routing, and a stress check that `active + queued + producer-current` never exceeds the
limit.

Six assertions are **controls** — they establish that the case was genuinely exercised, because
a bound is trivially satisfied by a pipeline that never gets ahead, and "cancel returned" proves
nothing against a producer that had already exited. Every blocking case carries a watchdog, so
a deadlock fails the test rather than hanging the suite. The four `RelionError` reports in its
stdout are expected: one case deliberately probes absent files.

### `PrefetchEquivalence`

Serial vs prefetched, same movies, requiring identical corrected pixels, identical STAR
metadata and identical frame selection (full output in
`prefetch_equivalence_stdout_189ed1fc8e72.txt`):

```
normal:  4/4 movies identical; budget=466944 B, peak_reserved=466944 B, peak_queue=1
control: a changed option does change the pixels (the checks can fail)
mixed:   4/4 identical across differing geometry and frame counts (decoded=4, inline=0)
tight:   3/3 identical with a 9 MiB budget holding one movie (unit=8413184 B,
         peak_reserved=8413184 B)
starved: 3/3 identical with a 8 MiB budget, all via the counted in-line fallback
         (forced_grants=3)
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
  consumer-active were all charged **simultaneously**, so overlap really happened and the bound
  is not satisfied vacuously by a pipeline that never got ahead.
- `tight` and `starved` place a whole-MiB budget one MiB either side of a single movie's
  8413184 B estimate, which pins the estimate arithmetic itself: 9 MiB admits exactly one movie
  at a time, 8 MiB admits none.
- `frames` checks an **absolute** value, not merely that the two arms agree. Selected and
  original frame indices are different spaces, and exposures are written from the original one,
  so a record that lost it would produce correct pixels with wrong exposures — invisible to any
  pixel or header comparison, and both arms could be identically wrong. The per-movie STAR must
  record start frame 2.

## ThreadSanitizer

`thread_sanitizer/tsan_run.log`. A `-fsanitize=thread` build with `OMP_NUM_THREADS=1`
throughout: GCC's libgomp is not TSan-annotated, so OpenMP workers generate false positives
that would bury a real finding, and with one OpenMP thread the only concurrency left is exactly
what this PR adds — the producer running alongside the consumer.

- `PrefetchLifecycle`: exit 0, **0 warnings**.
- A real serial run and a real prefetched run over four synthetic MRCs and two TIFF fixtures,
  so the actual TIFF and MRC readers execute on the producer thread: both exit 0, **0 warnings
  each**, and all **6 corrected images byte-identical** between the arms, none empty.

`thread_sanitizer/tsan_attempt1_aslr_flake.log` is the first attempt, retained rather than
discarded: its serial arm died before `main()` with
`FATAL: ThreadSanitizer: unexpected memory mapping`, a TSan/ASLR interaction at load time —
the prefetch arm of the same binary started fine. Rerun under `setarch -R`.

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
  serial loader by design and are **unrun**, not "supported".
- Multi-worker (2/3/4 GPU process) schedules.
- Real host RSS at tutorial movie scale. `process_peak_rss_bytes` is printed by the run, but
  nothing here exercises it at a size where it would be informative.
- TSan with OpenMP decode threads (`OMP_NUM_THREADS > 1`), which needs a TSan-annotated OpenMP
  runtime to be readable.
