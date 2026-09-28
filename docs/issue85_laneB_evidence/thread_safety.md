# Lane B thread safety: what ThreadSanitizer does and does not establish

Source `1a0b789`. macOS 26.7, AppleClang, Homebrew LibTIFF 4.7.2, Homebrew
libomp (**not** built with `LIBOMP_TSAN_SUPPORT`, so no Archer).
Build: `-DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_CXX_FLAGS="-fsanitize=thread -g -O1"`.
Runs use `OMP_WAIT_POLICY=passive KMP_BLOCKTIME=0`, which makes some OpenMP
barriers visible to TSan (197 reports without it, 59 with).

## The limitation, stated first

Without a TSan-instrumented OpenMP runtime, TSan cannot see the implicit
barrier at the end of a parallel region. Anything a worker touches inside the
region and the main thread touches after it is reported as a race. **TSan
therefore cannot establish the absence of races here**, and a raw report count
is not a verdict.

What it can do is separate the two classes. A bug in this design — two workers
on one handle, one scratch, or one error context — is a **worker-versus-worker**
race. The barrier artifact is always **worker-versus-main**.

## Results

| run | total reports | worker-vs-worker |
|---|---:|---:|
| the pool, healthy and damaged fixtures | 59 | 0 |
| **negative control**: all workers forced onto `workers_[0]` | 12 | **4** |
| the pool again, damaged fixtures, different schedule | 87 | 1 (see below) |
| **baseline control**: shipping per-frame loop, damaged movie, no pool | 5 | 1 (same site) |

Locations in the 59-report run: 23 on a main-thread heap block, 20 on the main
thread's stack, the rest small main-thread allocations — all
`Location is ... of main thread`, i.e. the join barrier.

### The negative control matters

`0 worker-vs-worker` only means something if that class is observable. Forcing
every worker onto one handle (`Worker &w = *workers_[0];`) produces 4
worker-versus-worker races, so the check can see what it asserts.

### The one worker-vs-worker report is pre-existing

On a damaged movie, two workers can construct a `RelionError` at the same
time, and `RelionError::RelionError` writes a backtrace to `std::cerr`
unsynchronised (`src/error.cpp:66`). The race is on `std::ios_base::width`.

`tsan_baseline_control.cpp` runs the **shipping** per-frame read loop —
`#pragma omp parallel for` over `Image::read`, no pool — on a truncated movie,
against `origin/main` code. It reports the same race at the same site. This is
a property of `RelionError` under concurrent failure, present in main, not
introduced by lane B. It is out of scope here; fixing it would change the
observable error contract that `tests/test_damaged_movie.py` pins.

## Files

- `tsan_pool_healthy_and_damaged.log` — the pool, full parity matrix
- `tsan_negative_control_shared_handle.log` — all workers sharing one handle
- `tsan_baseline_control_shipping_loop.log` — shipping loop, damaged movie
- `tsan_baseline_control.cpp` — the baseline control program
