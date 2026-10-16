# Registered hugepage staging pool (parked)

**Status: parked; not for merge.** The decision on #53 required a resolved
SCARF dataset-wall gain for this change alone. The paired SCARF A/B did not
resolve one: 1×8 −72 ms (8/12 pairs, p=0.39), 4×8 −81 ms (9/12, p=0.15). The
per-process component saving is measured and consistent: pinning the 128 MiB
pool costs 15 ms instead of 86 ms on SCARF and 22 ms instead of 112 ms on 4GPUs.
Evidence: [`evidence/pinned_register/`](evidence/pinned_register/README.md).

This is step 2 of #53. Step 1, creating the CUDA context on a helper thread, is
not merged and is not on this branch. It stays on `perf/cuda-warmup-thread`
(`6d9527a9`).

## Change

`ensurePinnedStage()` used to keep the worker-lifetime nvCOMP staging pool in a
`thread_local` `cudaHostAlloc` buffer. That allocation costs about 112 ms for
128 MiB on 4GPUs (THP `madvise`), and `cudaFreeHost` about 43 ms.
`mc_cuda::PinnedStage` now owns the buffer as a 2 MiB-aligned anonymous mapping
with `MADV_DONTFORK` and `MADV_HUGEPAGE`, pinned in place by
`cudaHostRegister`. The size and the point of allocation are unchanged, so
`MOTIONCORR_NVCOMP_PINNED_MAX_MB` behaves as before. A pool sized before the
first movie would need that movie's compressed request and could pin memory that
runs without nvCOMP never use, so the hand-off design (option a) was not used.

- **One owner, one free path.** The buffer is either `Registered`, released by
  `cudaHostUnregister` then `munmap`, or `HostAlloc`, released by `cudaFreeHost`.
  `release()` is idempotent. `acquire()` refuses while a buffer is held, so
  growing the pool is release-then-acquire, as before.
- **Fallback.** If the mapping, `MADV_DONTFORK` or the registration fails, the
  mapping is returned and `cudaHostAlloc` supplies the buffer, with one extra log
  line. A refused `cudaHostRegister` leaves its status in the thread's last-error
  slot, so `acquire()` clears it, but only when the slot still holds that status.
  The `pinned staging pool grown to N bytes` line is unchanged.
  `MOTIONCORR_PINNED_REGISTER=0` selects `cudaHostAlloc`.
- **Free failures.** A failed unpin keeps ownership, as a failed `cudaFreeHost`
  did. The thread-exit destructor returns the mapping regardless, because the
  context may already be gone.
- **Ledgers.** `CudaPreprocessingFailurePaths` tracks `cudaMalloc`/`cudaFree`.
  Pinned host memory has its own ledger, `CudaPinnedStage`: a device-free
  counting backend plus four compiled mutants (double free, leak after unpin,
  leak on refusal, mapping inherited by fork).

## Fork exposure

The runner forks while the pool is held: `popen` for compressed MRC movies and
`system()` for Ghostscript. `fork_probe` forks with 128 MiB held under each
pinning method, writes a new pattern in the parent while the child is alive,
copies it to the device and checks every page.

| Pinning | VMA flags | Mapped in child | `fork()` | Stale pages read by the device |
|---|---|---|---|---|
| `cudaHostAlloc` (main) | `sh` (shared driver mapping) | yes, shared | 2.5 ms | 0 |
| `mmap` + register (`16bd9eee` alone) | private anonymous | yes, copied | 54-58 ms | 0 |
| `mmap` + `MADV_DONTFORK` + register (this branch) | `dc` | no | 2.4 ms | 0 |

These are SCARF gn0002 figures (kernel 5.14 el9, driver 580). The 4GPUs rows
are in the evidence.

- **Main:** main's buffer did not have the same exposure. A fork shares it
  without copying it, and no copy-on-write fault can move it.
- **Without `MADV_DONTFORK`:** the registered mapping made every fork copy the
  pinned pages, about 55 ms per fork on SCARF. Neither kernel served the device
  a stale page. That depends on the kernel copying pinned pages at fork, which
  older kernels did not do.
- **With `MADV_DONTFORK`:** the child gets no mapping at all.
- **Test:** `CudaPinnedStage` forks with the real mapping held and requires
  `mincore()` in the child to report `ENOMEM`. The mutant without the `madvise`
  fails that check.

## Transparent huge pages

4GPUs runs THP `madvise` with defrag `madvise`, so a fault in this mapping
compacts memory synchronously when no 2 MiB block is free. The host had been up
87 days and had 17,553 free 2 MiB blocks.

Across 45 probe acquisitions and 16 profiled runs, every acquisition got huge
pages for the whole buffer. The system-wide `compact_stall` and
`thp_fault_fallback` counters did not change around any process. `ingest setup`
took 28.1-29.3 ms in every run.

Not tested: a host with few free 2 MiB blocks. There the faults would compact
directly. `MADV_NOHUGEPAGE` would avoid that at 75 ms per acquisition, still
below `cudaHostAlloc`'s 112 ms.
