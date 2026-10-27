# Single-GPU baseline profile, unchanged C1 CUDA binary (26 October 2026)

Characterization only. No optimisation, no speedup claim, no cross-venue ratio. **C1 M1 stays held; the A13 and K269-CUDA FAIL dispositions are unchanged** (the acceptance packet and `native-final-20261025/` were not touched). Plan frozen before launch: [PREDECLARED.md](PREDECLARED.md) (sha256 in `evidence/PREDECLARED.sha256`, frozen 14:15:24Z; runs started 14:15:36Z).

## Pins and receipts

| | |
|---|---|
| Source | `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`, clean checkout, no rebuild |
| Binary | `build-cuda/motioncorr` sha256 `34e768128b83f7c94eb4a41ee6bb9a795c52c531a5d646ce4116df83d8d3535a` (plain CUDA, Release -O3, the K269/CTest binary) |
| Input | K269 census movie `dose1-s01` (4096x4096x40 float MRC): movie.mrcs `3b6126ef…d25def`, RECEIPT.json `27d9a55b…0608a6`, input.star `ba3a39e5…ac55`; equal to the hashes in the retained census RUN.json |
| Command | the K269 census options with `--j 6` and without `--skip_logfile` (complete publication): `--use_own --j 6 --patch_x 5 --patch_y 5 --group_frames 1 --bin_factor 1 --seed 1 --skip_defect --save_noDW --first_frame_sum 1 --last_frame_sum 40 --ingest float --ingest_witness F --gpu 0` ([evidence/kit-run1/provenance.json](evidence/kit-run1/provenance.json)) |
| Affinity | whole chain `taskset -c 96-103`; payload CPUs 96-101 (verified per run), kit and monitor on 102-103 |
| GPU | GPU3 `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d` by UUID (A100 80GB PCIe, driver 570.86.10, persistence off); NVML sampling per run saw only the run's own PID |
| Route | pinned `--ingest float` (host float reader, no nvCOMP, no compact); witness `movie.mrcs float` x7 (7 processes), no fallback line |
| Locks | GPU3 correctness lock and `/tmp/motioncorr-bench.lock` taken with `flock -n` before the first run and held to the end (inode recorded in [locks.txt](evidence/logs/locks.txt)); both free afterwards. The profiling kit ran with `--no-lock` because this script held them continuously |
| Health | C1 health check (identity, ECC, row remap, retired pages, no compute process) PASS before and after; no Xid scan (not requested; no sudo) |
| Host | THP `madvise`, glibc defaults, load1 1.06-1.82 over the window, no other GPU process on any GPU, scratch 388 MB, trace 268 KB |

## Unprofiled wall samples (kit `run`, one process per sample, process start to exit)

| run | wall s | CPU s | peak RSS GiB | flags |
|---|---|---|---|---|
| W warmup (not a sample) | 3.008 | 8.43 | 2.81 | none |
| A1 | 2.745 | 7.67 | 2.83 | none |
| A2 | 2.853 | 8.05 | 2.86 | none |
| (P1, P2 profiled, below) | | | | |
| A3 | 2.738 | 7.59 | 2.86 | none |
| A4 | 2.700 | 7.59 | 2.82 | none |

AA scatter: |A2-A1| 3.9% of their mean, |A4-A3| 1.4%; A1-A4 range 2.700-2.853 s (5.7% of the minimum), mean 2.759 s. The observed A1-A4 range is 5.7% of the minimum and the two same-binary pairs differ by 3.9% and 1.4%; these are descriptive observations of four samples, not a calibrated resolution bound (amended 2026-10-26, below). Peak device memory above idle 6.40 GB in every run. Foreign lane CPU at most 0.008 cores; no foreign GPU process.

## Complete publication and drift

Each run publishes 14 files: `movie.mrc` (64 MiB sum), `movie.star`, `movie.log`, `movie_shifts.eps`, the aggregate `corrected_micrographs.star`, three `corrected_micrographs_all_rlnAccumMotion{Early,Late,Total}.eps`, `logfile.pdf` (3 pages), `header.pdf`, `all_batches.pdf`, `batch.pdf` (0 bytes) and two `.lst` files. No separate noDW MRC is written because this census configuration has no dose weighting. A1 vs A2, A3, A4 and vs P1 with the kit's identity comparison: **identical** (9 files compared, MRC payload equal; PDFs and per-movie log are excluded by the kit's rules, Ghostscript dates and timings). Whole-file sha256 differs for 8 files in every pair for the usual reasons (MRC header label timestamp, output-root paths in STAR/EPS/lst, PDF dates, log timings), as expected ([baseline-results.json](evidence/baseline-results.json)). No drift.

## Stage profile, P1 (built-in `--profile`, device timing off, no Nsight; one sample)

Movie wall 2356.9 ms; run wall 2564.6 ms (the remaining 208 ms: main-thread joint STAR and `logfile.pdf` 199.7 ms, writer drain 7.5 ms); writer threads 129 ms in parallel; `/usr/bin/time` 2.82 s, peak RSS 2.81 GiB.

| stage | wall ms | share of movie | notes |
|---|---|---|---|
| host read movie | 1313.2 | **55.7%** | CPU 1054 ms, 233,226 minor faults, 42 blocking switches |
| movie teardown | 325.2 | 13.8% | |
| gain and sum | 298.6 | 12.7% | |
| unweighted sums | 161.3 | 6.8% | |
| session and device ingest | 158.6 | 6.7% | |
| patch alignment | 44.7 | 1.9% | |
| global fft / alignment / ifft | 14.9 / 11.5 / 14.6 | 0.6 / 0.5 / 0.6% | |
| other (setup, release, fit, plot) | ~14 | 0.6% | |

**Result: dominant stage = host read movie** by the predeclared rule (>=35% of the movie wall and >=1.25x the next stage: 55.7% and 4.04x movie teardown (raw 1313.183594 / 325.213809 ms); amended 2026-10-26, below). This is one sample, so the shares are single-sample facts, not stable estimates; the first-touch fault count is a recorded fact, not a diagnosed cause.

## Device view, P2 (Nsight Systems 2024.6.2, `cuda,nvtx`, no CPU sampling, unprivileged; one sample, instrumented)

Host walls in this run are inflated by tracing and are not used for shares. Traced window 2889.9 ms: device busy 516.1 ms (17.9%), idle 2373.8 ms; 749 kernels (83.5 ms summed), 143 copies (432.5 ms, 5195.7 MiB), kernel/copy overlap 0 ms. Host-to-device pageable copies 2570 MiB in 84 copies (422.1 ms device time, 6.4 GB/s) make up almost all of the `gain and sum` stage's device busy time (421.6 ms busy in a 434 ms traced stage). Allocation high-water 5661 MiB at patch alignment. Top kernels: Bluestein FFT 29.1%, radix FFT 18.0%, polynomial interpolation 11.3%, Fourier shift 11.3%. Full report: [evidence/kit-trace/report.md](evidence/kit-trace/report.md).

## Interpretation (limits stated once)

For this movie, on this host, in this 6-CPU lane, with a warm page cache and the host float reader, the run is host-bound: the device is idle for 82% of the traced window and the largest single cost is reading the movie on the host (about 56% of the movie wall), followed by teardown and the gain/sum upload. Everything is one movie, one binary, one route and one lane; the cold-cache read, the nvCOMP route, dose weighting, other geometries and `--j 8` were not measured. Wall samples are four numbers; no stable speedup, no CPU/GPU or cross-venue comparison is claimed. The census `--j 2` timings (about 4.5-5 s per movie) are not comparable (different threads, `--skip_logfile`).

## Retrieval

`retrieval-index.txt`: sha256, size and VM path of all 132 files under `/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-bp-20261026` (kept outside Git: run trees with the 64 MiB sums, `kit-trace/trace.nsys-rep` sha256 `4af4be60…0cce7a`, full kit reports). `evidence/` holds the compact receipts (runs.jsonl and provenance of each kit invocation, reports, P1 JSONL, trace summary, monitor, occupancy, health, pins). `run_baseline.sh` is the exact driver; `analyze.py` produced `baseline-results.json`.

## Amendment 2026-10-26 (result interpretation; docs only, no new measurement)

Raw data, `evidence/`, `retrieval-index.txt` and the original commit `0247cc2d` are unchanged; the corrected lines above replace their earlier wording in place and the earlier wording stays in git.

1. **Ratio corrected.** The dominant-stage ratio was published as 2.27x. From the raw P1 record (`evidence/p1/p1.profile.jsonl`): host read movie 1313.183594 ms, movie teardown 325.213809 ms, ratio **4.038x** (4.40x against gain and sum, 298.606297 ms). The share 55.7% (1313.183594 / 2356.923755) was right. The predeclared rule (>=35% and >=1.25x the next stage) is satisfied by the corrected numbers, so the conclusion is unchanged. The PR #282 comment of 26 Oct that said "2.3x the next stage" carries the same error and is corrected in the follow-up comment.
2. **Wording.** "Differences below about 6% ... are not resolvable" treated a four-sample range as an inferential resolution. Replaced by the descriptive statement: observed A1-A4 range 5.7% of the minimum, same-binary pairs 3.9% and 1.4%. No resolution bound is calibrated from four samples.
3. **What the largest phase is, from source (read-only, `e77a51a2`, no new timing).** The built-in stage `host read movie` is `MC_STAGE("host read movie")` at `src/motioncorr_runner.cpp:2538` to `MC_STAGE("allocate host sum")` at about :2606. It encloses the `read_errors` vector, an `omp parallel for num_threads(n_io_threads)` over frames (`n_io_threads = n_threads`, capped by `--max_io_threads`, :142/:2095-2100), and per frame `read_movie_frame` -> `Image<T>::read(fn_mic, true, frames[i], false, true)` (`image.h:719`) -> `fImageHandler::openFile` (a file open per frame call), `_read` -> `readMRC` (`rwMRC.h:261`, header `fread` and `parseMRCHeader`) -> `readData` (`image.h:1161`: `data.coreAllocateReuse()`, page-buffer allocation, `fseek`, per-page `fread`, `castPage2T`, where the float-to-float case is a `memcpy`), the page free, then the exception rethrow loop. The "per-row Y-flip" in the runner comment belongs to the TIFF reader (`rwTIFF.h:276-311`); the float MRC `readData` path of this input contains no flip. So the 1313 ms phase is the whole enclosed block, **not file I/O alone**. The phase is measured; its cause within the phase (frame-buffer allocation and first touch, page buffer, `fread`/memory copy, file-open, memory or file-system behaviour, thread scheduling) is **unresolved**. The warm page cache and 0 major faults in the record do not diagnose it (233,226 minor faults are recorded, not interpreted).
