# Single-GPU release candidate: integration evidence

Branch `integrate/single-gpu-rc`. Campaign code head `c0f82c2` (tree `02bc7e0`). Code head for merge: `17877c4` = `c0f82c2` + `50889a6` (validation-parser fix, tools only) + #162's pool eviction fix (`6446559`, `be70fa5`), revalidated below ("Revalidation at 17877c4"). The eviction change only acts when the frame geometry changes during a run, which the 24-movie kit workload never does, so the kit campaigns at `c0f82c2` were not repeated.
Host 4GPUs: A100 80GB PCIe GPU0 `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, payload CPUs 96-103, runner CPUs 120-121, driver 570.86.10, CUDA 12.8, THP madvise.
Every result below is MEASURED unless marked UNRUN.

## Composition

| step | commit | parents | content |
|---|---|---|---|
| `main` | `9d14275` | | baseline (#154 profiler, #155 allocator) |
| #159 | `341dd54` | | host/device overheads; base of A, B, C |
| A (#160) | `867c560` | `341dd54` + `41b50be` | batched patch alignment, K=4 |
| C (#163) | `26bc1a1` | `867c560` + `e4b68ca` | out-of-place DW, one wait per FFT, shared reconstruction scratch |
| B (#164) | `dfca087` | `26bc1a1` + `db2af3d` | pipelined chunked nvCOMP ingest (`integrate/abc-profiling`) |
| #162 | `57b0b9a` | `dfca087` + `8ca28de` | profiler safety, `FrameBufferPool` |
| #166 | `c0f82c2` | `57b0b9a` + `93c3897` | `--profile_device_timing 0` |
| #162 fix | `17877c4` | `50889a6` + `be70fa5` | pool evicts a stale geometry when the current one is released into a full pool (Codex P2) |

Leave-one-out variants (local throwaway branches, not pushed): `c0f82c2` plus `git revert -m 1 <merge>`. All three reverts applied without conflicts.

| variant | revert | commit | tree |
|---|---|---|---|
| RC−A | `867c560` | `b20f514` | `06914e8` |
| RC−B | `dfca087` | `6447376` | `c56a771` |
| RC−C | `26bc1a1` | `e583caf` | `6e314c3` |

Lines added per component (`git diff --numstat` of the merge against its first parent):

| component | src | tests | docs | cmake |
|---|---|---|---|---|
| A (#160) | +653/−52 | +564 | +148 | +45 |
| C (#163) | +154/−44 | +251/−14 | +161 | +1 |
| B (#164) | +499/−122 | +259/−29 | +210 | +1/−1 |
| #162 | +362/−63 | +322/−20 | +55/−55 | +8 |
| #166 | +12 | +44 | +14 | +4 |

## Binaries and build

`scripts/build.sh`: `cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON -DCUDA=ON -DUSE_NVCOMP=ON -DNVCOMP_ROOT=<nvcomp 5.3.0.16 cuda12>`, built with `-j15` under `flock /tmp/motioncorr-build.lock taskset -c 104-118 nice -n 5`. The CPU-only build adds `-DCUDA=OFF` and drops the nvCOMP options.

| arm | source | binary sha256 (16) |
|---|---|---|
| main | `9d14275` | `c73168a5ca85f908` |
| abc (`dfca087`) | `dfca087` | `b94e835e6cec8ade` |
| rc | `c0f82c2` | `ff1bc2679a040bc9` |
| rc−A | `b20f514` | `473c07e60713e519` |
| rc−B | `6447376` | `2b37c5f5ee468543` |
| rc−C | `e583caf` | `5f5b93294ae51d82` |
| rc CPU-only | `c0f82c2` | `f1c676924da466d1` |

## Campaigns

Kit: `tools/profiling-kit` `d873993` (PR #165). Command (`scripts/campaign.sh`), one campaign at a time, base first:

```
mcprof.py compare <base>=<bin> <cand>=<bin> --data /home/alex/mc-perf-20261001/data --cpus 96-103 \
  --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --lane-wait 600 \
  --settle-timeout 600 --pairs 12 --max-rounds 20 --profile-pass 3 --trace-pass 2 --work <fresh> \
  --source <base>=<src> --source <cand>=<src> -- --use_own --dose_weighting --dose_per_frame 1.277 \
  --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp
```

Input: the 24 tutorial movies (`movies.star` sha256 `fb998f70b375a4eb`). Each subdirectory keeps `report.md`, `compare.json`, `provenance.json`, `identity.json` and the trace-pass timelines (`timeline_<arm>_p0N.json.gz`); run outputs, Nsight reports and profiles were deleted for disk space.

| campaign | base → candidate | rounds run/kept | verdict | median B−A s (CI ≥95%) | noise s | wall med s | CPU med s | peak RSS MiB | VRAM NVML MiB | trace HW MiB | kit identity |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `rc_vs_main` | main → rc | 15/12 | **resolved faster** (−22.54%) | −2.114 (−2.689..−1.086) | 1.148 | 9.379 → 7.100 | 17.009 → 17.822 | 642 → 368 | 3512 → 3558 | 3236 → 3221 | PASS, 81 files, 24 MRC |
| `rc_vs_dfca087` | abc → rc | 13/12 | not resolved (below noise 1.271) | −0.193 (−0.972..+0.990) | 1.271 | 7.303 → 7.182 | 18.467 → 18.102 | 441 → 368 | 3558 → 3558 | 3221 → 3221 | PASS, 81, 24 |
| `loo_noA` | rc−A → rc | 14/12 | not resolved (below noise 0.549) | −0.171 (−1.127..−0.030) | 0.177 | 7.304 → 7.148 | 18.173 → 18.150 | 368 → 368 | 3476 → 3558 | 3143 → 3221 | PASS, 81, 24 |
| `loo_noB` | rc−B → rc | 12/12 | not resolved (below noise 0.683) | −0.238 (−0.399..+0.508) | 0.683 | 7.565 → 7.328 | 15.482 → 18.820 | 567 → 368 | 3558 → 3558 | 3285 → 3221 | PASS, 81, 24 |
| `loo_noC` | rc−C → rc | 13/12 | not resolved (below noise 0.695) | −0.336 (−1.296..+0.094) | 0.672 | 7.685 → 7.310 | 19.856 → 18.406 | 368 → 368 | 3558 → 3558 | 3221 → 3221 | PASS, 81, 24 |

Kit warnings: `rc_vs_main`, main alone triggered 2 of 3 discards (foreign CPU on the lane); `rc_vs_dfca087`, kept orders unbalanced (AB 7, BA 5); `loo_noA`, rc alone triggered 2 of 2 discards. `loo_noA` has a CI that excludes zero but |median| 0.171 s is below the noise 0.177 s, so it is not resolved.

Wall, CPU and RSS come from unprofiled runs (wait4); VRAM "NVML" is the sampled per-process peak (lower bound, includes the CUDA context); "trace HW" is the Nsight device-allocation high-water of the trace passes. Per-component deltas are not additive: every arm contains #159 and the other components.

`main` and `dfca087` have no `--profile_device_timing`, so their trace passes run with CUDA device timing on, while binaries containing #166 run with it off. Device-side sync counts in `rc_vs_main` and `rc_vs_dfca087` therefore include the base arm's timing waits. The leave-one-out variants all contain #166, so those campaigns have device timing off in both trace arms.

## Stage deltas

Profiled (`--profile`, 3 passes per arm, steady-state median per movie; `*` = flagged by the kit). Trace rows are Nsight per-movie deltas (2 passes per arm).

| campaign | movie wall ms | flagged profile stages (ms) | flagged trace deltas (per movie) |
|---|---|---|---|
| `rc_vs_main` | 276.1 → 230.6 (−45.5 *) | allocate host sum −10.66, allocate reconstruction −5.24, global ifft −1.91, patch alignment −14.23, fix defects +0.80 | patch alignment −489 syncs; dose weighting −100 syncs, −1304 MiB copies; global fft −24 syncs (main has device timing on) |
| `rc_vs_dfca087` | 237.8 → 236.0 (−1.7) | none | dose weighting −72 syncs, global alignment −15 syncs (abc has device timing on) |
| `loo_noA` | 250.6 → 228.2 (−22.5) | patch alignment −13.77 | patch alignment −191 syncs, −2 mallocs |
| `loo_noB` | 243.5 → 233.1 (−10.4) | session and device ingest −11.25 (minflt −288 flagged, wall not), fix defects +0.74 | session and device ingest idle −12.1 |
| `loo_noC` | 244.9 → 233.3 (−11.6) | global ifft −1.49 | global fft −24, global ifft −23, dose weighting −28 syncs; dose weighting −1304 MiB copies, −4 mallocs |

Stage flags locate a change; only the wall verdict decides it. The +0.8 ms `fix defects` cost appears in both `rc_vs_main` and `loo_noB`, so it comes with B.

## Product identity

Kit check (every campaign, round 1 only): MRC core header (bytes 0-223), extended header and payload (bytes 1024 onwards) and file length; STAR/EPS byte-equal after path normalisation; per-movie `.log` files excluded (timing values); PDFs inventoried but not compared (Ghostscript dates); MRC label bytes 224-1023 excluded. This is regression evidence against the base binary, not scientific certification.

Extended matrix, `main` vs `rc`, movies 00021-00024, `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8`, same comparison rule as the kit (`identity/cmp_trees.py`). Scripts and raw output in `identity/`.

| config | extra options | rc arms | result |
|---|---|---|---|
| GPU eo | `--gpu 0 --ingest nvcomp --even_odd_split` | rc | IDENTICAL, 12 MRC + 17 other, 4 PDF inventoried |
| GPU eo + noDW | `... --even_odd_split --save_noDW` | rc, `MOTIONCORR_FRAME_POOL_POISON=1`, `MOTIONCORR_FRAME_POOL=0` | IDENTICAL, 16 MRC + 17 other each |
| CPU | `--even_odd_split --save_noDW` (no `--gpu`) | rc, poison | IDENTICAL, 16 MRC + 17 other each |
| early binning | `--gpu 0 --ingest auto --bin_factor 1.25 --even_odd_split --save_noDW` | rc, poison | IDENTICAL, 16 MRC + 17 other each |
| late binning | as above + `--no_early_binning` | rc, poison | IDENTICAL, 16 MRC + 17 other each |

- `--bin_factor 2` is not usable on this data: 3838×3710 bins to odd dimensions and both `main` and `rc` exit 1 ("dimensions of the image after binning must be even"). 1.25 gives 3070×2968.
- `--ingest nvcomp` fails closed with binning in both binaries ("device ingest did not run"), so the binned rows use `--ingest auto`.
- `run_idm.sh` phase 1 ran `--bin_factor 2` with `--ingest nvcomp` (fails closed in both binaries) and `run_idm2.sh` phase 2 with `--ingest auto` (odd dimensions in both); `run_idm3.sh` phase 3 is the bin 1.25 run reported above.
- In `identity/summary.txt` the phase-3 rows are labelled `bin2`/`bin2late` because `run_idm3.sh` reused the directory names; they ran with `--bin_factor 1.25`.
- Comparator controls: `eo` vs `eo_nodw` on `main` reports DIFFERENT (inventory: missing `_noDW` files); early vs late binning on `main` reports DIFFERENT (MRC content).

## Revalidation at 17877c4

After merging #162's eviction fix (MEASURED, 4GPUs GPU0, `identity/validate_17877c4.txt`):

- Native: CUDA `ctest` 62/62, CPU-only `ctest` 44/44.
- Identity vs `main` with the same comparison rule: GPU eo, GPU eo + noDW (also with pool poison), late binning 1.25, CPU, all IDENTICAL.
- New **mixed-geometry** batch (`full, 2048x2048 crop, crop, full, full`, no gain, `--even_odd_split --save_noDW`), so the pool fills with one size and the geometry changes twice: GPU rc, GPU with pool poison, GPU with the pool disabled, and CPU are all IDENTICAL to `main` (20 MRC + 19 other each).
- Comparator control (main eo vs main eo + noDW): DIFFERENT.

## Native suites

- CUDA build, `ctest` on GPU0 under `/tmp/motioncorr-gpu0-correctness.lock`: 62/62 passed, none skipped. Includes the fault, fallback and fail-closed suites (`WriteFaults*`, `OutputStageFaults`, `ImageWriteFaults`, `CudaFaultMatrix`, `CudaPreprocessingFailurePaths`, `CudaNvcompAcceptance*`, `CiFailClosedControls`) and A's in-tree mutants `CudaPatchBatchMutant_*`.
- CPU-only build (`-DCUDA=OFF`), `ctest` on CPUs 64-71: 44/44 passed.

- Codex P1 on #167, ctest `CudaValidationParser`: `tools/run_cuda_patch_validation.py` did not parse the `Batched alignment:` patch block that A writes, so the CUDA patch validation gate saw 0 patch profiles on the default batched path. Fixed in the parser; `tools/test_cuda_patch_validation_parser.py` now builds a batched block from the source literals. Control: with only the parser reverted, the test fails (`batched: parsed patches=0`). On four real RC movie logs (`59249c2` binary, 5x5 patches, batches of 4,4,4,4,4,4,1) the old parser found 0/25 patch blocks per movie and the fixed one 25/25. `total_patch_gpu_ms` counts each batch total once.

## Compiled negative controls

`scripts/mutants.sh` on `c0f82c2`; each mutant is one `sed` edit, rebuilt and run against one test on GPU1. Log: `scripts/mutants.log`.

| mutant | component | test | result |
|---|---|---|---|
| pool retains never-requested sizes | #162 | FrameBufferPool | DETECTED (2 checks fail) |
| no same-size in-place keep | #162 | FrameBufferPool | DETECTED (2 checks fail) |
| no owner check in stage profile | #162 | StageProfileThreads | DETECTED (SegFault) |
| per-frame device wait in forward FFT | C | CudaDoseNormalization | DETECTED |
| Adler check skipped | B | CudaNvcompAcceptanceFailures | DETECTED |
| packed-span spread from wrong source | B | DeflateLayout | DETECTED |
| A: `CudaPatchBatchMutant_shift_retired`, `_never_retire` | A | in-tree, part of ctest | DETECTED (tests pass by detecting) |

## UNRUN

- Timing of the CPU path, and of any configuration other than the kit's 24-movie GPU `--ingest nvcomp` workload.
- Multi-GPU or multi-process runs.
- Identity with `--bin_factor 2` (not possible on this data) and with binning under `--ingest nvcomp` (fails closed in both binaries).
- Identity for late binning without `--save_noDW`, and for `--float16` output.
- compute-sanitizer runs.
- Downstream scientific validation (FSC/B-factor). Products are byte-identical to `main` in the configurations above, so they inherit `main`'s validation; this was not re-run.
- The open Codex P2 on #162 (evict stale geometries when the pool is full) is not addressed here: with four buffers of one geometry in the pool, buffers of a later geometry are not retained. Memory stays bounded at four buffers; only reuse is lost.
