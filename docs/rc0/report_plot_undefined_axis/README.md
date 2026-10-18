# RC0 D13 Evidence: `MetaDataTable::addToCPlot2D` Undefined X-Axis Guard (#229)

- **Issue:** [#229](https://github.com/KingAlejandro/MotionCorr-standalone/issues/229) (RC0 programme [#198](https://github.com/KingAlejandro/MotionCorr-standalone/issues/198), decision D13 revised 2026-10-17)
- **Branch:** `fix/rc0-report-plot-undefined-axis`
- **Base (`main`):** `1afa03b57afbae42138ee30c3545b57b5a74c321`
- **Code + test commit:** `b82d25f4dda6bca746e4206fed1272851cc6a5ce`
- **Draft PR:** [#230](https://github.com/KingAlejandro/MotionCorr-standalone/pull/230)

---

## 1. Defect and Narrow Fix

In `src/metadata_table.cpp`, `MetaDataTable::addToCPlot2D` (~line 1721 at `main` `1afa03b5`) indexed `const long offx = label2offset[xaxis];` before testing `if (xaxis == EMDL_UNDEFINED)`. Because `EMDL_UNDEFINED` is `-1` (`src/metadata_label.h:60`) and `MotioncorrRunner::generateLogFilePDFAndWriteStarFiles` calls `MDavg.addToCPlot2D(plot2Db, EMDL_UNDEFINED, label, 1.)` (`src/motioncorr_runner.cpp:1730`), every run that generates `logfile.pdf` (any run without `--skip_report_pdf`) read `label2offset[-1]` (8 bytes before `label2offset.data()`).

### Fix (`src/metadata_table.cpp`)
Check `if (xaxis == EMDL_UNDEFINED)` first and set `xval = idx + 1;`; only index `label2offset[xaxis]` in the `else` branch for defined x-axis labels. All error messages (`cannot find x-axis label`, `cannot find y-axis label`, `can only plot x-axis double, int or long int`, `can only plot y-axis double, int or long int`), plotted coordinates, and axis titles are preserved verbatim.

### Audit of Other `label2offset[...]` Sites (Unchanged)
All other `label2offset[...]` uses in `src/metadata_table.h` and `src/metadata_table.cpp` were audited and left unchanged per scope:
1. `src/metadata_table.cpp:1742` (`MetaDataTable::addToCPlot2D`, y-axis `label2offset[yaxis]`): `addToCPlot2D` has no `EMDL_UNDEFINED` y-axis mode (`yaxis` is unconditionally used as the dataset and y-axis title), and the sole caller (`src/motioncorr_runner.cpp:1730`) passes only positive defined labels (`EMDL_MICROGRAPH_ACCUM_MOTION_TOTAL`, `EMDL_MICROGRAPH_ACCUM_MOTION_EARLY`, `EMDL_MICROGRAPH_ACCUM_MOTION_LATE`) guarded by `MDavg.containsLabel(label)`.
2. `src/metadata_table.h:444` (`MetaDataTable::getValue`): already guarded at line 434 by `if (label < 0 || label >= EMDL_LAST_LABEL) return false;`.
3. `src/metadata_table.h:486, 491` (`MetaDataTable::setValue`): already guarded at line 477 by `if (label < 0 || label >= EMDL_LAST_LABEL) return false;`.
4. `src/metadata_table.cpp:661, 666, 670, 675, 679` (`MetaDataTable::newSort`): guarded by `EMDL::isString(label)`, `EMDL::isDouble(label)`, `EMDL::isInt(label)`, which look up `label` in `EMDL::data` and return `false` for `EMDL_UNDEFINED`/negative labels (falling into the `REPORT_ERROR` branch without indexing `label2offset`). All callers pass fixed positive enum constants.
5. `src/metadata_table.cpp:726` (`MetaDataTable::deactivateLabel`): only indexes `label2offset[label]` after matching `activeLabels[i] == label` and `label != EMDL_UNKNOWN_LABEL`.
6. `src/metadata_table.cpp:738, 824` (`MetaDataTable::addLabel`): checks `if (label >= EMDL_LAST_LABEL)` without `label < 0`, but is unreachable with `EMDL_UNDEFINED`/negative labels on real code paths (`readStarLoop` at line 1064 and `readStarList` at line 1166 both map `EMDL_UNDEFINED` to `EMDL_UNKNOWN_LABEL` before calling `addLabel`; `setValue` guards `label < 0`; `addMissingLabels` and `joinMetaDataTables` iterate `activeLabels`; direct callers pass fixed positive `EMDL_*` constants).
7. `src/metadata_table.cpp:840` (`MetaDataTable::addMissingLabels`) and `src/metadata_table.cpp:919–920` (`MetaDataTable::setObjectUnsafe`): index `label2offset` only with labels drawn from `activeLabels`.

---

## 2. Binaries & Provenance on `4GPUs`

- **Host:** `4-gpu-vm` (`4GPUs`), `g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`, CUDA `12.8` (`/usr/local/cuda-12.8`), nvCOMP `5.3.0.16`, CMake `3.28`, Ghostscript `10.02.1`.
- **Scratch:** `/mnt/clathrin/alex-motioncorr-rc0/W-D13/` (`3.7 GB` after deleting bulk `.mrc` files; cap `20 GB`).
- **Lanes:** CPUs `40-55,72-79` for CPU builds, sanitizer, identity, CTest, and composition checks; `GPU1` (`CUDA_VISIBLE_DEVICES=GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d`) + CPUs `104-111` under `flock /tmp/motioncorr-gpu1-correctness.lock` for CUDA CTest and CUDA+nvCOMP identity.

| Build (`4GPUs`) | Source SHA | CMake Configuration | `motioncorr` SHA-256 (`raw/4gpus/binary-sha256.txt`) |
|---|---|---|---|
| `fix-cpu` | `b82d25f4dda6bca746e4206fed1272851cc6a5ce` | `Release -DBUILD_TESTING=ON -DCUDA=OFF` | `7dc0565c7adce24df371109b84886a2bef79cb724630c61f145d3703d7bed480` |
| `fix-cuda` | `b82d25f4dda6bca746e4206fed1272851cc6a5ce` | `Release -DBUILD_TESTING=ON -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=OFF` | `853ee7da503f32de0cc93777a4859a86abfc5a9f2b7f1343d2b9e93900346eb8` |
| `fix-nvcomp` | `b82d25f4dda6bca746e4206fed1272851cc6a5ce` | `Release -DBUILD_TESTING=ON -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=ON` | `8618429f7e97345c026b8b00d69d41148ca64ebeb1e1362531acedb6868f0ca6` |
| `fix-asan` | `b82d25f4dda6bca746e4206fed1272851cc6a5ce` | `RelWithDebInfo -DBUILD_TESTING=ON -DCUDA=OFF -fsanitize=address,undefined -fno-omit-frame-pointer` | `c2d9a7c974853a64b828415b1e242207ca01a378a9f802bfdf923f43d82b56ac` |
| `main-cpu` | `1afa03b57afbae42138ee30c3545b57b5a74c321` | `Release -DBUILD_TESTING=OFF -DCUDA=OFF` | `ccf2736e7596813e58bd05e0c96dca27ea911a80c90a3678b511d3cb744ac72b` |
| `main-nvcomp` | `1afa03b57afbae42138ee30c3545b57b5a74c321` | `Release -DBUILD_TESTING=OFF -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DUSE_NVCOMP=ON` | `1ba654ccb5dbbf6f414a491fe9e0ab841c6ee7836e045a8ce4b9499e6a8e24fe` |
| `main-asan` | `1afa03b57afbae42138ee30c3545b57b5a74c321` | `RelWithDebInfo -DBUILD_TESTING=OFF -DCUDA=OFF -fsanitize=address,undefined -fno-omit-frame-pointer` | `da2be282a5975b9650039b791faff3b5106603fe3bd05f50be2417e992797933` |

---

## 3. Regression Test & Full CTest (Items 1 & 4)

- **Added CTest:** `ReportPlotUndefinedAxis` (`$<TARGET_FILE:runner_numerics> plot2d_undefined_axis` in `tests/test_runner_numerics.cpp`), registered in `CMakeLists.txt`, `tools/validate_test_collection.py` (`DEFAULT_REQUIRED_TESTS`), and `tools/test_ci_fail_closed.py` (`INTEGRATED_SUITE` and drop-one controls).
- **What it tests:**
  1. `addToCPlot2D` with `xaxis = EMDL_UNDEFINED` on a 4-row `MetaDataTable` with a defined `double` y-label (`EMDL_MICROGRAPH_ACCUM_MOTION_TOTAL`) and a defined `int` y-label (`EMDL_IMAGE_OPTICS_GROUP`): verifies `x = 1..4`, exact `y` values, empty x-axis title, and exact y-axis title.
  2. `addToCPlot2D` with defined numeric x- and y-labels: verifies exact `x` and `y` values and both axis titles.
  3. Missing defined x-label, missing defined y-label (with both `EMDL_UNDEFINED` and defined x-axis), and non-numeric defined x- or y-label: verifies `RelionError` is raised with the exact expected `REPORT_ERROR` message.

| Build (`b82d25f4`) | Collected | Passed | Failed | Skipped | `validate_test_collection.py` | Raw Evidence |
|---|---|---|---|---|---|---|
| `fix-cpu` | `73` | `73` | `0` | `0` | `PASS` (`rc=0`, `test_ci_fail_closed.py` `8/8` `OK`) | `raw/4gpus/ctest-fix-cpu.{log,summary.json,collection.json}` |
| `fix-cuda` (`sm_80`, `GPU1`) | `106` | `106` | `0` | `0` | `PASS` (`rc=0`) | `raw/4gpus/ctest-fix-cuda.{log,summary.json,collection.json}` |
| `fix-nvcomp` (`sm_80` + nvCOMP, `GPU1`) | `109` | `109` | `0` | `0` | `PASS` (`rc=0`) | `raw/4gpus/ctest-fix-nvcomp.{log,summary.json,collection.json}` |

---

## 4. Sanitizer Evidence (Item 2)

Input: 4-movie tutorial subset (`movies4.star`: `20170629_00021..00024_frameImage.tiff` + `Movies/gain.mrc`, hashes in `raw/4gpus/tutorial4-inputs.sha256`), run **without** `--skip_report_pdf`:
```bash
motioncorr --i movies4.star --use_own --dose_weighting --dose_per_frame 1.277 \
  --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc \
  --seed 1 --expected_frames 24 --j 8 --o <out>/
```

| Control | Binary | Exit | ASan/UBSan Result | Raw Log |
|---|---|---|---|---|
| **Negative control (`main` `1afa03b5`)** | `main-asan` | `1` | `ERROR: AddressSanitizer: heap-buffer-overflow` READ of size 8 at `MetaDataTable::addToCPlot2D` (`src/metadata_table.cpp:1721`), 8 bytes before the 5,000-byte `label2offset` buffer allocated in `MetaDataTable::clear()` (`src/metadata_table.cpp:161`), called from `MotioncorrRunner::generateLogFilePDFAndWriteStarFiles` (`src/motioncorr_runner.cpp:1730`). | `raw/4gpus/asan-main.log` |
| **Positive control (`fix` `b82d25f4`)** | `fix-asan` | `0` | **0 ASan/UBSan errors.** Completes `corrected_micrographs.star`, all 6 summary EPS plots (`corrected_micrographs_{all,hist}_*.eps`), 4 per-movie `_shifts.eps`, and `logfile.pdf`. | `raw/4gpus/asan-fix.log` |
| **Unit test under ASan+UBSan (`fix` `b82d25f4`)** | `fix-asan/runner_numerics` | `0` | `ctest -R ReportPlotUndefinedAxis` passes with **0 ASan/UBSan errors**. | `raw/4gpus/asan-ctest-report-plot.log` |

*Separate unrelated sanitizer observation (not fixed per instructions):* When `runner_numerics plot2d_undefined_axis` is run under LeakSanitizer (`detect_leaks=1`), catching `RelionError` in-process reports an 800-byte leak per thrown `RelionError` at `RelionError::RelionError` (`src/error.cpp:58`: `char* str = new char[MAX_BACKTRACE_SIZE];` is never freed).

---

## 5. Output-Tree Identity (Item 3)

Compared on the 4-movie tutorial subset (`movies4.star`, `MDavg.numberOfObjects() == 4 > 3`, so both `_all_*.eps` via `addToCPlot2D` and `_hist_*.eps` via `columnHistogram` are generated alongside `logfile.pdf`):

1. **Release CPU (`main-cpu` `1afa03b5` vs `fix-cpu` `b82d25f4`):**
   - `docs/rc0/qf/tools/compact_compare_output_trees.py` (complete non-PDF tree): **PASS** (`4` movies, `4` MRC images, `5` STAR files, `56,955,920` pixels per arm, `different files=0`; `raw/4gpus/identity-cpu-strict.json`).
   - `tools/profiling/lib/identity.py` (`compare_trees`): **PASS** (`21` files compared, `4` MRC headers+extended headers+payloads, `identical: true`; `raw/4gpus/identity-cpu-mcprof.json`).
   - **EPS & `logfile.pdf` plot content (`raw/4gpus/identity-cpu-eps-pdf.json`):**
     - All 6 summary EPS files (`corrected_micrographs_all_rlnAccumMotion{Early,Late,Total}.eps` and `corrected_micrographs_hist_rlnAccumMotion{Early,Late,Total}.eps`) are **raw byte-for-byte identical** (`raw_equal=True`) without any path normalization.
     - All 4 per-movie `Movies/20170629_00021..00024_frameImage_shifts.eps` are byte-identical after normalizing the output root path in the plot title (`norm_equal=True`).
     - `header.pdf` and pages 1–6 of `logfile.pdf` (the 6 summary plots rendered by Ghostscript) rendered at 150 DPI (`gs -sDEVICE=pgmraw -r150`) have identical SHA-256 `bc1d3b371b6ce2d9e0c709a39bcc2848c575abab477ac7b7cca1aa9912df0e8b` on both arms (`EQUAL`).
2. **Release CUDA+nvCOMP (`main-nvcomp` `1afa03b5` vs `fix-nvcomp` `b82d25f4` on `GPU1`):**
   - `docs/rc0/qf/tools/compact_compare_output_trees.py --products-only`: **PASS** (`4` movies, `4` MRC images, `5` STAR files, `56,955,920` pixels per arm, `different files=0`; `raw/4gpus/identity-nvcomp-products.json`).
   - `tools/profiling/lib/identity.py` (`compare_trees`): **PASS** (`21` files compared, `identical: true`; `raw/4gpus/identity-nvcomp-mcprof.json`).
   - All 6 summary EPS files are raw byte-for-byte identical (`raw_equal=True`), and `header.pdf` / `logfile.pdf` pages 1–6 rendered at 150 DPI have identical SHA-256 `91ab7cde319025918c8c0e9e63e59570bc68f60a9105d304fb6e930e9b2f71cb` (`raw/4gpus/identity-nvcomp-eps-pdf.json`).

---

## 6. Composition Check (Item 5)

Checked using `git merge-tree --write-tree` (`raw/4gpus/composition.log`):
1. `fix/rc0-report-plot-undefined-axis` (`b82d25f4`) + `origin/fix/rc0-stale-cuda-oom` (#228, `da402cab31110cdd8a5837889ae3a205511450c3`):
   - `git merge-tree --write-tree` exit `0`, tree `cc7ec4ad59cab1c3fc64ef18bb20b2f55e6e8ad7` (**0 textual conflicts**).
2. Above + D10 branch `w-d10c` (`97fb9fda5902f4bd5c2aab7c40ae4064637b5125`, local D10 branch as `fix/rc0-d10-eer-memory-safety` is not yet pushed to `origin`):
   - `git merge-tree --write-tree` exit `0`, tree `e33f89a33781af3f88d30ce2c02d7e178a5e5c64` (**0 textual conflicts**).
3. **Semantic collisions:** **0 collisions.**
   - `runner_numerics` has 19 unique subcommands (`interpolate_recenter`, `mrc_stats`, `plot2d_undefined_axis`, `float_plan_cache`, `render_eer`, `read_tiff_raw`, `count_eer`, `render_eer_groups`, `integer_to_string`, `read_tiff`, `read`, `model_eer`, `model_complete`, `model_query`, `model_roundtrip`, `model_mask`, `legacy_mtf`, `bin`, `write_model`).
   - `DEFAULT_REQUIRED_TESTS` has 66 unique entries (`ReportPlotUndefinedAxis` and `EerMemorySafety` both present); `CUDA_REQUIRED_TESTS` has 1 unique entry (`CudaStaleErrorAfterOom`); 0 duplicates and 0 overlap.
4. **Composed builds & tests on `4GPUs`:**
   - Composed CPU (`4659fe56bca4a90045cd3dba3fd4c88c4bcba80112d47d431334d7d7a1be6a7a`) and CUDA+nvCOMP (`514da152b9a0dd739f1fb31438664f9053abfe29e52871a87e7d709a3ecc6cea`) built with `rc=0`.
   - `validate_test_collection.py` **PASS** on both (`74` CPU tests, `111` CUDA+nvCOMP tests).
   - `test_ci_fail_closed.py` **PASS** (`8/8`).
   - `ctest -R "ReportPlotUndefinedAxis|EerMemorySafety"` **PASS** (`2/2`).

---

## 7. Whole-Job Paired CPU Performance (Item 6)

Per the coordinator's updated resource policy (no timing on `4GPUs`; SCARF `ibis` rejected submission with `Invalid account or account/partition combination specified` for `scarf1415`), the paired whole-job CPU timing was run on the designated alternative venue **`cpu64`** (`small-refmac-machine`, `130.246.81.24`):
- **Host & CPU:** `small-refmac-machine`, 2× AMD EPYC 7763 64-Core Processor (64 CPUs), kernel `6.8.0-86-generic`, THP `always [madvise] never`, `GLIBC_TUNABLES` unset.
- **Toolchain:** `g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`, CMake `4.4.3`, Ghostscript `10.02.1`, Python `3.12.3`.
- **Binaries (built on `cpu64` under `/tmp/motioncorr-cpu64-bench.lock` on CPUs `48-63`, `-O3 -DNDEBUG -std=gnu++17 -fopenmp`):**
  - `main` (`1afa03b5`): `307a030b03785201342a57c4d8adae14120d87676fa6bec7e62f8959d5b03a35`
  - `fix` (`b82d25f4`): `68dc7ac11049bb15be3caa90af10adb6c7bb7e44b752d797080b9ca1a79d96f9`
- **Lock & Lane:** `/tmp/motioncorr-cpu64-bench.lock` held via `tools/profiling/mcprof.py compare`; payload pinned to CPUs `48-55` (`--j 8`), sampler pinned to CPUs `56-59`.
- **Workload:** 2-movie tutorial subset (`/home/ubuntu/mc-rc0-paired-20261017/work/tutorial/movies.star`, sha256 `65b1c972db5b06f4bd556f3118948ee0da35589a1f06e8a120ce33ffc7724f05`), `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8` (**without** `--skip_report_pdf`).

| Comparison | Retained Pairs (Order) | Arm A Med Wall (IQR, Range) | Arm B Med Wall (IQR, Range) | Median $\Delta T = B - A$ | 95%+ CI of Median | Sign Test | Noise ($1.4826 \cdot \text{MAD}$) | Null Max $|\Delta T|$ | Verdict (`mcprof compare` / D14) | Product Identity |
|---|---|---|---|---|---|---|---|---|---|---|
| **Round-0 `fix` vs `main` (AB/BA)** | `8 / 8` (`4 AB, 4 BA`, `0` discarded, `0.00` foreign lane cores) | `17.630 s` (`0.130 s`, `17.511–17.661 s`) | `17.681 s` (`0.282 s`, `17.494–18.367 s`) | **`+0.051 s` (`+0.29%`)** | **`[-0.131, +0.717] s`** (`99.2%`, upper bound **`+4.06%`**) | `4+/4-` (`p = 1.000`) | `0.141 s` | `0.293 s` (`0.050 s` ex. 1 spike) | **Unresolved** (`not resolved (below noise 0.424 s)`; CI upper bound `+4.06% > +0.5%`) | **PASS** (`12` files, `2` MRCs) |
| **Round-0 `main_null` vs `main` (AA null)** | `6 / 6` (`3 AB, 3 BA`, `0` discarded, `0.00` foreign lane cores) | `17.703 s` (`0.042 s`, `17.650–17.832 s`) | `17.691 s` (`0.059 s`, `17.650–18.125 s`) | **`+0.018 s` (`+0.10%`)** | **`[-0.049, +0.293] s`** (`96.9%`) | `4+/2-` (`p = 0.688`) | `0.067 s` | `0.293 s` | **not resolved (below noise `0.171 s`)** | **PASS** (`12` files, `2` MRCs) |

Raw round-0 artifacts: `raw/cpu64_timing/ab_compare/{provenance.json,runs.jsonl,identity.json,compare.json,report.md}` and `raw/cpu64_timing/aa_null/{provenance.json,runs.jsonl,identity.json,compare.json,report.md}`.

---

## 8. Revision Round 1: Pilot Study & Pre-Specified Definitive Design (D14)

At $N = 8$ pairs, the binomial order-statistic CI (`tools/profiling/lib/stats.py` `median_ci`) uses the sample minimum and maximum (`[d(1), d(8)]`, `99.22%` coverage), so a single ext4 disk-writeback spike (`+0.717 s` in round 8 on `/dev/vda1`) set the upper confidence bound to `+4.06%`, leaving the 8-pair comparison **unresolved** under the maintainer's **D14 `+0.5%` margin**.

### A. Separate Pilot Study (`raw/cpu64_pilot/`, excluded from the definitive result)
To select the workload with the best relative precision per unit time and size $N$ in advance, a separate 4-pair balanced AB/BA pilot (`r01..r04` alternating `AB, BA, AB, BA`, plus 1 discarded warmup per arm) was run on `cpu64` under `/tmp/motioncorr-cpu64-bench.lock` (`CPUs 48-55`, `--j 8`, `mcprof` sampler on `56-59`, THP `madvise`, inputs and run trees staged in `/dev/shm` `tmpfs` to eliminate virtual-disk writeback stalls, report generation ON):

| Pilot Workload | Pairs | `main` Med Wall $T_{\text{main}}$ | Pair Time ($2 T_{\text{main}}$) | Paired Diffs $d = \text{fix} - \text{main}$ (s) | SD $s_d$ (s) | Robust SD $1.4826\cdot\text{MAD}$ (s) | $\sigma_{\text{rel}} = \frac{\max(s_d, \text{MAD}_{\text{sd}})}{T_{\text{main}}}$ | Relative Precision per $\sqrt{\text{min}}$ ($\sigma_{\text{rel}}\sqrt{2T_{\text{main}}/60}$) | Expected CI Half-Width at $N=32$ ($0.516\,\sigma_{\text{rel}}$) |
|---|---|---|---|---|---|---|---|---|---|
| **2-movie tutorial (`movies2.star`)** | `4` (`2 AB, 2 BA`) | `17.5711 s` | `35.14 s` | `+0.0858, +0.0554, -0.0180, +0.0025` | `0.0477 s` (`0.271%`) | `0.0544 s` (`0.310%`) | **`0.3098%`** | **`0.2371%`** | **`0.1598%`** ($\le 0.50\%$) |
| **8-movie tutorial (`movies8.star`)** | `4` (`2 AB, 2 BA`) | `68.6199 s` | `137.24 s` | `-0.7921, +0.5156, +0.8426, +0.7057` | `0.7521 s` (`1.096%`) | `0.2424 s` (`0.353%`) | **`1.0960%`** | **`1.6576%`** | **`0.5652%`** ($> 0.50\%$) |

**Workload selection from pilot:** The **2-movie tutorial workload (`movies2.star`)** achieves **`0.2371%` vs `1.6576%`** relative spread per $\sqrt{\text{minute}}$ (**7.0× better relative precision per unit time** than the 8-movie workload, because pairing A and B across a 17.6 s window cancels background host drift far better than across a 68.6 s window), while exercising the full multi-movie report path (`corrected_micrographs.star`, all 3 `MDavg.addToCPlot2D(plot2Db, EMDL_UNDEFINED, label, 1.)` calls producing `corrected_micrographs_all_rlnAccumMotion{Total,Early,Late}.eps`, per-movie `_shifts.eps`, and `logfile.pdf`).

### B. Pre-Specified Definitive Design (`run_definitive_cpu64.sh`, fixed before execution)
1. **Venue & Lock:** `cpu64` (`small-refmac-machine`, 2× AMD EPYC 7763 64-Core Processor, THP `always [madvise] never`, `GLIBC_TUNABLES` unset), holding `/tmp/motioncorr-cpu64-bench.lock` via `flock`.
2. **Binaries, Affinity & Threads:** Matched Release CPU binaries (`main` `1afa03b5` sha256 `307a030b03785201342a57c4d8adae14120d87676fa6bec7e62f8959d5b03a35`; `fix` `b82d25f4` sha256 `68dc7ac11049bb15be3caa90af10adb6c7bb7e44b752d797080b9ca1a79d96f9`), payload pinned to `CPUs 48-55` (single 8-core CCD on NUMA node 1, `--j 8`, `OMP_NUM_THREADS=8`), `mcprof` sampler pinned to `CPUs 56-59`.
3. **Workload & Options:** `movies2.star` (`20170629_00021_frameImage.tiff`, `20170629_00022_frameImage.tiff`, sha256 `aa019332ca8825b26f89ffd94d382f46a1a64749b052ede953a48e40107fd69e`) + `gain.mrc` staged in `/dev/shm` `tmpfs`; options `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8` (**report generation ON**, no `--skip_report_pdf`).
4. **Sample Size, Seed & Deterministic Order:**
   - **AB/BA (`main` vs `fix`):** `1` unrecorded warmup per arm (`r00`), followed by **$N = 32$ pairs** (`--pairs 32 --max-rounds 32`), deterministic alternating order: odd rounds `r01, r03, ..., r31` = `AB` (`16` pairs) and even rounds `r02, r04, ..., r32` = `BA` (`16` pairs) — **exact `16 AB / 16 BA` balance**. At $N = 32$, `stats.median_ci` selects order statistics `[d(10), d(23)]` (`97.99%` coverage, $z = 0.516$), giving an expected CI half-width of $0.516 \times 0.3098\% = \mathbf{0.160\%} \le +0.50\%$ (`+0.088 s`).
   - **AA Null (`main` vs `main_null`):** `1` unrecorded warmup per arm (`r00`), followed by **$N_{\text{null}} = 12$ pairs** (`--pairs 12 --max-rounds 12`), deterministic alternating order: odd rounds `r01, r03, ..., r11` = `AB` (`6` pairs) and even rounds `r02, r04, ..., r12` = `BA` (`6` pairs) — **exact `6 AB / 6 BA` balance** (`stats.median_ci` order statistics `[d(3), d(10)]`, `96.14%` coverage).
   - ** MotionCorr RNG seed:** `--seed 1` (deterministic hot-pixel RNG).
5. **Exclusion Rule:** Before each round `mcprof` waits up to `300 s` (`--lane-wait 300`) for `CPUs 48-55` foreign CPU $\le 0.25$ cores. A pair is discarded only if either arm has `rc != 0`, `< 2` MRC products, an unverified executable image, a payload affinity mismatch (`!= [48..55]`), or recorded foreign lane CPU $> 0.25$ cores during the run; any discard removes both arms of the pair. The declared design is run **once** (`--pairs 32 --max-rounds 32` and `--pairs 12 --max-rounds 12`) without adding runs.
6. **D14 Decision Rule:**
   - **Pass:** no resolved slowdown, and upper $\ge 95\%$ CI bound of $\text{median}(\text{fix} - \text{main}) \le +0.5\%$ of $\text{median}(\text{main})$ whole-job wall time.
   - **Unresolved:** no resolved slowdown, and upper $\ge 95\%$ CI bound $> +0.5\%$ of $\text{median}(\text{main})$.
   - **Fail:** resolved slowdown.

### C. Definitive Comparison Results (`raw/cpu64_definitive/`)

Executed once on `cpu64` under `/tmp/motioncorr-cpu64-bench.lock` (`2026-10-18T01:57:57Z` to `2026-10-18T02:25:36Z`, `0` discarded pairs in both series, max foreign CPU on `CPUs 48-55` $\le 0.006$ cores, host `load1 = 5.10–10.19`):

| Series | Retained Pairs (Order) | Arm A Med Wall (IQR, Range) | Arm B Med Wall (IQR, Range) | Median $\Delta T = B - A$ | $\ge 95\%$ CI of Median | Upper CI Bound vs `main` Med | Sign Test | Noise ($1.4826 \cdot \text{MAD}$) | Null Max $|\Delta T|$ | `mcprof compare` Verdict | **D14 Status (`+0.5%` = `+0.0870 s`)** | Product Identity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Round-1 `fix` vs `main` (`ab_32`, sequential)** | `32 / 32` (`16 AB, 16 BA`, `0` discarded) | `17.398 s` (`0.113 s`, `17.228–17.561 s`) | `17.400 s` (`0.086 s`, `17.237–17.616 s`) | **`-0.000068 s` (`-0.0004%`)** | **`[-0.084329, +0.051712] s`** (`[-0.4847%, +0.2972%]`, `97.99%` cov., `[d(10), d(23)]`) | **`+0.051712 s` (`+0.2972%`)** | `16+/16-` (`p = 1.000`) | `0.115883 s` (`0.6661%`) | `0.258634 s` (`1.4799%`) | `not resolved (below noise 0.116 s)` | **within 0.5 % numerically (upper +0.297 %); protocol deviation: nulls sequential, not interleaved; superseded by the interleaved run below** | **PASS** (`12` files, `2` MRCs) |
| **Round-1 `main_null` vs `main` (`aa_12`, sequential)** | `12 / 12` (`6 AB, 6 BA`, `0` discarded) | `17.476 s` (`0.078 s`, `17.377–17.612 s`) | `17.425 s` (`0.061 s`, `17.349–17.511 s`) | **`-0.042996 s` (`-0.2460%`)** | **`[-0.180871, +0.038215] s`** (`[-1.0350%, +0.2187%]`, `96.14%` cov., `[d(3), d(10)]`) | `+0.038215 s` (`+0.2187%`) | `4+/8-` (`p = 0.388`) | `0.111503 s` (`0.6380%`) | `0.258634 s` (`1.4799%`) | `not resolved (below noise 0.112 s)` | — (sequential null control, superseded below) | **PASS** (`12` files, `2` MRCs) |

- **Positional breakdown (`ab_32`):** When `fix` ran second (`AB`, $n = 16$), median $\Delta T = -0.078\text{ s}$; when `fix` ran first (`BA`, $n = 16$), median $\Delta T = +0.054\text{ s}$; second-position cost $= -0.066\text{ s}$.
- **Paired IQR (`ab_32`):** `[-0.090088, +0.057857] s`; full range `[-0.141, +0.276] s`.
- **Raw artifacts:** `run_definitive_cpu64.sh`, `raw/cpu64_definitive/definitive_summary.json`, `raw/cpu64_definitive/ab_32/{provenance.json,runs.jsonl,identity.json,compare.json,report.md}`, and `raw/cpu64_definitive/aa_12/{provenance.json,runs.jsonl,identity.json,compare.json,report.md}`.

---

## 9. Revision Round 2: Pre-Specified Interleaved Definitive Comparison (`wd13_interleaved_pairs.py`)

Because `mcprof.py compare` ran the 32 comparison pairs and the 12 null pairs as two sequential series in Section 8.C rather than interleaving the nulls across the comparison window, a fresh pre-specified interleaved definitive comparison (`wd13_interleaved_pairs.py`, invoked by `run_interleaved_cpu64.sh`) is declared in advance and committed before execution:

1. **Venue, Lock, CPUs & Binaries:** Same as Section 8.B (`cpu64`, `/tmp/motioncorr-cpu64-bench.lock`, payload on `CPUs 48-55` `--j 8`, driver/sampler on `CPUs 56-59`, THP `madvise`, `GLIBC_TUNABLES` unset; `A` = `main` `1afa03b5` sha256 `307a030b03785201342a57c4d8adae14120d87676fa6bec7e62f8959d5b03a35`; `B` = `fix` `b82d25f4` sha256 `68dc7ac11049bb15be3caa90af10adb6c7bb7e44b752d797080b9ca1a79d96f9`; $A'$ = same `main` binary under directory tag `A2`, avoiding any `'` character in filesystem paths passed to Ghostscript).
2. **Workload & Sizing:** 2-movie tutorial subset (`movies2.star` in `/dev/shm` `tmpfs`, report generation ON), sized from the recorded pilot (`raw/cpu64_pilot/pilot_summary.json`; no new pilot run).
3. **Interleaved Order (48 definitive pairs = 96 runs, after 1 discarded warmup per arm):**
   - `16` comparison blocks `blk = 1..16`, each block `[AB, BA]` (**$N = 32$ comparison pairs: `16 AB / 16 BA`**).
   - After every $k = 2$-nd comparison block (`blk in {2, 4, 6, 8, 10, 12, 14, 16}`), run `1` null block `[AA', A'A]` (**$N_{\text{null}} = 16$ interleaved null pairs: `8 AA' / 8 A'A`**).
   - Each of the 8 cycles ($c = 1 \dots 8$) runs the 6-pair sequence `AB, BA, AB, BA, AA', A'A`; the final null block (`blk = 16`, positions `47–48`) follows the final comparison block (`blk = 16`, positions `45–46`).
4. **Exclusion & Immediate Same-Position Retry Rule:**
   - Before each run, wait up to `300 s` for foreign CPU on `CPUs 48-55` $\le 0.25$ cores.
   - Discard a pair only if either run has `rc != 0`, `< 2` MRC products, missing/empty `logfile.pdf`, unverified executable path, payload affinity mismatch (`!= [48..55]`), or foreign CPU $> 0.25$ cores on `CPUs 48-55` during the run.
   - Rerun any discarded pair immediately in the exact same position and order, up to `3` attempts.
5. **Pre-Run Declaration Artifacts:** Written to `rule.txt`, `design.json`, and `declared_timestamps.json` before the first warmup/timed run.
