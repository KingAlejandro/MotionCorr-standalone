# Reducing host/device round-trips (branch `perf/host-device-overheads`)

Follows `docs/host_device_audit.md` (#156, issue #157). Stacked on #155.

## Prior attempts

| idea | where | result |
|---|---|---|
| Remove timing-only waits in alignment | `experiment/post128-alignment-sync` | exact, **no-go**: 1/3 pairs faster, median +0.2 s |
| Remove per-frame syncs in global FFTs | `experiment/post128-fft-sync` | exact, **no-go**: 2/5 pairs faster |
| Make event profiling runtime-optional | PR #88 (#74) | exact, **no wall gain** at n=6, 95% CI ±1 s |
| DW telemetry-free stream-ordered loop | #139 control arm | exact, **−2.31 ms/movie, 161/168 movies faster** |
| CUDA Graph replay of DW | #139 | no-go: +0.94 ms/movie |
| Batched movie FFT (batch>1) | issue #50 lanes | rejected for VRAM: batch-2 exceeded the target; batch 1 kept |
| Persistent TIFF reader pool | #121 | no-go |
| Next-movie prefetch | #108, #94 | precondition failed on the nvCOMP path |

The conclusion behind those no-gos still holds: deleting a wait only helps when
the CPU has other work to do. Every remaining wait sat on a data dependency, so
the step stayed serial. Telemetry removal is kept here as hygiene, combined with
changes that actually remove dependencies or round-trips. It is not presented as
a gain by itself.

## Measured costs addressed (traced run, per movie unless stated)

| item | cost | change |
|---|---|---|
| final DW image D2H into pageable memory | 7.8 ms at 7.2 GB/s | async copy into a pinned buffer, ~2.5× faster |
| ~400 timing event syncs, record/elapsed calls | measured in aggregate only | events and log timing only under `--profile` |
| reconstruction buffers allocated and freed per movie | 5 `cudaMalloc`/`cudaFree` (each free syncs) | reuse session scratch |
| patch alignment: 25 sequential patches | ~250 blocking round-trips | one checked sync per iteration; no timing syncs |
| host sum allocated and zeroed every movie | 14–15 ms (with #155) | lazily materialised only when a CPU reader needs it |
| reconstruction buffer zeroed then overwritten | 6 ms | skip the zeroing when the CUDA path writes every pixel |

## Memory

- Pinned output buffer: one full-frame image (57 MB) per worker, held for the
  process. This is less than the per-movie pageable buffer it replaces, and is
  reused across movies of the same geometry.
- Session scratch reuse: no new VRAM. The DW scratch that was allocated per call
  is replaced by buffers the session already owns.
- Batched patches are out of scope here. They would multiply the patch
  workspace (~1.4 GB for 25 patches at this geometry); evaluate them separately
  with a chunk bound.

## Exactness

All changes in this branch are intended to be byte-identical: same kernels,
same order, same stream, same arithmetic. Only waits, telemetry, allocation and
copy destinations change. Any change that breaks bit-exactness will be a
separate, opt-in commit with a numerical comparison against the CPU and current
CUDA baselines, not part of these.
