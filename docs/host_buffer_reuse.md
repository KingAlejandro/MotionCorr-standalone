# Reuse full-frame host buffers across movies

## Finding

`--profile` on the 24-movie tutorial (4GPUs, GPU0, `--j 8`, nvCOMP ingest,
main `af64101`) attributed 21% of the steady per-movie wall to two stages with
no device work at all:

| stage | median ms/movie | main-thread CPU | minor faults/movie |
|---|---|---|---|
| allocate host sum | 49.1 | 100% | 13,906 |
| allocate reconstruction | 43.3 | 100% | 13,908 |

Each one is a single 3838×3710 float buffer (56.96 MB = 13,906 pages)
allocated and zeroed once per movie. glibc serves allocations above its mmap
threshold from a fresh anonymous mapping and unmaps them on free. The dynamic
threshold stops adapting at 32 MiB (`DEFAULT_MMAP_THRESHOLD_MAX`), so a 57 MB
buffer is never reused. Every movie pays a kernel fault plus a page clear for
each 4 KiB, serially, on the main thread, while the GPU is idle. A standalone
reproduction measures 56 ms per 57 MiB allocate-touch-free cycle with defaults,
7 ms with raised thresholds and 10 ms with `MADV_HUGEPAGE`.

## Change (revised after the #155 review)

**Default: a bounded, scoped full-frame buffer pool** (`src/frame_buffer_pool.h`).
The reconstruction buffers (`Iref`, and `Iref_odd`/`Iref_even` when requested)
are acquired from the pool. After the output writer has written them, they go
back to it. The pool keeps at most 4 buffers, each exactly one frame of the
geometry it was made for. A release that does not fit (pool full, a buffer
under 8 MiB, or a non-owning alias) frees normally. **Retained memory is
therefore bounded by 4 × the largest frame** (228 MB for the tutorial
geometry). Nothing else in the process changes allocator behaviour; per-frame
movie storage on the float and CPU paths is untouched.

`MOTIONCORR_FRAME_POOL=0` disables pooling. `MOTIONCORR_FRAME_POOL_POISON=1`
is a test hook that fills every reused buffer with NaNs.

The host unaligned sum is not pooled, because on the resident CUDA path it is
no longer allocated at all (#159).

**Opt-in only: process-wide glibc thresholds** (`MOTIONCORR_MALLOC_REUSE=1`).
The original #155 behaviour is kept for measurement. It is not the default
because it changes every malloc-family allocation:

- `M_TRIM_THRESHOLD` is not a cap on retained memory. It only triggers
  trimming of the top-most free chunk. A probe retained about 435 MiB after
  freeing eight 57 MB blocks under a 256 MiB threshold (#155 review), and float
  frames, each one large allocation, all become heap-served.
- glibc < 2.35 refuses a mmap threshold above 32 MiB, and any successful
  setter freezes the dynamic threshold. The code sets the mmap threshold first
  and, if it is refused, changes nothing.
- User settings (`MALLOC_MMAP_THRESHOLD_`, `MALLOC_TRIM_THRESHOLD_`,
  `GLIBC_TUNABLES`) are never overridden.

The mode in effect is printed at start (`Host allocator: ...`) and recorded in
the `--profile` process record.

## Correctness

A reused buffer no longer starts as kernel-zeroed pages, so a read-before-write
would make products depend on the previous movie. Two tests cover this:

- `tests/test_host_buffer_reuse.py` checks that products are byte-identical
  without the pool, with it, with it plus `MALLOC_PERTURB_` and
  `MOTIONCORR_FRAME_POOL_POISON=1`, and under the opt-in thresholds. It runs a
  multi-movie batch and a mixed-geometry batch in one process.
- `tests/test_frame_buffer_pool.cpp` checks reuse, the retention bound, refusal
  of small, odd-size and aliased buffers, the disabled mode, and concurrent
  acquire and release.

The synthetic fixtures are 512×512, below the pool's 8 MiB floor. The
real-size identity check therefore runs on the 24-movie tutorial in the PR.
