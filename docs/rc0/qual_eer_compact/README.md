# W-EER-Q: qualification of #196 (EER rendered on the host into uint16, compact staging)

Coordination: #198 (register item E1). Source `1db869025507ac801845b4001b84e6bc0e77a645` (main, contains #196 as `4b849165`).

## Result

- **34 of 34 strict output-tree identities pass**: 31 CUDA cases (`--ingest auto`, compact route where eligible, vs `--ingest float`) and 3 CPU-only cases (`0ac2726a` vs `1db86902`). Each case has one movie and one run per arm. Cases cover default and remainder grouping, small grouping on a subset, upsampling -1/1/2/3, with and without gain, defect files, and synthetic encodings 65000 and 65002.
- The overflow guard works and can fail: with the guard removed (negative control) the same fixture fails identity in MRC, STAR and logs; with it, `auto` logs the fallback and matches `float`, and pinned `--ingest compact` refuses with no products.
- Compact lowers **host** peak RSS by 34-39 % at upsampling 1, 43-47 % at 2 and 3. It does not change NVML device memory (the device holds the float movie on either route). No saving at upsampling -1 (see below).
- Falcon4 at upsampling 2 (144 x 8192 x 8192) **fits and passes**: 79 522 MiB device, within 1.2 % of the prediction (80 520 MiB); compact RSS 21 547 MiB vs float 40 171 MiB.
- **Defect (pre-existing, not introduced by #196): damaged EER input is accepted silently** in several forms, on both routes and on the pre-#196 CPU build. See "Failure inputs". Escalation E-1 below.
- Not run: CTest, a second GPU, SCARF, multi-movie batches of healthy movies beyond the failure batches, timing claims. Timings in the tables are single samples taken on a shared lane and carry no performance claim.

Recommended register status for E1: **GO (qualified)**. Keep GO for the compact route. Open E-1 for the damaged-input behaviour, which is independent of #196 and needs a maintainer decision.

## Provenance

| item | value |
|---|---|
| source | `1db869025507ac801845b4001b84e6bc0e77a645` via `git archive` (no `.git`); CPU base `0ac2726a` (pre-#196; also pre-#195/#178/#185/#187, so the CPU comparison covers the whole delta) |
| binaries (sha256) | CUDA+nvCOMP `f37d62ec…c84166a3`; CPU `1db86902` `99205698…c5a94c53`; CPU `0ac2726a` `ee4f11d1…f42c0bd8`; negative control `7f73d701…6a7d023a` (full values in `evidence/binary-sha256.txt`) |
| build | Release, CUDA 12.8.61 (sm_80), nvCOMP 5.3.0.16, gcc 13.3.0, libtiff 4.5.1; `-DCUDA=ON -DUSE_NVCOMP=ON` |
| host | 4GPUs VM, kernel 6.8.0-136, THP `madvise`, 124 logical CPUs |
| lane | `taskset -c 112-119`, `--j 8`, GPU2 (`GPU-063e5232-…`, A100 80GB PCIe, driver 570.86.10), `CUDA_VISIBLE_DEVICES=2 --gpu 0`; `/tmp/motioncorr-gpu2-correctness.lock` held per run |
| etiquette | after the coordinator steer, `flock -n /tmp/motioncorr-bench.lock true` is checked before every arm and the run waits (60 s polls) while W-EER-DEV holds it: 14 polls in total. **c01 and c03 ran before the check was added**; other runs overlapped no GPU0 work that I know of, but I did not log the bench-lock state for those two. |
| options | corpus config L: `--use_own --dose_weighting --dose_per_frame <family> --bfactor 150 --seed 1 --j 8 --gpu 0 --patch_x 5 --patch_y 5 --expected_frames <groups>` (config G for sparse cases), plus per-case `--eer_grouping/--eer_upsampling/--gainref/--first_frame_sum/--last_frame_sum/--defect_file/--skip_defect/--ingest`. Exact lists in `evidence/cases/*.json`. Pixel size scaled with upsampling. |
| comparator | `docs/issue85_laneC/compare_output_trees.py` (the brief's `tools/` path does not exist), complete non-PDF tree, with the route-only log lines dropped from both arms: `Staging this movie as native`, `Released native uint`, `Materialized native uint`, `EER grouping` (the last is the fallback record that `auto` adds). Every non-log product (MRC header, extended header, payload, STAR) is compared in full. |
| NVML | `nvidia-smi -lms 100` streams for the GPU2 UUID; per-process `used_gpu_memory` summed over processes in the run's own session. No foreign PIDs on GPU2 in any retained run. |
| RSS | `/usr/bin/time -v` maximum resident set |
| inputs | Corpus EER movies, SHA-256 checked against `docs/workload_corpus/corpus.md`: Falcon3 `2019-06-21_20-39-45.801…eer` `fad4d37c…`, Falcon4 `FoilHole_10919949…eer` `2a46fd61…`, 12963 movie `3fc5feb6…`, 12963 gain `6d4f3e5f…`. Synthetic and damaged fixtures: `evidence/fixture-sha256.txt`. |

Scripts: `eer_inventory.py`, `eer_synth.py`, `eer_corrupt.py`, `mkcase.py`, `eer_matrix.py`, `eer_cpu_compare.py`, `analyse_batch.py`, `summarize.py`. Raw per-case results (logs, witness files, time files, compare JSON, NVML-derived JSON) are in `evidence/results/`; per-movie STAR files, NVML streams, stdout and MRC products were not kept.

## 1. Encoding inventory

Parsed with `struct` from the IFD chain (independent of libtiff), `evidence/eer_inventory.json`.

| file | container | tag | fractions | geometry | strips/directory | bytes |
|---|---|---|---:|---|---|---:|
| Falcon3 x4 (`2019-06-21_*_eer_data_4096x4096.eer`) | BigTIFF | **65001** (7-bit RLE, 4-bit subpixel) | 2331 | 4096 x 4096 | 1 | 1.21-1.22 GB |
| Falcon4 x2 (`FoilHole_*_Fractions.mrc.eer`) | BigTIFF | **65001** | 5782 | 4096 x 4096 | 1 | 2.93 GB |
| 12963 (`FoilHole_4674725_*_EER.eer`) | BigTIFF | **65001** | 1911 | 4096 x 4096 | 1 | 0.87 GB |

Groups at the corpus defaults: Falcon3 g40 = 58 (11 fractions dropped), Falcon4 g40 = 144 (22 dropped), 12963 g49 = 39 (0 dropped).
The corpus contains no 65000 and no 65002 movie, and no 2K detector. Those encodings are covered only by synthetic movies (section 4), which show that compact and float agree on them but say nothing about real files.

## 2. Source check of #196's count bound

Claim: a pixel gets at most one count per fraction at upsampling 1 and 2, and at most four at 4K to 2K.

- **Decode.** In all three decode loops (`renderEER.cpp:427-469`, `:471-518`, `:522-560`) an electron is placed at `n_pix` after `n_pix += gap`, then `n_pix++`. Positions are therefore strictly increasing whatever the data, and a position is always `< total_pixels` because the loop breaks first. Corrupt input cannot repeat a source pixel or write out of the image.
- **Render.** Every mapping from source pixel to output pixel is injective except 4K to 2K: 4K to 4K (`:92`), 4K to 8K (`:81`, `2*sx + subpixel bit`), 4K to 16K (`:70`, `4*sx + 2 subpixel bits`), 2K to 2K (`:125`), 2K to 4K (`:103`). 4K to 2K (`:114`, `sx >> 1, sy >> 1`) merges four source pixels. So the bound is `g` at upsampling 1, 2 and 3 and `4g` at -1, as `motioncorr_runner.cpp:2344` computes. **Confirmed.**
- **Accepted `--eer_upsampling` values.** The runner does not validate the value (`motioncorr_runner.cpp:177`); `EERRenderer::read` accepts **-1, 1, 2, 3** (`renderEER.cpp:150`). 0, 4 and -2 fail with "must be -1, 1, 2 or 3" (`evidence/results/u_cli/`). A 2K detector accepts only 1 and 2 (explicit error at render, `renderEER.cpp:593`), and tag 65002 only 1 and 2 (explicit error at read, `:229`). 4K detectors with 65000/65001 accept all four. The gain loader accepts 4K gains only at upsampling 1 and 2 (`renderEER.h:149-170`); -1 and 3 with a 4K gain fail with "Unsupported gain size" (case c17).
- **Minimum groups.** The runner skips a movie with fewer than 3 groups (`motioncorr_runner.cpp:2168`). Together with a bound of `g`, the guard needs a movie of at least `3 * 65536` fractions at upsampling 1/2/3 and `3 * 16384` at -1. Real movies here have 1911-5782.
- **Stale comment.** `renderEER.h:95` says libtiff limits a movie to 65535 directories. libtiff 4.5.1 on 4GPUs reads 70 000 directories and `TIFFSetDirectory(69999)` succeeds, so synthetic movies with 196 608 fractions load. The comment is out of date for this libtiff.

## 3. Matrix (CUDA+nvCOMP build, 1 movie per case, 1 run per arm)

`evidence/results_table.md` is the generated table. Routes are the `--ingest_witness` lines; peak RSS and NVML are single samples. All rows below passed strict identity (complete non-PDF tree) unless the verdict column says otherwise.

| case | g | up | gain | groups (dropped fractions) | route auto / float | peak RSS auto / float MiB | NVML VRAM auto / float MiB | identity |
|---|---:|---:|---|---|---|---|---|---|
| c01 Falcon3 | 40 | 1 | no | 58 (11) | compact / float | 3240 / 5260 (-38 %) | 8738 / 8726 | PASS |
| c02 Falcon4 | 40 | 1 | no | 144 (22) | compact / float | 7625 / 12288 (-38 %) | 20446 / 20446 | PASS |
| c03 12963 | 49 | 1 | yes | 39 (0) | compact / float | 2358 / 3721 (-37 %) | 6116 / 6140 | PASS |
| c04 12963 | 49 | 1 | no | 39 (0) | compact / float | 2293 / 3657 (-37 %) | 6052 / 6052 | PASS |
| c05 Falcon3 remainder | 45 | 1 | no | 51 (36) | compact / float | 3016 / 4796 (-37 %) | 7774 / 7774 | PASS |
| c06 Falcon4 remainder | 37 | 1 | no | 156 (10) | compact / float | 8009 / 13056 (-39 %) | 22106 / 22106 | PASS |
| c07 12963 remainder | 47 | 1 | yes | 40 (31) | compact / float | 2392 / 3789 (-37 %) | 6278 / 6286 | PASS |
| c08 Falcon3, groups 101-140 of 2331 | 1 | 1 | no | 40 used | compact / float | 2632 / 3960 (-34 %) | 5774 / 5744 | PASS |
| c09 12963, groups 101-140 of 1911 | 1 | 1 | yes | 40 used | compact / float | 2362 / 3689 (-36 %) | 5838 / 5806 | PASS |
| c10 Falcon3 | 40 | 2 | no | 58 (11) | compact / float | 8906 / 16858 (-47 %) | 33694 / 33694 | PASS |
| c11 12963 | 49 | 2 | yes | 39 (0) | compact / float | 6390 / 11717 (-45 %) | 23222 / 23138 | PASS |
| c12 12963 | 49 | 2 | no | 39 (0) | compact / float | 6134 / 11462 (-46 %) | 22966 / 22966 | PASS |
| c13 Falcon3 | 40 | -1 | no | 58 (11) | compact / float | 2441 / 2441 (0 %) | 2342 / 2334 | PASS |
| c14 12963 | 49 | -1 | no | 39 (0) | compact / float | 1787 / 1785 (0 %) | 1892 / 1892 | PASS |
| c15 Falcon3 | 200 | 3 | no | 11 (131) | compact / float | 7492 / 13866 (-46 %) | 26850 / 26888 | PASS |
| c16 12963 | 150 | 3 | no | 12 (111) | compact / float | 7649 / 14562 (-47 %) | 29072 / 28994 | PASS |

Notes:

- Compact route was witnessed (`compact`) in every row; `float` arms witnessed `float`.
- NVML values agree between routes within a few tens of MiB (sampling noise), as expected: the compact route only changes the host staging type.
- At upsampling -1 compact gave no RSS saving in this run (the staged movie is small, 58 x 2048 x 2048). I did not investigate what sets the peak there.
- c08/c09 use `--first_frame_sum 101 --last_frame_sum 140` with `--eer_grouping 1` under config G; the log's `Movie size N` is the full group count.
- Upsampling 3 (16384 x 16384, 1 GiB float MRC per movie) completes on the GPU with grouping 150-200. Smaller groupings were not tried for memory reasons.
- Gain: c03, c07, c09, c11 pass with a 4K gain (upsampled 2x at upsampling 2 by `loadEERGain`). An 8K gain at upsampling 1 and a gain at upsampling 3 were not run.

### Defect replacement with gain (coordinator steer 1)

From source, the sparse device gather (`sparse_neighbours`, `motioncorr_runner.cpp:2948`) requires `nvcomp_ingested`, which requires `!isEER` (`:2284`). It is **unreachable for EER**. The reachable path is the host loop after `:2958`: it reads `Iframes_u16` (`:3022`), multiplies by `Igain` when `host_frames_are_raw && gain` (`:3033`), with `D_MAX = 4` for EER (`:2733`). The Gaussian branch is reached when a defect has 6 or fewer valid neighbours in the 9 x 9 window, and with GPU statistics it makes the runner log a warning and redo detection on host statistics (`:2912`).

| case | what is exercised | route auto / float | identity |
|---|---|---|---|
| c03 | natural hot pixels (78) with gain, no defect file | compact / float | PASS |
| d1 | `--defect_file`: 4 single pixels (one at the image corner), a 40-pixel row segment, plus the 78 natural hits; gain | compact / float | PASS |
| d2 | d1 plus an 11 x 11 block: Gaussian branch; log shows `WARNING: Gaussian hot-pixel replacement needs host statistics` in both arms | compact / float | PASS |
| d3 | upsampling 2, defect list scaled 2x including a 22 x 22 block; gain | compact / float | PASS |

The defect file changes the product (payload hashes of c03, d1 and d2 differ), so the identity is not vacuous. "Detected N hot pixels" counts only new hits (78 in all of c03, d1, d2), not the defect-file pixels.

### Other encodings (synthetic, 240 fractions, g40, config G)

| case | tag, detector | up | route auto / float | RSS auto / float MiB | identity |
|---|---|---:|---|---|---|
| x1 | 65000 (8-bit RLE), 4K | 1 | compact / float | 394 / 634 | PASS |
| x2 | 65000, 4K | -1 | compact / float | 214 / 274 | PASS |
| x3 | 65002 (detailed, 2-bit subpixel), 2K | 1 | compact / float | 193 / 252 | PASS |
| x4 | 65002, 2K | 2 | compact / float | 369 / 607 | PASS |
| x5 | 65001, 2K | 2 | compact / float | 369 / 610 | PASS |

The movies are random electron positions, made by `eer_synth.py` (seeded). They only test that the two routes agree.

## 4. Overflow guard

Fixtures are synthetic (`eer_synth.py`): one pixel (or, at -1, the four merging source pixels) is hit in every fraction, so a group of `g` fractions counts `g` (or `4g`) at one output pixel. Three groups, `--skip_defect` so the hot pixel is not replaced, config G. Arms: `auto`, `float`, pinned `compact`.

| case | detector, up | g | max count | auto route | auto vs float | pinned compact |
|---|---|---:|---:|---|---|---|
| o2 | 4K, -1 | 16383 | 65 532 | compact | PASS | runs, route compact |
| o1 | 4K, -1 | 16384 | **65 536** | **float**, log `EER grouping 16384 at upsampling -1 can exceed 65535 counts per pixel; using the float movie.` | PASS | **exit 1**, `--ingest compact was requested but the compact native staging did not apply`, no MRC/STAR |
| o3 | 2K, 1 | 65535 | **65 535 (exact)** | compact | PASS | runs, route compact |
| o4 | 2K, 1 | 65536 | **65 536** | float, same log line | PASS | exit 1, no products |
| o5 | 4K, **2 (8192 x 8192)** | 65536 | **65 536** | float, same log line | PASS | exit 1, no products |
| o1n | 4K, -1, **guard removed** (`src-noguard`, one-line patch in `evidence/noguard.diff`) | 16384 | 65 536 | compact | **FAIL**: MRC, STAR, log and EPS differ | not run |

- The exact boundary is covered twice: 65535 at upsampling 1 fits and matches (o3); at -1 the largest fitting group is 16383 (65532, o2) and 16384 overflows (o1).
- The negative control shows the identity gate can fail for the defect the guard prevents (uint16 wrap of 65536 to 0). Without the guard the wrapped compact product differs from float.
- Pinned compact refused in o1, o4 and o5 with no MRC and no STAR in the output tree (`movie.log` only); the batch exit code was 1. In o2 and o3 the pinned arm ran on the compact route; its products were not separately compared with `auto` (same route).
- **Reachability.** At upsampling 1, 2 and 3 the guard needs `g >= 65536` and 3 groups, so at least 196 608 fractions; at -1 it needs `g >= 16384` and 49 152 fractions. The corpus movies have 1911-5782. The guard is reachable only with absurd grouping or synthetic movies. Note `--eer_grouping 65536` is above the largest real fraction count, so such a run would normally be skipped for too few groups.
- Cost of the fallback: o4 and o5 `auto` (float route) decode every fraction once and take the same time as `float` (wall times in the results, single samples).

## 5. Failure inputs

Batches of three movies from Falcon3: healthy A, damaged copy of A, healthy B; config G, `--expected_frames 58` unless noted; arms `auto` (compact) and `float`. `evidence/batch_analysis.json` holds the per-movie product list and payload hashes. Healthy movies' MRC payloads are identical across routes and across all batches.

| case | damage | exit | movie 2 | joint STAR | compact vs float |
|---|---|---:|---|---|---|
| b1 | file cut at 60 % | **1** | **fails** (`frame count mismatch: expected 58 frames, but decoded 34 frames`); no MRC/STAR for it; movies 1 and 3 complete | not written | same |
| b2 | 4096 random bytes in frame 500's strip | **0** | **completes, no warning**; product differs from the healthy copy | written, lists all 3 | same payloads |
| b3 | frame 700's strip set to 0xFF | **0** | completes with `WARNING: The number of pixels is not right ... frame 701 ... This frame is skipped.`; product differs | written | same payloads, same warning |
| b4 | frame 900's strip set to 0x00 | **0** | as b3 (frame 901) | written | same |
| b5 | file cut at 60 %, **no `--expected_frames`** | **0** | **completes with 34 groups instead of 58**, no warning | written | same |
| b6 | 12963 twice, 2048 x 2048 gain (wrong dimensions) | **1** | both movies fail, `Unsupported gain size in EERRenderer::loadEERGain()`; no MRC/STAR | not written | same |
| c17 | 12963, up -1, 4K gain | 1 | same message | not written | same |

- The explicit-failure expectation holds for b1 (when `--expected_frames` is given), b6 and c17: failure for the movie, no false completion STAR, healthy movies in b1 complete, non-zero exit, no crash, and compact and float behave identically.
- It does **not** hold for b2-b5: the damaged movie is published as if healthy and the batch exits 0. b3/b4 print a warning to stderr only. The same results come from the pre-#196 CPU build (`0ac2726a`) and from `1db86902` CPU (`evidence/inherited_damaged_cpu.txt`: ff, random, truncated: exit 0, 58/58/34 groups, same warning counts). The code is unchanged since the RELION extraction: `renderEER.cpp:566` skips the frame with a warning, `:242` takes whatever directory count libtiff reports, and `lazyReadFrames` ignores the return value of `TIFFReadRawStrip` (`:326`).
- #196 does not alter any of this, and the compact route inherits it exactly.

## 6. Memory edge: Falcon4, upsampling 2

Prediction was written before the run (`memory_prediction.md`) from the c01/c02/c10 NVML peaks: device `2.127 x movie_float + 4 x 423 + 419 MiB`, host `staging + file buffer + overhead`.

| case | predicted device MiB | measured NVML MiB | predicted RSS compact / float MiB | measured RSS compact / float MiB | result |
|---|---:|---:|---|---|---|
| m2: groups 1-100 | 56 560 | 56 164 | - | 15 913 / 28 905 | PASS, identity |
| m1: all 144 groups (8192 x 8192) | 80 520 | **79 522** of 81 920 | 21 500 / 40 500 | **21 547 / 40 171** | PASS, identity |

The full movie fits with about 2.3 GiB to spare on an 80 GB card, so the out-of-memory path was not exercised. The failure behaviour at the limit is therefore UNRUN for this input. A host-side cap on a smaller card, or the pinned `float` route with a larger movie, would hit it; the existing CUDA out-of-memory test (`tools/test_cuda_oom_behavior.py`) is not part of this package.

## 7. CPU-only build (`1db86902` vs `0ac2726a`)

CPU lane `taskset -c 112-119`, `--j 8`, no GPU. Complete non-PDF tree comparison, same comparator. 3 of 3 pass.

| case | movie, options | identity |
|---|---|---|
| cc1 | Falcon3, g40, up 1, config L | PASS |
| cc2 | 12963 with gain, g49, up 1, config L | PASS |
| cc3 | Falcon3, g40, up -1, config G | PASS |

The CPU delta `0ac2726a..1db86902` includes #195, #178, #185, #187 as well as #196, so this shows the whole composition leaves EER CPU products unchanged. #196's route only exists in the CUDA build.

## Limitations and UNRUN

- One movie per case, one run per arm. Determinism is not measured here, so no variability is reported; no timing or speedup claim is made.
- UNRUN: CTest on this SHA (owned by W-QUAL), multi-GPU, SCARF, the out-of-memory failure path, an 8K gain at upsampling 1, EER legacy (non-TIFF) files, real 65000/65002/2K movies, multi-movie batches with `--j` above the movie count and `--max_io_threads` limits, `--ingest nvcomp` on EER (refuses by design; not run).
- The synthetic movies share three strips across fractions to keep files small; they test count bounds and route agreement, not alignment quality.
- The bench-lock check was added mid-programme (c01, c03 ran without it); the first queue also produced unusable NVML values from a sampler that missed short runs, and those runs were discarded and repeated (`results_old_sampler` is not retained).
- The first manifests for o1, o1n, o2 (and a log-line allowance for o4) were wrong; the cases were re-run and only the re-runs are reported.

## Defects and escalations

| id | where | what | decision needed |
|---|---|---|---|
| E-1 | `renderEER.cpp:566`, `:242`, `:326` (inherited, unchanged since extraction) | A damaged EER strip (bytes, zeroed, 0xFF) or a file truncated in the directory chain yields a published product and exit 0; only an all-0xFF/0x00 strip prints a stderr warning, random bytes print nothing, and a truncated file silently loses groups unless `--expected_frames` is passed. Affects compact and float equally and the pre-#196 build. | Maintainer: treat as part of the malformed-input trust policy (#134/D1), or fix separately. Fixing it changes inherited RELION behaviour (see the parity-divergence rule), so it needs sign-off. |
| D-1 | `renderEER.h:95` | Comment says libtiff caps a movie at 65535 directories; libtiff 4.5.1 here has no such limit. Cosmetic. | none |
| D-2 | `renderEER.cpp:593` | "upsamle" typo in two error messages (`:584`, `:593`) and "upsamling" at `:229`. Cosmetic. | none |
