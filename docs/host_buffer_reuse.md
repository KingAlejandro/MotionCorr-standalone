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

`main()` sets `M_MMAP_THRESHOLD` and then `M_TRIM_THRESHOLD` to 512 MiB before
any allocation, so freed full-frame buffers stay in the heap and the next movie
reuses them. The mode is printed at start (`Host allocator: ...`) and recorded
in the `--profile` process record.

### glibc versions

- **glibc >= 2.35** accepts the value. This covers Ubuntu 22.04+, RHEL 10 and Debian 12+.
- **glibc < 2.35** (RHEL 8/9, Ubuntu 20.04, Debian 11) rejects a mmap threshold
  above `HEAP_MAX_SIZE/2` (32 MiB). Any successful `mallopt` setter also
  disables the dynamic threshold, so setting only the trim threshold there would
  pin the mmap threshold at 128 KiB and *increase* mmap churn. The code
  therefore sets the mmap threshold first and, if it is refused, changes nothing
  and reports `glibc defaults (...)`. Those hosts behave exactly as before; buffer
  reuse there would need an explicit buffer cache instead.
- Setting the threshold disables glibc's dynamic threshold process-wide. That is
  intended here: large buffers stay in the heap.

### When it is skipped

- `MOTIONCORR_MALLOC_DEFAULTS` set to anything other than empty or `0`.
- The user already chose malloc settings (`MALLOC_MMAP_THRESHOLD_`,
  `MALLOC_TRIM_THRESHOLD_` or `GLIBC_TUNABLES`). These are never overridden.

### Threshold size

512 MiB covers the largest single full-frame float buffer expected: K3
super-resolution (11520×8184, 377 MB) and EER 8K at 4× (268 MB). Allocations at
or above it still get their own mapping. On the float ingest path each frame is
one such buffer, so the frame stack is heap-served too. The compact and nvCOMP
paths hold no host float movie.

## Correctness

Buffers that used to be fresh, kernel-zeroed mappings are now recycled heap
memory, so any read-before-write would make products depend on the previous
movie. `tests/test_host_buffer_reuse.py` checks for that. On a multi-movie batch
and on a mixed-geometry batch in one process, products must be byte-identical
across glibc defaults, reuse, and reuse with `MALLOC_PERTURB_` (every allocation
filled with a non-zero pattern).

## Memory

The live peak is unchanged. Freed memory is retained in the heap up to the trim
threshold, so RSS behaves as a high-water mark: same-geometry movies reuse the
space, while alternating geometries can fragment it. Measured peak RSS on the
24-movie tutorial (nvCOMP path, 6 paired runs) is 570 MiB with defaults and
643 MiB with reuse (+72 MiB). The float ingest path is measured separately in
the PR.

## Alternatives measured

- **`MADV_HUGEPAGE` on large buffers:** 10 ms per cycle in isolation, but
  first-touch cost depends on host fragmentation. One paired campaign on the
  shared host lost the gain whenever compaction stalled. Rejected as the
  primary fix.
- **Removing the allocations:** done separately where a buffer is dead
  (`perf/host-device-overheads`). Reuse covers the remaining live buffers.
