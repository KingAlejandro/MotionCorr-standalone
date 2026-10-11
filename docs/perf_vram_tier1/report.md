# Low-VRAM Tier 1: windowed patch spectra and scratch in dead movie buffers

Branch `perf/vram-tier1` from main `1a99da0`. Products are unchanged by
construction (identity matrix and kit identity PASS). The patch-alignment peak,
which is the movie peak, drops from 3221 to 3026 MiB (traced); wall time is not resolved.
Host 4GPUs, A100 80GB PCIe, driver 570.86.10, CUDA 12.8 (cuFFT 11.3.3).

## Design

**Windowed patch spectra.** Patch alignment reads only the CCF window of each
patch spectrum (`ccf_ny` rows × `ccf_nx/2+1` columns; 192×97 of 742×384 on the
tutorial). `cudaExtractPatchWindow` copies that window after the patch R2C and
applies the normalisation scale in the same float operation as
`scaleComplexKernel`, so every value read is bit-identical. The windowed shift
uses the original frequency coordinates (`x` unchanged, window row mapped back to
the full-patch row, full `nfx`/`nfy` in the phase), so shifted values are
identical too. The batched slots and the per-patch buffer hold windows only; the
full spectrum lives in session scratch for one patch at a time. Global alignment
is unchanged.

**Scratch in dead movie buffers** (live ranges: `docs/vram_live_ranges.md`).

| Interval | `d_Iframes` content | Read later? | Scratch placed there |
|---|---|---|---|
| ingest → forward FFT | real-space movie | yes | none |
| forward FFT → global alignment | stale movie | no, the inverse FFT rewrites every frame | global alignment buffers + cuFFT work area |
| global inverse FFT → unweighted sums | real-space movie | yes | none |
| dose weighting | real-space movie | only with `--save_noDW` / `--even_odd_split` | DW scratch when neither is set |

- The DW borrow uses the runner's existing `pre_dw_sum_needed` predicate
  (`consume_real_frames = !pre_dw_sum_needed`), not a copy.
- While `d_Iframes` is lent out, every reader (forward FFT, patch preparation,
  unweighted reconstruction, real-frame download) refuses with
  `ERROR: refusing <operation>: the device real-space movie is no longer valid`.
  The refusal does not change the #69 failure state, so recoverable failures
  still take the existing host fallback (which refreshes from
  `downloadFourierFrames`, untouched by the scratch) and fatal ones still refuse.
- Ingest scratch in `d_Fframes` was not added.

## Tests and compiled negative controls (MEASURED, GPU0, full ctest 72/72)

- `CudaPatchBatch` window equivalence: windowed per-patch and batched paths vs
  the full-spectrum per-patch path, byte for byte (shifts, RMSD/iteration logs),
  on geometries including odd `ccf_ny/2`, cropped windows, `group_frames` > 1 and
  K = 1, 4, 25; window extraction checked against a host window written from the
  frequency definition.
- `CudaVramAlias`: global arena results identical to the allocating path on a
  1280×1152 CCF whose cuFFT C2R work area is actually written (precondition
  asserted: cuFFT 11.3.3 leaves it untouched at power-of-two and small sizes);
  refusal of every real-frame reader while borrowed; DW consume mode identical
  to the allocating mode, with no allocation.
- `CudaDoseWeightAlias` (runner): borrow logged by default, absent with
  `--save_noDW` and `--even_odd_split`, DW micrograph and core header identical.
- Mutants, each must fail its test: `extract_no_remap` (wrong `ly` remap),
  `scale_divide` (scale in a different rounding order), `shift_wrong_half`,
  `perpatch_wrong_half`, `shift_retired`, `never_retire`, `arena_overlap`,
  `arena_work_over_buffers`, `refusal_off`, `dw_scratch_over_fourier`, and the
  runner mutant with the DW predicate forced on (alias with `--save_noDW`).
- Fault controls, one test change: in consume mode the DW call has no
  `cudaFree`, so `dw-release-fatal` cannot fire in the default configuration.
  Both fault scripts run that row with `--save_noDW`, where the scratch is
  still a separate allocation. The runner writes `_noDW.mrc` before dose
  weighting starts (also on main), so that one file is excluded from the
  "failed movie published nothing" check; the DW image and STAR must still be
  absent, and the injection, refusal and cleanup attribution are asserted as
  before.

## Identity matrix vs main (MEASURED, GPU1)

`cmp_trees.py`, path-normalised, 4 tutorial movies (`four.star`, gain) and the
mixed-geometry batch (`/home/alex/mc-rc/mixed`). Log: `idm.log`.

| Config | Result |
|---|---|
| default (nvCOMP, DW borrow active) | IDENTICAL 29/29 files |
| eo | IDENTICAL 37/37 |
| eo + noDW | IDENTICAL 41/41 |
| late binning 1.25, `--ingest auto`, eo + noDW | IDENTICAL 41/41 |
| late binning 1.25, DW only | IDENTICAL 29/29 |
| CPU | IDENTICAL 41/41 |
| mixed, eo + noDW | IDENTICAL 48/48 |
| mixed, DW only | IDENTICAL 33/33 |
| poison: default / eo + noDW / mixed DW | IDENTICAL 29/29, 41/41, 33/33 |
| control: main eo vs main eo + noDW | DIFFERENT (inventory) |
| control: bit flip at byte 4096 | DIFFERENT |

Borrow line in candidate default logs: 4 of 4 movies; in eo + noDW logs: 0.

## Kit campaigns (MEASURED, GPU0, kit 629fdc4, cand source 866c14f)

24 tutorial movies, `--ingest nvcomp`, 12 clean pairs each. Evidence:
`compare.json`/`provenance.json`/`kit_report.md` (default),
`*_eonodw.*` (`--save_noDW --even_odd_split`), `trace_mem_peaks.json`.

| | default | eo + noDW |
|---|---|---|
| wall verdict | not resolved: median −0.24 s, CI −0.56..+0.72 s, noise 0.64 s | not resolved: median −0.25 s, CI −0.60..+1.03 s, noise 0.81 s |
| kit product identity | PASS, 81 files | PASS, 153 files |
| NVML process peak (sampled, lower bound) | 3558 → 3362 MiB | 3558 → 3374 MiB |
| patch alignment device stage | 32.82 → 26.98 ms (−5.84, flagged) | 32.34 → 27.48 ms (−4.86, flagged) |
| global alignment device stage | 11.83 → 8.88 ms (−2.95, flagged) | 11.53 → 9.13 ms (−2.40, flagged) |

No wall-time improvement is claimed. Stage deltas are from `--profile`
passes; flags locate a change, the verdict decides wall time.

Traced device-allocation high-water per stage (`mem peak MiB`, both trace
passes agree to the MiB in every arm). The kit marks all four trace passes
CONTAMINATED: a kit bug (nsys puts the traced payload in a new session, which
the kit counted as foreign), fixed on `tools/profiling-kit` a8cbf4a. The
captures themselves are valid.

| Stage | main | cand default | cand eo + noDW |
|---|---|---|---|
| ingest | 2932 | 2932 | 2932 |
| global FFT | 2877 | 2877 | 2877 |
| global alignment | 3143 | **2877** | **2877** |
| global iFFT | 2877 | 2877 | 2877 |
| patch alignment | 3221 | **3026** | **3026** |
| dose weighting | 3117 | **2877** | **3013** |
| movie teardown | 2982 | 2877 | 2877 |
| movie peak | 3221 | **3026** | **3026** |

- Global alignment: the 266 MiB CCF workspace moved into `d_Iframes`.
- Patch alignment: the batched workspace drops 236 → 41 MiB (window-only slots).
- Dose weighting, default: the ~240 MiB DW scratch is carved from `d_Iframes`.
  With eo + noDW the scratch is still allocated (alias off, as designed). The
  104 MiB that dose weighting and teardown lose in both configurations matches
  smaller patch preparation buffers held until teardown (inferred, not traced
  per buffer).

Changed per-movie log lines (`log_memory_lines.txt`, one movie, GPU1). The
kit excludes `.log` files, so these are shown here:

| Line | main | cand |
|---|---|---|
| batched patch workspace | `workspace 236 MiB + cuFFT work 3 MiB` | `workspace 41 MiB + cuFFT work 3 MiB` |
| per-patch `Buffer VRAM` (×25) | 236.49 MiB | 41.42 MiB |
| per-patch `Peak GPU memory allocated` (×25) | 239.90 MiB | 44.83 MiB |
| global alignment | — | new: `Buffer placement: borrowed dead device memory, nothing allocated` |
| DW `Peak VRAM`, default | 135.81 MiB | 0.00 MiB, plus the new line `Dose-weighting scratch borrowed from the consumed real-space movie` |
| DW `Peak VRAM`, eo + noDW | unchanged | unchanged |


## Part B: patch R2C batch-size probe (MEASURED, GPU1)

`tests/cuda_patch_fft_batch_probe.cpp`, synthetic detector-like input. Each
row compares, bitwise, the session's batch-n plan against a batch-1 plan at the
same slot offsets and a batch-1 plan on a separate tile, each with default
plans, auto-allocation off with an explicit work area, and explicit
`inembed`/`onembed` strides. Log: `patch_fft_batch_probe.log`.

| Movie / grid | Patch sizes | n = 24, 25, 40, 50 |
|---|---|---|
| tutorial 3838×3710, 5×5 | 766×742 | identical |
| tutorial 3×3 | 1278×1236 | identical |
| tutorial 7×7 | 548×530 | identical |
| K3 5760×4092, 5×5 | 1152×818 | identical |
| Falcon 4 4096², 5×5 | 818×818 | identical |

0 of 20 rows differ in any arm or variant (0 differing words of up to 7.9e7).

**Tier 2 implication.** On this cuFFT and GPU, transforming patch tiles one at a
time gives the same bits as the batch-n plan for every production patch size
probed, so batch size does not block an exact Tier 2. Limits: one cuFFT version
and one architecture (the earlier 256×256 difference shows batch invariance is
size-dependent, so a Tier 2 PR needs this probe as a test on the versions it
supports); synthetic input; and Tier 2 also changes how real frames are produced
(per-frame C2R of the global inverse FFT instead of batch-n), which this probe
did not cover.

## UNRUN

- Full-frame C2R batch invariance for the global inverse FFT (needed by Tier 2).
- Probe on another GPU architecture or cuFFT version.
- K3 and Falcon 4 movies end to end (only their patch FFT sizes were probed).
