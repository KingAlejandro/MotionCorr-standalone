# PR #90 (issue #85) — evidence verdict matrix

Gathered 2026-09-27. **Evidence only: no merge, no production source change.**

## Pinned identity

| | value |
|---|---|
| PR #90 code head | `676f7632822b86bba25ead05a824084c2c0631d5` |
| base (main) | `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26` |
| PR #90 HEAD tree | `d55bcf870c8944999a0b23005f08d1b3cc381d4a` |
| main HEAD tree | `fbe9469af3401d618fca0698ccd6f120d335679f` |

On every machine used, `git write-tree` on the staged working tree equals
`rev-parse HEAD^{tree}`, and `git status --porcelain -uno` is empty — the only
untracked entry is the out-of-source build directory. Nothing was compiled from
a path that differs from the code head. See
`raw/cpu/source-tree-identity-cpu.txt` and the `sha256sum` blocks at the head
of each SCARF job log.

| binary | sha256 |
|---|---|
| main, CPU | `28918ae8438f1e953eda6648d6178544fc3b431158c41cf9907d67f3d8513a1d` |
| pr90, CPU | `993cc44000c6e26afaa1b89ac9e33645c744618784b228ee32624767390b7c12` |
| main, CUDA | `1d4dd13cb675b6bb563787070ed209e9479f9b4b9f0a7f1a170c816f387d80b8` |
| pr90, CUDA | `6bbc260628a056d63bb37dd0e0f3563f7e7176a8704d068b87753158d7973699` |

Build configuration, CPU: `Release`, `CUDA:BOOL=OFF`, `TIMING:BOOL=ON`,
`/usr/bin/c++`, no extra `CMAKE_CXX_FLAGS`. CUDA: `Release`, `CUDA:BOOL=ON`,
`sm80`, `TIMING:BOOL=ON`, CUDA 12.8.0, configured and built inside the
allocation (`raw/cuda/configure-cuda-*.log`).

The harness copies in `harness/` are the ones that ran, verified by digest
against the executing machine rather than assumed:

| harness file | md5 |
|---|---|
| `compare_outputs.py` | `e2dfd9c828be5303243a7d82c30ecf62` |
| `timing_blocks.py` | `bfedcf465760db0ca5c4f8c697176773` |
| `compare_decoded.py` | `20e5ceb53fe0d21853e39c5d63a6ce5a` |
| `dump_decoded_movie.cpp` | `470bfaa452bed6bc58f1b5df676d5493` |
| `ab_j1.sh` | `0afcec01fb31968376aeb82ca89bb011` |
| `ab_j4_and_timing.sh` | `8c3ec0867a0d9060091fc2ca5f9714fc` |
| `cpu_selfcontrol.sh` | `008c79a119f8136ddb8cb2e54f803581` |
| `contention_sampler.sh` | `0957a0d51fa185a2ba5dd95eaf9b6371` |
| `build_harness.sh` | `571c93c88c27717832d5274af7e1c154` |
| `scarf_gpu_job.sbatch` | `1a408a769394a524ffc8dd65cd9f203b` |
| `gpu_selfctl.sbatch` | `f6ed4fae61f066cfe678a75a7ed5e600` |

That is every file in `harness/`, not a selection. `compare_outputs.py` is also
recorded by sha256 inside each JSON it produced
(`cb37991af515c5529f31ac48adb157771b1ac21b8308ba28735362f36085e46b`), so a
report cannot be paired with a comparator it did not come from.

## Verdict matrix

| # | acceptance item | backend | verdict | evidence |
|---|---|---|---|---|
| 1 | decoded buffer ordered-pixel identity | CPU | **PASS** | `raw/cpu/decoded_pixel_identity.json` |
| 2 | decoded buffer ordered-pixel identity | CUDA | **PASS** | `raw/cuda/decoded_pixel_identity_cuda.json` |
| 3 | corrected pixels exact, 24 tutorial movies | CUDA | **PASS** | `raw/cuda/pr90_outputs_cuda_j8.json` |
| 4 | complete headers, STAR, trajectories, auxiliary products | CUDA | **PASS graded / see §4 for auxiliary** | same |
| 5 | negative controls fire | CPU + CUDA | **PASS** | per-case `controls` blocks |
| 6 | native CUDA execution witness | CUDA | **PASS** | §5 |
| 7 | unit suite at the code head | CPU | **PASS** | `raw/cpu/ctest-cpu-all-heads.log` |
| 8 | unit suite on CUDA hardware | CUDA | **PASS** | `raw/cuda/ctest-cuda-pr90.log` |
| 9 | corrected pixels exact, 24 tutorial movies | CPU `--j 1` | **PASS** | `raw/cpu/pr90_outputs_j1.json` |
| 9b | main-vs-main control at the same settings | CPU `--j 1` | **PASS (graded), same 4 aux** | `raw/cpu/selfcontrol_main_vs_main_j1.json` |
| 10 | corrected pixels exact, 24 tutorial movies | CPU `--j 4` | **PASS (graded), same 4 aux** | `raw/cpu/pr90_outputs_j4.json` |
| 11 | interleaved paired timing, 3 blocks | CPU `--j 8` | **MEASURED — not a PASS, see §11** | `raw/cpu/pr90_timing_blocks.json` |
| 12 | same-backend A/B at a non-pinned host | — | **UNRUN, deliberately** | §12 |

## 1–2. Decoded buffer ordered-pixel identity

This is the reviewer's finding on PR #90 answered directly. The in-tree TIFF
test compares **row sums**, which cannot see two pixels exchanged inside a row.
The harness (`harness/dump_decoded_movie.cpp`, `harness/compare_decoded.py`)
dumps the decoded `MultidimArray<float>` in `DIRECT_NZYX_ELEM` order straight
out of the reader and compares the two builds bit for bit.

CPU, 5 cases, **740,431,779 pixels compared, 740,431,779 matched, 0 differing**:

| case | geometry | pixels |
|---|---|---|
| `u16_deflate_rps1` | 29×37×3, deflate, 1 row/strip | 3,219 |
| `u16_raw_rps7` | 16×50×2, raw, 7 rows/strip | 1,600 |
| `packed4bit_k2sr` | 7420×7676×1, IMOD packed 4-bit | 56,955,920 |
| `real:20170629_00021_frameImage` | 3710×3838×24 | 341,735,520 |
| `real:20170629_00035_frameImage` | 3710×3838×24 | 341,735,520 |

The three synthetic geometries are the ones `tests/test_tiff_read.py` itself
declares; the fixture writer is hashed into the report
(`85bfa60d3554b3277ab704ff5f8f33e50ad893d71f72a827bcba783b2f6573ae`) so the
fixtures are traceable. CUDA-enabled builds: 4 cases, **398,696,259 pixels
compared and matched**.

The decisive control, present on every case:

```
"perm_row_sums_unchanged": true,
"perm_detected": true,
"perm": { "pixels_differing": 2, "first_differing_index": 1595, ... }
```

A permutation that leaves every row sum untouched is invisible to the in-tree
check and is caught here. `bitflip_detected` and `missing_detected` are also
true on every case, so the comparator is not merely returning "identical".

## 3–4. Twenty-four-movie same-backend A/B on CUDA

`main` and the PR #90 head, same exclusive A100 allocation, same options
(`--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
--bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --gpu 0`), same input,
complete 24-movie tutorial inventory.

```
artifacts_total 109   artifacts_pass 105   artifacts_fail 4
corrected_images_compared 24   corrected_images_pass 24
total_pixels_compared 341735520
star_files_compared 25
per_movie_exact_gate_pass 24 / 24
controls_all_detected true
overall_graded PASS   overall_auxiliary FAIL
```

What the 109 artefacts actually are, so "109" is not doing unexamined work:

| kind | count | extensions |
|---|---|---|
| `corrected_image` | 24 | 24 `.mrc` |
| `metadata` | 25 | 25 `.star` |
| `auxiliary` | 60 | 24 `.log`, 30 `.eps`, 4 `.pdf`, 2 `.lst` |

The 30 `.eps` are the 24 per-movie `_shifts.eps` motion trajectories plus 6
aggregate plots, and **all 30 pass** — the trajectories are compared, not
merely produced. The only failures anywhere are the 4 `.pdf`.

Corrected images are bitwise identical over 341,735,520 pixels. Headers are
compared in full, including the 224–1024 label block, with the RELION clock
stamp in the first 80-byte label normalised — that normalisation is disclosed
in `normalization_patterns` inside the JSON rather than applied silently.
All 24 per-movie comparisons additionally pass the in-tree comparator at
`--gate exact --require-complete-coverage`; the existing comparator definitions
are reused and no threshold was relaxed.

### §4. The four auxiliary artefacts that differ, and why they are not PR #90's

The four failures are the four PDFs: `header.pdf`, `batch.pdf`,
`all_batches.pdf`, `logfile.pdf`. Inflating their Flate streams shows exactly
what differs:

* Ghostscript's `CreationDate`, `ModDate`, XMP `CreateDate`/`ModifyDate` and
  its generated `DocumentID` uuid — clock and container, not result;
* the **absolute path of the `_shifts.eps` file, drawn as visible text in the
  plot**, and the text-matrix offset that follows from that string's rendered
  width:

```
- 1 0 0 1 17.0551 700 Tm
- (/scratch/.../ab-pr90/out_main_j8/Movies/20170629_00021_frameImage_shifts.eps)Tj
+ 1 0 0 1 18.3906 700 Tm
+ (/scratch/.../ab-pr90/out_pr90_j8/Movies/20170629_00021_frameImage_shifts.eps)Tj
```

The coordinate is a consequence of the glyph widths of the directory name, so
no normalisation regex can remove it: any two runs writing to two differently
named directories will differ here. Rather than loosen the comparator, the
question was settled with a **control** — `main` against `main`, the same
binary run twice into two directories on the same allocation:

```
main vs main, CUDA, 24 movies
artifacts_total 109   artifacts_pass 105   artifacts_fail 4
auxiliary_fail 4      corrected_images_pass 24/24
overall_graded PASS   overall_auxiliary FAIL
```

Identical to the PR #90 result, down to the count. The auxiliary FAIL is the
floor of this comparison, not a signal from the change. It is reported as FAIL
anyway, in its own `overall_auxiliary` field, because a comparator that hides
a difference it cannot explain is worse than one that reports a difference it
can. Raw: `raw/cuda/selfcontrol_main_vs_main_cuda_j8.json`.

The same control was run independently on the CPU backend at `--j 1`, on a
different machine, and lands in the same place:

| comparison | backend | artefacts | images | pixels | exact gate | graded | auxiliary |
|---|---|---|---|---|---|---|---|
| pr90 vs main | CUDA j8 | 105/109 | 24/24 | 341,735,520 | 24/24 | PASS | FAIL (4 PDFs) |
| main vs main | CUDA j8 | 105/109 | 24/24 | 341,735,520 | 24/24 | PASS | FAIL (4 PDFs) |
| pr90 vs main | CPU j1 | 105/109 | 24/24 | 341,735,520 | 24/24 | PASS | FAIL (4 PDFs) |
| main vs main | CPU j1 | 105/109 | 24/24 | 341,735,520 | 24/24 | PASS | FAIL (4 PDFs) |

Four comparisons, two backends, two machines; the four failing paths are the
same four PDFs in every one, including the two where the binary on both sides
is byte-identical. Raw: `raw/cpu/selfcontrol_main_vs_main_j1.json`.

## 5. Native CUDA execution witness

Compile-only evidence is not counted. Four positives and two negatives:

**Positive.** Every run prints `Using CUDA acceleration on GPU device 0 for
global alignment.` (`raw/cuda/run-*.stdout`). `nvidia-smi
--query-compute-apps=pid,process_name,used_gpu_memory` sampled every 2 s
*during* each run names the `motioncorr` binary resident on the device —
15 / 12 / 14 samples at 428–3262 MiB for main / pr90 / pr91
(`raw/cuda/gpu-sample-*.txt`). `ldd` shows `libcudart.so.12` and
`libcufft.so.11` from CUDA 12.8.0 on all three binaries
(`raw/cuda/cuda-linkage.txt`). `ctest -R Cuda` →
`CudaWrapperUploadFailure` passes on the hardware in 1.61 s
(`raw/cuda/ctest-cuda-pr90.log`).

**Negative.** `--gpu 99` on the CUDA build exits 1 with
`Invalid GPU device ID 99. Found 4 CUDA device(s).`
(`raw/cuda/negctl-bad-device.log`) — the device count cannot be reported
without a device. And all three **CPU** builds (`CUDA:BOOL=OFF`, zero CUDA
libraries linked) reject `--gpu 0` with exit 1 and
`--gpu was specified with --use_own, but MotionCorr was built without CUDA
support (-DCUDA=ON).` (`raw/cpu/cpu_negative_control_gpu.log`) — so the
acceleration marker cannot be printed by a build with no CUDA in it.

Allocation: SCARF `-p gpu --gres=gpu:1 --exclusive --constraint=scarf23`,
node `gn3000`, 4×A100-SXM4-40GB, no other compute apps on the device at job
start. Builds ran inside the allocation; nothing heavy ran on a login node.

## 9. Twenty-four-movie same-backend A/B on CPU, `--j 1`

Same comparator (`md5 e2dfd9c828be5303243a7d82c30ecf62`), same 24-movie
inventory, same options minus `--gpu`, `main` `28918ae8…` against pr90
`993cc440…`, pinned to cores 40-46 on `small-refmac-machine`:

```
artifacts_total 109   artifacts_pass 105   artifacts_fail 4
corrected_images_compared 24   corrected_images_pass 24
total_pixels_compared 341735520
star_files_compared 25
auxiliary_compared 60   auxiliary_fail 4
per_movie_exact_gate_pass 24 / 24
controls_all_detected true
overall_graded PASS   overall_auxiliary FAIL
```

The four auxiliary failures are `all_batches.pdf`, `batch.pdf`, `header.pdf`,
`logfile.pdf` — the same four, and the same four the main-vs-main CPU control
produces. All three negative controls fire (`missing`, `pixel`, `header`).

One provenance note, kept rather than tidied away. An earlier pass of this leg
produced the same numbers but its driver deleted the output trees on exit, so
the JSON could not be re-graded with the updated comparator and was overwritten
by a grade of an empty directory. That first-pass summary survives as
`raw/cpu/ab-j1-firstpass-oldcomparator.log` and is **not** quoted as a result:
the numbers above come from the re-run with the trees kept
(`raw/cpu/ab-j1-run.log`).

## 10. Twenty-four-movie same-backend A/B on CPU, `--j 4`

The `--j 1` leg exercises the serial path only. This leg repeats it with four
threads, so the OpenMP regions that PR #90 touches are actually entered, and
lands in exactly the same place:

```
artifacts_total 109   artifacts_pass 105   artifacts_fail 4
corrected_images_compared 24   corrected_images_pass 24
total_pixels_compared 341735520
star_files_compared 25
auxiliary_compared 60   auxiliary_fail 4
per_movie_exact_gate_pass 24 / 24
controls_all_detected true
overall_graded PASS   overall_auxiliary FAIL
```

Same binaries (`28918ae8…` / `993cc440…`), same comparator, pinned
`taskset -c 56-63`, both sides exit 0. The four auxiliary failures are the same
four PDFs as every other comparison in this document. All three negative
controls fire. Raw: `raw/cpu/pr90_outputs_j4.json`
(sha256 `07a0de1d23a0b8e823e48049ce9d3459907fae1cd31e7d129323cc097705f68a`),
driver log `raw/cpu/ab-j4-timing-run.log`.

So the corrected-pixel identity now holds at `--j 1`, `--j 4` and `--j 8`
(CUDA), with a main-vs-main control on two of them.

## 11. Interleaved paired timing — a measurement, not a verdict

Three paired blocks, one discarded warm-up, `--j 8`, `taskset -c 56-63`,
same host, same allocation, same options, same input, both binaries pinned by
sha256. Run order alternates per block so a monotonic drift in machine state
cannot systematically favour one side.

| block | order | `main` (s) | pr90 (s) | ratio pr90/main | delta (s) |
|---|---|---|---|---|---|
| warm-up | main only, **discarded** | 231.152 | — | — | — |
| 1 | main, pr90 | 226.516 | 210.171 | 0.9278 | −16.345 |
| 2 | **pr90, main** | 226.240 | 211.298 | 0.9340 | −14.942 |
| 3 | main, pr90 | 224.879 | 208.531 | 0.9273 | −16.348 |

```
median_ratio 0.9278   min 0.9273   max 0.9340
median_delta_seconds -16.345
all_blocks_completed true   all_blocks_same_micrograph_count true
overall MEASURED
```

**Verdict word is `MEASURED`, deliberately.** Three blocks on one machine is
enough to say the sign is stable and the spread is narrow (0.67 percentage
points across the three ratios, and the block whose order was reversed is the
*least* favourable to pr90, which is the right direction for an ordering
artefact to point). It is not enough to publish a confidence interval, and it
says nothing about any other host, allocation, thread count or dataset.

### Where the time goes

Stage tables (`TIMING:BOOL=ON`) were present on all six graded runs, so the
end-to-end delta can be attributed rather than guessed. Medians across blocks:

| stage | `main` (s) | pr90 (s) | delta (s) |
|---|---|---|---|
| apply gain and initial sum | 11.615 | 0.878 | **−10.737** |
| read gain | 2.794 | 0.124 | **−2.670** |
| read movie | 6.046 | 5.510 | −0.536 |
| global iFFT | 43.825 | 43.149 | −0.676 |
| dw - iFFT | 41.436 | 40.858 | −0.578 |
| dose weighting | 71.520 | 71.139 | −0.381 |
| prep patch - FFT (in thread) | 74.762 | 82.223 | **+7.461** |
| align - iFFT CCF (in thread) | 12.424 | 13.233 | +0.809 |

The two stages PR #90 actually changes — the gain cache and the fused
gain-apply/initial-sum — account for −13.4 s of the −16.3 s end-to-end median.
Every other stage moves by under a second except `prep patch - FFT (in thread)`,
which moves the *wrong* way by +7.5 s; that is a thread-pool-internal
accumulator whose total is not wall time, and it is recorded here rather than
dropped because it is the one number in the table that does not support the
headline.

### Contention during the timing window, disclosed

The machine was **not** idle. A sampler ran every 30 s for the whole window
(81 samples, 18:38:40 → 19:18:44 UTC), raw at
`raw/cpu/contention-during-timing.log`:

* load average 1-min: min 2.88, median 9.35, max 10.54;
* two long-lived `ctffind` processes belonging to another workload, present in
  **all 81 samples** at 99.9 % CPU, scheduled on **PSR 1 and PSR 6**;
* no foreign process was ever observed on the pinned mask. Every process seen
  on cores 56-63 was this harness: `motioncorr` (PSR 57, 60, 61, 62, 63), the
  driver `python3`, and the sampler's own `ps`.

This does not make the numbers clean-room. It makes them paired numbers taken
on a loaded shared machine with the load held off the pinned cores and
alternated across both sides. Nothing was killed, and nothing was deferred
onto another user.

## 12. What was deliberately not done

* No independent-dataset acquisition. The 24-movie RELION 3.0 tutorial
  inventory already on the machines is the whole input set.
* No timing comparison across hosts or allocations, and no speed claim from a
  single run. Anything quoted from an earlier cumulative head (for example the
  `747a30` series) belongs to **that original cumulative head**, not to this
  code head, and is not restated here as new-head proof. The −7.2 % median in
  §11 is this code head against its own base, on one machine, at `--j 8`, on
  the tutorial inventory — it is not a cumulative figure and does not
  corroborate one.
* No relaxation of any existing comparator, gate or threshold.
* No merge, no new PR, no source change.

## Standing caveat

Every comparison above is *same-backend*: one backend, two code heads. It does
not speak to CPU/CUDA agreement, to RELION parity, or to scientific
correctness. The historical CPU/RELION Gate 2 failures and the noisy-truth
characterisation recorded elsewhere in the repository remain open and are not
addressed by this evidence.
