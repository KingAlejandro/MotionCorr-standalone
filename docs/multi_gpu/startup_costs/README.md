# Per-process startup costs under the multi-GPU launcher

Each launcher worker is a separate `motioncorr` process, so every fixed cost
below is paid once per worker. These are **component measurements**, not
end-to-end savings; any change built on them needs a paired SCARF A/B before a
speedup is claimed.

Venue unless stated: 4GPUs (`4-gpu-vm`, A100 80GB PCIe x4, CUDA 12.8, driver
persistence mode off, no `nvidia-persistenced`), `flock
/tmp/motioncorr-bench.lock taskset -c 96-103`, THP `madvise`, 2026-10-13.

## Measured costs

`evidence/probe.cu` times each step in a fresh process; `evidence/probe.out`
has the commands and every row (3-5 reps per condition, medians below).

| Step | Condition | ms |
|---|---|---|
| `cuInit` | all 4 GPUs visible | ~300 |
| `cuInit` | `CUDA_VISIBLE_DEVICES=<one UUID>` (what the launcher sets) | ~110 |
| `cuInit` | another process already holds `cuInit` (emulates persistence) | ~60 |
| context create (`cudaFree(0)`) | one process | ~155 |
| context create | four processes starting at once | 470-555 |
| `cudaHostAlloc` 128 MiB | | ~120 |
| `cudaFreeHost` 128 MiB | | ~46 |
| `mmap` + touch 128 MiB, 4 KiB pages | | ~85 |
| `mmap` + `MADV_HUGEPAGE` + touch 128 MiB | | ~17 |
| `cudaHostRegister` 128 MiB | 4 KiB / huge pages | ~18 / ~9 |
| `cudaHostUnregister` 128 MiB | | ~7 |
| process exit wall, context + 128 MiB pinned + 1 GiB device | implicit teardown / explicit `cudaDeviceReset` | 470 / 470 |
| `CUDA_MODULE_LOADING=EAGER` vs default | one UUID visible | no meaningful difference |
| worker header `logfile.pdf` (Ghostscript) | replay of the runner's command | 140 |

SCARF (THP `always`), nsys on the parked one-process branch
(`perf/multi-device-one-process`,
`docs/multi_gpu/one_process/evidence/scarf/nsys/P2_cuda_api_sum.csv` and
`P2_osrt_sum.csv`): `cudaHostAlloc` 68 ms, `cudaFreeHost` 28 ms,
`cuModuleLoadData` ~0.4 ms x 184 calls, libc `system()` (Ghostscript) 180-191 ms
per call.

## Where it falls in a run

`evidence/mc-startup-st1.txt` (strace `openat`/`execve`, one movie, `--gpu 0
--j 8 --skip_logfile`, all GPUs visible; strace inflates the Ghostscript span):

| Offset from exec | Event |
|---|---|
| +26 ms | `libcufft` opened |
| +127 ms | first `/dev/nvidiactl` |
| +130-310 ms | `/dev/nvidia0-3` opened, NUMA reads (driver init) |
| +424 ms | first movie opened (gain at +437 ms) |
| +1.88 s | joint STAR written, then 6 EPS and `logfile.pdf.lst` |
| +1.90-2.44 s | `/bin/sh` -> `gs` builds `logfile.pdf` |

No input file is opened in the ~290 ms between the first driver open and the
input STAR, so host-side setup does not overlap driver and context setup.

## Levers

| Lever | Estimate | Status |
|---|---|---|
| Skip the workers' discarded `logfile.pdf` | 0.14 s (4GPUs) / ~0.19 s (SCARF) on the slowest worker's tail | done: `--skip_report_pdf`, below |
| Create the context on a background thread while host setup runs | ~150-250 ms | not started |
| Hugepage `mmap` + `cudaHostRegister` for the nvCOMP pinned stage | ~130 ms on 4GPUs; less on SCARF (THP `always`) | not started |
| Driver persistence mode | ~50 ms on `cuInit` | needs an administrator |
| Lazy module loading, skipping exit teardown, MPS, one process for all GPUs | none | rejected; one-process numbers in #175 |

Docs consulted: NVIDIA Driver Persistence
(<https://docs.nvidia.com/deploy/driver-persistence/persistence-daemon.html>,
device state is torn down when the last client closes it unless persistence is
on) and CUDA Lazy Loading
(<https://docs.nvidia.com/cuda/cuda-programming-guide/04-special-topics/lazy-loading.html>,
default since CUDA 12.3).

## Worker report suppression (`--skip_report_pdf`)

`--skip_logfile` skips only the per-movie batch pages: the runner still writes
6 EPS and runs Ghostscript for the header `logfile.pdf`. `merge_workers.py`
stages those under `_workers/wK/` and never publishes them; the dataset report
is built by the `--aggregate_only` step. The new runner flag writes the joint
STAR and returns before the report. The launcher passes it to every worker
unless `--worker-joint-report` is given or the caller names the flag; the
runner refuses it with `--aggregate_only`.

`evidence/worker_pdf/` (4GPUs, 24 tutorial movies, 2 workers via
`run_dataset.py`; base = `45b57754` (main), cand = this branch's code. Both
staged trees match their git trees blob-for-blob apart from `__pycache__`):

- `series.out`: Ghostscript execs 5 -> 3 (the remaining 3 are the aggregate's);
  worker consoles print "Now generating logfile.pdf" once each in base, never in
  cand.
- `tree-diff.txt`: the only paths missing from cand are each worker's
  `logfile.pdf`, `logfile.pdf.lst` and 6 EPS, in `workers/wK/` and
  `merged/_workers/wK/`. Nothing is added.
- `cmp.out`: `compare_output_trees.py --products-only` on the published tree
  (24 MRC, 25 STAR): base vs cand PASS, base vs cand-with-one-MRC-byte-flipped
  FAIL. The aggregate `logfile.pdf` has 30 pages in both, built from the same
  `logfile.pdf.lst` up to the temporary directory name.
- `gs-time.out`: the discarded build costs 0.14 s per worker (6 reps).

No wall-time saving is claimed from these runs; they ran under strace.
