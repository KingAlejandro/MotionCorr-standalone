# GPU characterisation of the workload corpus (4GPUs, A100, main `116eb04a`)

Timing, memory and decode-path measurements for the ten corpus families of issue #186, on one A100 with the
8-CPU lane, using main `116eb04a`. Definitions (families, inputs, options) come from the CPU thread's
`docs/workload_corpus/corpus.md` and `families.json` and are not repeated here. **Characterisation only:** no
source change, no product comparison beyond exit status and product count, no speedup claim. The CPU side-by-side
(section 10 of `results/tables.md`) is context from a different host.

## Result in brief

- **Host decode is the largest stage in 7 of 10 families: 54-78% of a steady movie in six of them, 33% for the 8-frame 10164.** The tutorial, which the existing numbers
  come from, is the only family on the nvCOMP device ingest (Deflate): 181 ms per steady movie, 0.5 ms per Mpx-frame.
  Every other family decodes on the host (LZW and EER included) and costs 1.0-9.5 ms per Mpx-frame (L, steady).
- **Ingest path actually taken** (`--ingest_witness`, every run): `nvcomp` for the tutorial only; `compact` (LibTIFF on the host,
  native samples staged, expansion and gain on the device) for the three LZW BigTIFF families; `float` (full host float movie) for EER
  and all MRC inputs. No silent fallback occurred: every run's witness matches its family and every run exited 0 with the expected product count.
- **Host decode saturates the 8-CPU lane.** CPU time over wall is 2.5-4.9 on the float and compact families where decode dominates (1.3 and 1.8 on 10641 and 10216, where the retry below runs on one thread; 1.2 on the tutorial).
  A faster host decoder needs more CPUs; a device decoder does not.
- **A data-dependent slow path, not related to ingest:** 41 of 50 patches in EMPIAR-10641 and 30 of 50 in EMPIAR-10216 do not converge at
  `--max_iter 5`. The inherited retry path downloads the resident real frames to the host and repeats the patch alignment. It costs
  13.6 s of a 15.7 s steady movie in 10641 (87%, 7 GiB RSS, 7 M page faults) and 1.7 s of 3.6 s in 10216. Config G is unaffected (3.9 s vs 29.8 s for 10641).
- **VRAM:** the peak is two resident float32 movies (`d_Fframes` + `d_Iframes`) plus 0.7-4.2 GiB. Measured peaks run from 2.7 GiB (10028)
  to 39.3 GiB (EMPIAR-10441, 11520x8184x50). Only 10441 exceeds a 24 GiB card, and it is borderline on 40 GiB (estimate, section VRAM).
- **Fixed cost per process is 0.53-1.25 s** outside the movie stages, plus a first-movie extra of 0.18-1.2 s. For the tutorial this is
  about 1.2 s of a 1.4 s two-movie run, against 0.18 s per steady movie.
- `--profile` costs nothing measurable here: profiled minus unprofiled wall is within -2.4% to +4.1% (median about 0%) over 20 cells.

## Setting

| item | value |
|---|---|
| source | main `116eb04ad359cd5bf789b28809fc2047ea155b9b`, clean tree `~/mc-small/src-116eb04` |
| binary | `~/mc-small/build-116eb04/motioncorr`, Release `-O3 -DNDEBUG`, CUDA 12.8, nvCOMP 5.3.0.16, cuFFT 11, sha256 `79c88e4ce1f1cb5a445f4da34f195b31edd257d58f4706624678f61fe6d6166c` |
| host | 4GPUs (`4-gpu-vm`), AMD EPYC 7452, 432 GiB RAM, kernel in `provenance.json`, **THP `madvise`** |
| GPU | GPU0, A100 80GB PCIe, `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, driver 570.86.10, **persistence mode disabled** |
| placement | `taskset -c 96-103`, `CUDA_VISIBLE_DEVICES=<UUID>`, `CUDA_DEVICE_ORDER=PCI_BUS_ID`, `--j 8 --gpu 0`, `OMP_PROC_BIND`/`OMP_PLACES` unset, `OMP_NUM_THREADS=8`. The driver and its NVML sampler sit on CPU 104, outside the lane. |
| data | **in tmpfs** (`/dev/shm/mc-corpus-186`, 19 GB): inputs, run directories and products were already in RAM, like a warm page cache, which is also how the CPU runs read them. Held families were copied from the #96 corpus (source untouched); tutorial from `~/mc-perf-20261001/data`; 10164 and 10216 were fetched directly from EBI on 4GPUs. Removed after the last run. |
| locks | `/tmp/motioncorr-bench.lock` then `/tmp/motioncorr-gpu0-correctness.lock`, taken per family block and released between blocks: 90 blocks, **63.2 min held** in total (budget was ~4 h). The only long wait (43 min) was the first block, behind another thread's timing job. |
| harness | profiling kit library of main `116eb04a` (`runner.run_once`: `wait4` rusage, NVML per-process and device VRAM sampling at ~10 ms, lane foreign-CPU and foreign-GPU-process flags, settle before every block), driven by `tools/gpu_matrix.py`. |

Inputs: 22 files verified against the SHA-256 in `corpus.md` on the tmpfs copies (`results/input-verify.json`, all pass).
Shared definitions used: `families.json` `86e4d697...053d` (unchanged between start and end), `corpus.md` `9dad79fc...` at the start.
`corpus.md` later gained a documentation-only note and file list (`dd7c8bea...`); no input, hash or option changed.

## Options and matrix

Per `corpus.md`: `--use_own --dose_weighting --dose_per_frame <family> --bfactor 150 --seed 1 --expected_frames <n>`, plus the family's gain and EER
options, `--gpu 0 --j 8`, and `--ingest_witness <file>` (diagnostic, writes no product). Default `--ingest auto` throughout; the tutorial
additionally with `--ingest nvcomp`. **G** = global only, **L** = `--patch_x 5 --patch_y 5`. Gain orientation is the default.

| phase | runs |
|---|---|
| warm-up | one discarded run per (family, G/L) cell: 20 runs (also the lock-time estimate) |
| unprofiled | **5 repeats** per cell, interleaved across families in rotating order: 110 runs (tutorial also `--ingest nvcomp`) |
| `--profile` | **3 repeats** per cell (device timing on, the default): 60 runs; plus 1 run of L per family with `--profile_device_timing 0`: 10 runs |
| replay | movie 1 listed 6 times under `r1_`..`r6_` symlinks, `--profile`, G and L, **3 repeats**: 60 runs. **Replayed rows, not distinct inputs.** They give the steady per-movie time and the first-movie extra. |

240 measured runs: all rc 0, expected product count, none flagged (largest foreign lane load 0.03 core, no foreign GPU process, payload image
and affinity verified, no compilers running), no repeat needed. Products per run: 2 `.mrc` (1 for 10441 and 12963) plus STAR/EPS/LST/PDF/log;
sizes in `results/runs.jsonl` (`product_inventory`). Product trees were deleted after each run.

## Per-family result

Wall = whole process (start, all movies, dataset report, exit), unprofiled, median [min-max] of 5. First/steady = movie 1 and the median of movies 2-6 of the
profiled six-row replay (L). RSS = largest process, unprofiled L. VRAM = NVML per-process peak over all runs of the cell (G / L), includes the CUDA context;
sampled, so a lower bound. Device-delta peaks are within 10 MiB of the process peaks (`results/tables.md` section 1).

| family | movies | ingest path | wall G s | wall L s | first / steady movie ms (L, replay) | steady ms per Mpx-frame (L) | host read share of steady | RSS GiB | VRAM GiB (G / L) | CPU/wall (L) |
|---|---:|---|---|---|---|---:|---:|---:|---|---:|
| RELION tutorial | 2 | nvcomp | 1.41 [1.35-1.42] | 1.43 [1.41-1.51] | 644 / 181 | 0.5 | 0% | 0.4 | 3.2 / 3.3 | 1.2 |
| EMPIAR-10028 | 2 | float | 2.20 [2.20-2.38] | 2.32 [2.23-2.40] | 959 / 700 | 2.6 | 57% | 1.6 | 2.6 / 2.7 | 3.0 |
| EMPIAR-10361 | 2 | compact | 4.90 [4.86-4.97] | 5.18 [5.14-5.28] | 2405 / 2063 | 1.4 | 67% | 1.7 | 11.6 / 12.3 | 4.7 |
| EMPIAR-10641 | 2 | compact | 3.90 [3.80-3.94] | 29.82 [29.80-30.02] | 16605 / 15730 | 9.5 | 4% | 7.0 | 13.1 / 14.7 | 1.3 |
| EMPIAR-10441 | 1 | compact | 6.85 [6.77-6.87] | 7.14 [7.06-7.17] | 6070 / 4843 | 1.0 | 54% | 5.0 | 37.0 / 39.3 | 3.2 |
| EMPIAR-10474 Falcon3 (58 fr) | 2 | float | 12.43 [12.35-12.51] | 14.21 [14.05-14.34] | 7664 / 7208 | 7.4 | 61% | 5.3 | 7.9 / 8.8 | 4.1 |
| EMPIAR-10474 Falcon4 (144 fr) | 2 | float | 25.99 [25.68-26.13] | 26.40 [26.03-26.41] | 12951 / 12776 | 5.3 | 78% | 12.0 | 18.6 / 20.0 | 4.9 |
| EMPIAR-12963 | 1 | float | 5.07 [5.05-5.10] | 5.80 [5.79-5.94] | 5326 / 4548 | 7.0 | 68% | 3.7 | 5.5 / 6.2 | 3.8 |
| EMPIAR-10164 tilt series (8 fr) | 2 | float | 3.01 [2.99-3.17] | 3.16 [3.13-3.21] | 1468 / 1005 | 2.2 | 33% | 2.2 | 4.5 / 4.5 | 2.5 |
| EMPIAR-10216 apoferritin (59 fr) | 2 | float | 4.75 [4.73-4.88] | 12.80 [12.73-12.88] | 3973 / 3639 | 3.7 | 26% | 4.2 | 8.0 / 9.0 | 1.8 |

Mpx-frame per movie: tutorial 342, 10028 268, 10361 1461, 10641 1650, 10441 4714, f3 973, f4 2416, 12963 654, 10164 456, 10216 990.
10641 and 10216 L include the non-convergence retry below; their G rows (0.9 and 2.0 ms per Mpx-frame) show the cost without it.
Tutorial `--ingest nvcomp` equals `auto` (G 1.36 s, L 1.49 s, witness `nvcomp`).

### Top stages, L, steady movie (replay; ms)

| family | steady movie | stage 1 | stage 2 | stage 3 |
|---|---:|---|---|---|
| tutorial | 181 | dose weighting 44 | session and device ingest 39 | patch alignment 26 |
| 10028 (f32 MRC) | 700 | host read 396 (57%) | movie teardown 130 | gain and sum 94 |
| 10361 (LZW) | 2063 | host read 1392 (67%) | global fft 224 | gain and sum 151 |
| 10641 (LZW) | 15730 | patch alignment 13634 (87%) | movie teardown 711 | host read 701 |
| 10441 (LZW, K3) | 4843 | host read 2614 (54%) | global fft 741 | gain and sum 457 |
| EER f3 | 7208 | host read 4382 (61%) | patch alignment 1418 | movie teardown 591 |
| EER f4 | 12776 | host read 10022 (78%) | movie teardown 1398 | gain and sum 891 |
| EER 12963 | 4548 | host read 3099 (68%) | patch alignment 697 | movie teardown 405 |
| 10164 (8-bit MRC, mode 0, 8 fr) | 1005 | host read 336 (33%) | movie teardown 217 | gain and sum 156 |
| 10216 (i16 MRC) | 3639 | patch alignment 1712 (47%) | host read 958 (26%) | movie teardown 458 |

`movie teardown` tracks the host float movie that the float path (and the retry download) frees: 0.12-0.17 s per GiB of host float movie across
10028, 10164, 10216, f3, f4 and 12963 (a correlation; the cause is inferred, not traced). It is below 70 ms on the compact path without retries (10361).

Stage walls come from `--profile` runs with device timing on, where each timed CUDA step waits for the device. The profile's own cost
was measured against unprofiled walls (`tables.md` section 7): within -2.4% to +4.1% per cell, and `--profile_device_timing 0` shows the same.

### Fixed and first-movie cost (L, replay, profiled)

| family | fixed outside movies, s | first minus steady, ms | `read gain` in first movie, ms |
|---|---:|---:|---:|
| tutorial | 0.77 | 463 | 106 |
| 10028 | 0.67 | 259 | 0 |
| 10361 | 0.82 | 342 | 0 |
| 10641 | 0.73 | 874 | 170 |
| 10441 | 1.25 | 1227 | 633 |
| EER f3 / f4 | 0.89 / 0.85 | 456 / 175 | 0 |
| 12963 | 0.72 | 778 | 403 |
| 10164 | 0.75 | 463 | 0 |
| 10216 | 0.76 | 334 | 0 |

The two-distinct-movie rows in `tables.md` section 3 confound movie content with first-vs-later (10216 movie 2 is 2x movie 1 because more of its patches
retry), so the replay rows are the first-vs-steady figures. Persistence mode is off on this host, so process and first-movie costs
include driver initialisation that persistence mode would shorten (see #53).

## Patch non-convergence retry (data dependent)

A patch whose first attempt reports `converged=no` goes through the retry branch in `src/motioncorr_runner.cpp` (`if (!converged)` after the resident attempt):
it downloads the real frames to the host (`downloadRealFrames`), re-extracts the patch and runs the alignment again. In the `Patch (1, 1)` log of 10641 the retry
prints the same five RMSD values as the first attempt (10.08, 6.41, 5.07, 4.43, 4.43) and still reports `converged=no`. Retried patches (first run of L, per-movie logs):

| family | patches | retried | retry converged |
|---|---:|---:|---:|
| 10641 (0.4 A/px, 70 fr) | 50 | 41 | 1 |
| 10216 (0.517 A/px, 59 fr) | 50 | 30 | 0 |
| EER f3 | 50 | 4 | 0 |
| EER 12963 | 25 | 2 | 0 |
| the other six families | 25-50 each | 0 | - |

That the retry reproduces the first attempt bit for bit is **not established** (only the logged RMSD sequences were compared). It is inherited behaviour,
so changing it needs the parity sign-off, not a quiet fix.

## VRAM

Measured: NVML process peak on the 80 GB A100 (table above and `tables.md` section 9). Tier 1 (#168) is already in `116eb04a`, so these peaks are post-Tier 1.
The traced allocation lines in the movie logs are lower (21.6 GiB traced for 10441 against a 39.3 GiB process peak) because they count the alignment-stage
buffers the code accounts for, not the whole process; they are not used for the fit estimate.

**Estimate (arithmetic, not measured on a small card).** Peak = 2 x frames x nx x ny x 4 B (resident `d_Fframes` half-spectra and `d_Iframes` real frames,
`docs/vram_live_ranges.md`) + a per-geometry overhead taken from the measurement above. The overhead is 0.67 GiB (4096x4096x16) to 4.2 GiB (11520x8184):
CUDA context, cuFFT work area, gain, patch workspace. The two movie buffers are 75-90% of the peak in every family (35.1 of 39.3 GiB, 89%, for 10441). A family fits when
the estimate is under 95% of nominal capacity.

| geometry | measured peak GiB | 24 GiB | 40 GiB | 48 GiB | max frames at 24 / 40 / 48 GiB |
|---|---:|---|---|---|---|
| 11520x8184x50 (K3 super-res, 10441) | 39.3 | **no** | borderline | yes | 26 / 48 / 58 |
| 4096x4096x144 (Falcon 4 EER, 10474f4) | 20.0 | yes | yes | yes | 166 / 288 / 349 |
| 7420x7676x8 (10164) | 4.5 | yes | yes | yes | 51 / 87 / 104 |
| 5760x4092x70 (10641) | 14.7 | yes | yes | yes | 116 / 202 / 246 |
| all other corpus families | 2.7-12.3 | yes | yes | yes | see `tables.md` |

The full frames-per-card table is in `results/tables.md` section 9. A 144-group EER movie at `--eer_upsampling 2` (8192x8192) would need
about 2 x 36 GiB for the pair, so roughly 75 GiB with overhead: close to the limit of the 80 GB card (estimate; not run). Tier 1 trimmed scratch only
(about 0.2 GiB on the tutorial). Reducing the peak materially means reducing one of the two resident movie-size arrays, which is the Tier 2 scope in
`docs/perf_vram_tier1/report.md` (per-tile patch FFT and per-frame C2R; its batch-invariance probe covered K3 and Falcon 4 patch sizes only and left full-frame C2R unrun).

## Ranked bottlenecks and ideas

Headroom figures are **ceilings from the measured stage shares** (the stage's time if it cost nothing), not expected gains. Rows 2-3 contain one analogy-based
estimate, labelled.

| # | bottleneck | families | measured share of steady movie | ceiling per movie | existing issue |
|---|---|---|---|---|---|
| 1 | EER host render (`host read movie`), plus the host float movie's upload (`gain and sum` 0.23-0.89 s) and teardown (0.4-1.4 s) | f3, f4, 12963 | 61% (76% without retry) / 78% / 68% (80%) | 4.4 / 10.0 / 3.1 s read, 4.2-4.7 ms per Mpx-frame | **#193** (host render into `uint16` + compact staging, or device render). #8 holds EER validation |
| 2 | LZW host decode on the compact path | 10361, 10441, 10641 | 67% / 54% / 33% (4% as measured, hidden by the retry) | 1.4 / 2.6 / 0.7 s; 0.42-0.95 ms per Mpx-frame | **#141** (nvTIFF). The host decode alone is 5-17x the 0.15 s/movie gate. Analogy-based estimate, not a measurement: the tutorial's Deflate device ingest costs 0.12 ms per Mpx-frame, which would leave about 0.2 s of 1.4 s on 10361 |
| 3 | Non-convergence retry (host download and repeat) | 10641, 10216, f3, 12963 | 87% / 47% / 20% / 15% | 13.6 / 1.7 / 1.4 / 0.7 s (the whole `patch alignment` stage; the retry's own share is not separated) | **#192** (keep the retry on the device, products unchanged); dropping the retry is a separate parity decision. Related #69, #157 |
| 4 | Raw MRC read and convert (u8, i16, f32) to a host float movie | 10028, 10164, 10216 | 57% / 33% / 26% (50% without retry) | 0.40 / 0.34 / 0.96 s; 0.74-1.48 ms per Mpx-frame | **#194**. The compact route is gated on a `tif` file name and on unsigned types; MRC mode 0 is read as signed char (`src/rwMRC.h:201`) and mode 1 as signed short, so signed staging is needed. Float32 MRC is out of scope. #8 for the MRC input paths |
| 5 | Per-process fixed cost and first-movie extra (context, nvCOMP/pinned setup, gain read on the first movie) | all; dominant for short runs | 0.53-1.25 s + 0.18-1.2 s per process | tutorial: ~1.2 s of a 1.43 s two-movie run | **#53**. First-movie `read gain` is 0.1-0.63 s in the four gain families |
| 6 | Device stages after decode (global FFT, gain and sum, dose weighting, patch alignment without retries) | K3, 10361 | each 3-15% (global fft 741 ms on 10441, 224 ms on 10361) | no single stage above 15% | none needed yet |
| 7 | VRAM capacity | 10441; EER with upsampling 2 | n/a | 39.3 GiB peak; 24 GiB card holds ~26 of 50 frames (estimate) | **Tier 2** (follow-up to #168) |

Rows 1, 2 and 4 are the same lever seen from three formats: the tutorial runs 0.5 ms per Mpx-frame because decode never touches the host, and every other family
pays 1.0-7.4 ms (L, excluding 10641, whose retry cost is in its 9.5). Rows 1 and 4 also remove the host float movie, which is what `gain and sum` uploads and `movie teardown` frees.

## Limitations

- One GPU model (A100 80 GB PCIe), one host, THP `madvise`, persistence mode off. SCARF and 4GPUs are not comparable (see the memory notes on THP and persistence).
- Inputs are in tmpfs, so no disk or network read time appears. Real storage can only add to the decode stages.
- Per-family movies: 1 or 2 distinct inputs. Replay rows repeat movie 1 and measure steady state, not content variation. The two distinct-movie rows differ in content as well as position.
- Peak VRAM and the `traced peak` are not the same quantity; NVML peaks are sampled lower bounds. VRAM on other cards is arithmetic from the 80 GB measurement.
- Dose per frame is a placeholder for most families, voltage is a placeholder for several, and gain orientation is the default. These runs time the work; products were not compared and no scientific claim is made.
- GPU idle time and overlap were not traced here (no Nsight run). For the tutorial see `docs/single_gpu_execution_profile.md`.
- `--ingest` was run as `auto` (and `nvcomp` for the tutorial). `compact` versus `float` was not compared on the LZW families.
- The retry's equality to the first attempt is not verified (above). The cause of the teardown correlation is inferred.
- CPU context comes from the CPU thread's uncommitted `cpu/summary.json` (sha256 `929735a5...c028`), which was read at the end of this pass.

## Files

| path | content |
|---|---|
| `tools/stage_inputs.py` | copy inputs to tmpfs and verify every file against `corpus.md` |
| `tools/setup_replay.py` | six-row replay run directories (`setup_corpus.py` of the CPU thread builds the normal ones) |
| `tools/gpu_matrix.py` | the driver (phases `warmup`, `rounds`, `replay`) built on the kit's `lib/` |
| `tools/collect_provenance.py` | host, GPU, binary, source, kit and input provenance |
| `tools/analyse_gpu.py` | `analyse_gpu.py FAMILIES_JSON RESULTS_DIR OUT_DIR [CPU_SUMMARY_JSON]` writes `summary.json` and `tables.md` |
| `provenance.json` | everything above, plus lock and run statistics |
| `results/runs.jsonl`, `blocks.jsonl` | one record per run (argv, wall, CPU, RSS, faults, VRAM, flags, witness, product inventory) and per lock block |
| `results/summary.json`, `tables.md` | derived figures; `tables.md` has sections 1-10 (all per-family tables, filtering, CPU context) |
| `results/input-verify.json` | SHA-256 verification of the 22 inputs |
| `evidence/profiles-and-witness.tar.gz` | every `--profile` jsonl and `--ingest_witness` file |
| `evidence/movie-and-stdout-logs.tar.gz` | per-movie logs (patch convergence, VRAM lines) and run stdout, per run |

Reproduce (on 4GPUs, paths as used): `stage_inputs.py` then the CPU thread's `setup_corpus.py` and `setup_replay.py`, then
`gpu_matrix.py --phase warmup`, `--phase rounds --reps 5 --prof-reps 3`, `--phase replay --replay-reps 3 --replay-g`, then `analyse_gpu.py`.
