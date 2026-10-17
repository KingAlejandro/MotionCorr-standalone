# RC0 memory admission on smaller GPUs (QM)

Register row QM (#198). Measurement and qualification only; no source was changed.

## Result

On `483e881d` (CUDA + nvCOMP, Release), with an A100 80 GB made to look like a 40, 24 or 16 GiB card by a VRAM balloon:

- **No crash, hang or wrong output.** 162 runs (18 unconstrained, 144 constrained), exit status only 0 or 1, no timeouts (longest 75 s). All 102 constrained runs that completed have corrected image, motion STAR and joint STAR identical to the unconstrained run of the same case. Every failed single-movie run (38 runs, all exit 1) names the movie, writes no `.mrc`/`.star`, leaves no stray file, and releases the GPU. In the 4 failed multi-movie jobs the failed movie has no products and the other movies are complete.
- **Memory admission works at the session level.** When the resident session cannot allocate its two stacks, the movie falls back to the streaming path and still completes identically. When even that cannot fit, the movie fails.
- **Three problems found** (details below; none fixed here):
  1. **D1.** A movie that fails with a device OOM makes the *next* movie lose its fast route (nvCOMP or resident), although the next movie fits. Products stay identical; only speed and route change. The third movie is unaffected.
  2. **D2.** Admission only checks the session buffers. In config L there are free-VRAM bands just above each streaming-only range where the session is admitted and then patch alignment runs out of memory, so the movie fails although the streaming path would have completed at that free VRAM (10441: 37.5–38.5 GiB; e10474f4: 19–19.5; e10216: 8.5).
  3. **D3.** The final failure is late and its text is misleading (see below). For 10441 at 16 GiB the movie spends about 30 s and 35.7 GiB of host RSS before failing.

## Provenance

| Item | Value |
|---|---|
| Source | `483e881d9a6a352dba3268dac0f8c729364860b5` (main), clone of a git bundle |
| Binary | `build-nvcomp/motioncorr`, sha256 `d8e7a003753be5d83b5ea88f5cc3af950f06b5c03d939e6e77b760e8f2f98173` |
| Build | Release, `-DCUDA=ON -DUSE_NVCOMP=ON -DCMAKE_CUDA_ARCHITECTURES=80`, CUDA 12.8, nvCOMP 5.3.0.16, driver 570.86.10 |
| Host / GPU | `4GPUs`, GPU1 only: A100 80GB PCIe, `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d`; `CUDA_VISIBLE_DEVICES=1`, `taskset -c 104-111`, inside `flock /tmp/motioncorr-gpu1-correctness.lock`; bench lock checked before every run (one 60 s wait) |
| Inputs | `input_sha256.txt` (all match `docs/workload_corpus/corpus.md`). 10441 `20May09_3A-3_109-21_0003.tif` + `200509_gain.mrc`; EMPIAR-10474 Falcon 4 `…001116_Fractions.mrc.eer` (144 groups, `--eer_grouping 40`); tutorial `20170629_00026`; e10216 (int16 MRC); e10361 (u8 LZW TIFF) |
| Config G | `--use_own --dose_weighting --dose_per_frame <family> --bfactor 150 --seed 1 --expected_frames N --j 8 [--gainref] --gpu 0 --ingest <auto\|compact\|float>` |
| Config L | G plus `--patch_x 5 --patch_y 5` |
| Comparison | `docs/issue85_laneC/compare_output_trees.py`, strict (whole tree) and `--products-only`, against the unconstrained run of the same case |

**Balloon.** `harness/qm_balloon.cu` `cudaMalloc`s 1 GiB chunks on GPU1, touches them and sleeps. The harness calibrates its own context overhead, then checks `nvidia-smi` free memory before each run; "free GiB" everywhere below is that reading (for example 24 GiB nominal = 24573 MiB measured). The balloon is the harness's child, killed in a `finally`; after every run `nvidia-smi` showed 1 MiB used and no compute apps. The harness samples `nvidia-smi` every ~0.15 s, so sampled peaks are lower bounds.

**Bisection.** Floors were bracketed to 1 GiB (0.5 GiB in the bands). Completion is **not monotone** in free VRAM, so `tables.md` lists every probe; do not interpolate between them.

## Per-case verdicts

Cells are `outcome, wall s`. "res" = resident session (compact, nvCOMP, or float ingest into the session), "stream" = session declined, streaming float path. All completed cells have identical products.

| Movie | Config | `--ingest` | 40 GiB | 24 GiB | 16 GiB |
|---|---|---|---|---|---|
| e10216 | G | auto | res, 2.3 | res, 2.3 | res, 2.3 |
| e10216 | L | auto | res, 2.8 | res, 2.8 | res, 2.8 |
| e10441 | G | auto | res, 8.7 | stream, 60 | **FAIL** clean, 29 |
| e10441 | G | float | res, 12.1 | stream, 54 | **FAIL** clean, 29 |
| e10441 | L | auto | res, 8.6 | stream, 69 | **FAIL** clean, 31 |
| e10441 | L | float | res, 12.4 | stream, 64 | **FAIL** clean, 28 |
| e10474f4 | G | auto | res, 12.0 | res, 11.8 | stream, 38 |
| e10474f4 | L | auto | res, 12.3 | res, 12.2 | stream, 42 |
| tutorial | G | auto | res, 1.2 | res, 1.1 | res, 1.1 |
| tutorial | L | auto | res, 1.3 | res, 1.3 | res, 1.2 |

Other cases:

| Case | Verdict |
|---|---|
| 10441 `--ingest compact`, 24 and 16 GiB | **Fails clean, fast** (1.1 s, exit 1): "`--ingest compact` was requested but the compact native staging did not apply…". No products. |
| 10441 `--ingest float`, 24 GiB | Completes identical via streaming (54–64 s). 16 GiB fails as for `auto`. |
| e10361 (62 frames, 5760×4092) G and L, 16 GiB | Resident, identical (control for D1; peak 11.9 GiB). |
| mmA/mmB/mmC at 24 GiB (10441 then tutorial [then e10361]) | All movies complete, every movie identical. Movie 1 uses streaming; later movies keep their baseline routes. |
| mmA/mmB/mmC at 16 GiB | Movie 1 fails clean (no products); later movies complete, products identical. Movie 2 loses its fast route (**D1**); movie 3 is back on its baseline route. |

## VRAM floors

Minimum free VRAM at launch (GiB, measured after the balloon, excludes the process's own CUDA context), A100, `--use_own --gpu 0`. "Resident" means the full-speed route with no fallback logged. "Streaming" means the session is declined and the movie completes through the streaming path.

| Geometry (frames, route) | Two resident stacks | Peak, 80 GB run (G / L) | Resident floor G | Resident floor L | Streaming completes (G / L) | Fails at or below |
|---|---:|---:|---|---|---|---|
| tutorial 3838×3710×24 (nvCOMP) | 2.5 GiB | 3.2 GiB | 4 | 4 | 2–3 | 1 |
| e10216 4096²×59 int16 MRC (compact) | 7.4 GiB | 8.0 / 8.7 | 8.25 (8.0 degrades to CPU preprocessing) | 8.75 (**8.5 fails**; 8.0 degrades) | 5–7.5 | 4 |
| e10361 5760×4092×62 u8 TIFF (compact) | ≈11 GiB | 11.6 | not bisected; resident at 16 | not bisected; resident at 16 | not tested | not tested |
| e10474 Falcon 4 4096²×144 EER (compact) | 18.0 GiB | 18.6 / 19.9 | 19 | 20 (**19–19.5 fail**) | 12–18.5 | 11 |
| e10441 11520×8184×50 u8 TIFF (compact) | 35.1 GiB | 37.0 / 39.3 | 37.5 (37 degrades to CPU preprocessing, 60 s) | 39 (**37.5–38.5 fail**; 37 degrades, 68 s) | 22–36.5 | 21 |

Streaming-path host RSS: 10441 about 36 GiB (resident compact: 5.0 GiB), e10474f4 21 GiB (7.4), e10216 7.6 GiB (2.1). The streaming path is 7–9× slower for 10441 (54–69 s vs 7–9 s) and about 3× for e10474f4 (35–42 s vs 12 s).

## Findings

### D1. A failed movie makes the next movie lose its fast route

At 16 GiB free, after 10441 fails, the next movie is declined by an "out of memory" that is not real:

- tutorial (needs 3.2 GiB, 15 GiB free): `CUDA Error in cuda_movie_session.cu:2012 : out of memory`, "Device ingestion failed recoverably … re-reading the movie with the host reader", route `compact` instead of `nvcomp`.
- e10361 (needs 11.9 GiB, 16 GiB free; the standalone control at 16 GiB runs resident): `cuda_movie_session.cu:913 : out of memory`, "CUDA fused gain and sum failed. Falling back to CPU preprocessing".
- The process holds 422 MiB of device memory after the failed movie (`logs/mm*-L-auto@16/timeline.csv`), against 414 MiB at process start, so nothing large is retained.
- Both sites are `HANDLE_ERROR(cudaGetLastError())` straight after the first kernel launch of the movie. Movie 1 failed in a plain `cudaMalloc` check (`cuda_alignpatch.cu:1121`) that never reads the last-error slot. `harness/qm_stale.cu` shows the CUDA behaviour: a handled failed `cudaMalloc` leaves `cudaErrorMemoryAllocation` pending and the next `cudaGetLastError()` after a good launch returns it (`logs/stale_repro.out`, and a clear-before-launch control returns success).
- The mechanism fits all the evidence but was not confirmed inside the product (no instrumented build).
- At 24 GiB, where movie 1 is handled by the session's own fallback, movie 2 keeps its route. The effect lasts one movie (mmC: movie 3 is back on baseline).
- Products of the affected movie are identical to the unconstrained run in every case. The cost is the fast route (CPU preprocessing or host reader).

### D2. Admission does not reserve the patch-stage headroom

`initialize()` checks the session buffers only. Just above the streaming-only range, config L admits the session, then patch alignment cannot allocate. The recoverable declines are logged ("resident patch preparation did not complete…", "CUDA patch preparation declined…"), then `cuda_alignpatch.cu:1121` OOMs and the movie fails after 20–23 s. At the same free VRAM the streaming path completes.

| Case (config L) | Fails | Completes just below | Completes just above |
|---|---|---|---|
| 10441 | 37.5, 38, 38.5 GiB | 36.5 (stream); 37 (resident, CPU preprocessing, 68 s) | 39 |
| e10474f4 | 19, 19.5 | 18.5 (stream) | 20 |
| e10216 | 8.5 | 8.0 (CPU preprocessing), 7.5 (stream) | 8.75 |

Config G has no failing band; it degrades to CPU preprocessing for a few hundred MiB (10441 at 37 GiB, e10216 at 8 GiB). Relevant to common cards (card sizes are not measured here): an A100 40 GB has 40960 MiB in total, so if its driver reserve matches the 766 MiB seen on this 80 GB card it would show about 39.3 GiB free, at the 10441 config L floor with no margin; a failure there is clean but avoidable. A card showing 23.5–24 GiB free would sit only 1.5–2 GiB above the 10441 streaming floor.

### D3. The failure itself is late and badly worded

10441 at 16 GiB (G and L, `auto` and `float`): hot-pixel detection and the widening to a 17.6 GiB host float movie run first (35.7 GiB host RSS, about 30 s), then `cudaAlignPatch` cannot `cudaMalloc` the Fourier stack (`cuda_alignpatch.cu:1121`, error 2). Stdout does say `out of memory`, then prints the generic "A GPU-function failed to execute … you might have GPUs which are incompatible…" text and a backtrace; the final line names the movie ("Motion correction failed for 1 movie(s): …"). Not tested: a host with less than ~36 GiB of RAM, where the host side may fail before the clean error is reached.

### Smaller points

- A handled session-init OOM is logged as `ERROR: Movie buffer allocation failed: out of memory` followed by a `WARNING … falling back to streaming pipeline`. Harmless but reads like a failure.
- Patch alignment adapts its chunking to the free memory ("workspace does not fit, using per-patch alignment") with identical products.
- Strict whole-tree comparison differs from the unconstrained run only in `.log` files, and only in lines on a declared list (route/fallback lines, free-memory numbers, patch chunking, VRAM statistics, output path). `harness/qm_final.py` applies the list; 0 non-listed lines remained across all 102 completed constrained runs (`log_residuals.json`). Products-only comparison passes for all 102.

## Suggested release wording (DOC1)

> **GPU memory.** The resident CUDA route keeps the movie on the device twice (real space and Fourier space, about 8 bytes × pixels × frames) plus a few GiB of workspace. The table gives the minimum free GPU memory at launch for the full-speed route on an A100, measured with `--use_own --gpu`; leave 1–2 GiB of margin and add about 1 GiB for local (patch) alignment.
>
> | Movie | Full speed (global / patch) | Slower streaming route completes | Fails |
> |---|---|---|---|
> | 3838×3710×24 | 4 / 4 GiB | 2–3 GiB | ≤ 1 GiB |
> | 4096²×59 (int16 MRC) | 8.25 / 8.75 GiB | 5–7.5 GiB | ≤ 4 GiB |
> | 4096²×144 (Falcon 4 EER) | 19 / 20 GiB | 12–18.5 GiB | ≤ 11 GiB |
> | 11520×8184×50 (K3-class u8 TIFF) | 37.5 / 39 GiB | 22–36.5 GiB | ≤ 21 GiB |
>
> If the resident session does not fit, the movie is processed through the streaming route (identical output, 3–9× slower, and several times the host RAM: about 36 GiB for the 11520×8184×50 movie). If that does not fit either, the movie fails with an out-of-memory error and writes no products. Within about 1.5 GiB above a full-speed floor a movie can fall back to CPU preprocessing or, with patch alignment, fail; do not run at the floor. After a movie fails with an out-of-memory error, the next movie in the same run may use a slower route (output unchanged). `--ingest compact` refuses immediately when the resident session cannot be created.

## Limitations

- One 80 GB A100 emulating smaller cards: the balloon fixes free memory but not bandwidth, SM count or the driver's own reservation on a real small card. Floors are in free GiB, not card size.
- One movie per family; 1 GiB bracketing (0.5 GiB in bands) and the sampler's lower-bound peaks. The e10361 floor was not bisected.
- Not covered: EER `--eer_upsampling 2` (8192²), `--grouping_for_ps`, `--bin_factor`/`--early_binning`, e10028 float MRC, e10164, e10641, multi-GPU.
- Wall times are informational (balloon, sampler and pinned 8-CPU lane), not benchmarks.
- D1's mechanism is inferred from call sites and a standalone reproducer, not from an instrumented product build.

## Files

- `tables.md`: full per-case and per-probe tables (generated from `cases.json`).
- `cases.json`: all 162 runs (free VRAM reading, command, exit, route, flags, wall, RSS, identity result, failure details).
- `env.txt`, `input_sha256.txt`, `log_residuals.json`.
- `logs/<case>/`: `result.json`, filtered stdout, per-movie `.log`, `time.txt`, witness; `timeline.csv` and per-movie comparator reports for the multi-movie runs. `logs/matrix*.out`: batch progress; `logs/stale_repro.out`.
- `harness/`: balloon, case runner (`qm_batch.py`), bisector, reproducer, aggregation and the batch scripts that were run.
