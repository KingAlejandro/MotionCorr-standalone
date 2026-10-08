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

## Change

`main()` raises `M_MMAP_THRESHOLD` and `M_TRIM_THRESHOLD` to 256 MiB before
any allocation, so freed full-frame buffers stay in the heap and the next movie
reuses them. This is glibc-only and a no-op elsewhere.

- **Products:** unchanged. Every buffer is still initialised by the code that
  allocates it. Only where the pages come from changes.
- **Memory:** live peak is unchanged. Up to the trim threshold of freed heap
  memory is retained between movies. The run's peak RSS is the figure to watch
  and is reported below.
- **Escape hatch:** `MOTIONCORR_MALLOC_DEFAULTS=1` restores glibc defaults,
  which also makes a same-binary A/B possible.

## Alternatives measured

- **`MADV_HUGEPAGE` on large buffers:** 10 ms per cycle in isolation, but
  first-touch cost depends on host fragmentation. One paired campaign on the
  shared host lost the gain whenever compaction stalled. Rejected as the
  primary fix.
- **Removing the allocations:** the host sum is unread on the resident path
  only when GPU statistics pass their exactness guard, and the reconstruction
  buffer is always written. Either change would be more invasive, and both are
  subsumed by reuse.
