# RC0 acceptance report (SKELETON)

Status: **skeleton, not a result, revision 1** (after the R-REL accuracy review of PR #201). Fill from the qualification of the frozen SHA (QF, #198). Every cell that needs a QF result says
**pending RC0 QF**. A planned or unrun check is **UNRUN**, never PASS. Rows labelled "reference" come from earlier evidence at an
older SHA and are not RC0 results.

## 1. Frozen SHA

| Field | Value |
|---|---|
| Frozen source SHA | pending RC0 QF (decision D4 on #198) |
| Base for this draft | main `1db86902` |
| Register items included (GO, merged) | C1 #178, C2 #187, C3 #188, C4 #185, E1 #196, M1 #195, R1 #197; list the merge SHAs at freeze |
| Prospective, not yet merged | **F1** (no `logfile.pdf` after a failed render, `fix/rc0-logfile-failed-render`): GO as a routine fix, pending merge, independent review and tests. Pending merge/review/tests state: pending RC0 QF. C5 #179, C6 #181, C7 #183: **bounded experiments** under the amended rule ([#10](https://github.com/KingAlejandro/MotionCorr-standalone/issues/10#issuecomment-6223528151)); only items the coordinator records GO enter |
| Held / excluded | T1 #138: bounded experiment, **merge HOLD pending D1** and its gates (not simply out of scope); L1 #141/#152 nvTIFF: **NO-GO for RC0** unless D2 is GO before freeze and a separate complete-product gate passes; E2 #193 option 2: bounded experiment, NO-GO for RC0 unless all gates pass before freeze; C8 #184 and C9 #177/#182: NO-GO; #149 deferred |
| Open items that affect the claim | QM memory admission on smaller GPUs: pending; T3 nvCOMP pre-decode arithmetic audit: decision pending |
| CI run on the frozen head | pending RC0 QF |
| Decisions recorded | D1 decoder trust boundary: pending; D2 optional proprietary dependencies: pending; T3 arithmetic audit: pending (brief [PR #199](https://github.com/KingAlejandro/MotionCorr-standalone/pull/199), being revised); D3 each merge: per PR; D4 scope and SHA: pending |

## 2. Supported and unsupported configurations

Copy the final classes from `SUPPORT.md` §1 and the matrices in §2 and §3 of that page. Each row below is filled at freeze.

| Configuration | Class at freeze | Evidence | Verdict |
|---|---|---|---|
| CPU `--use_own`, Release, Linux x86_64 | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| CPU `--use_own`, Release, macOS arm64 | pending RC0 QF | CPU suite with 2 inherited failures and 1 skip (`RELEASE_CHECKLIST.md` §3) | pending RC0 QF |
| CUDA one device, no nvCOMP | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| CUDA one device, nvCOMP | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| Multi-GPU via `run_dataset.py` | pending RC0 QF | pending RC0 QF | pending RC0 QF |
| Input rows R1-R12 | per `RELEASE_CHECKLIST.md` §7 | pending RC0 QF | pending RC0 QF |
| Unsupported (named in `SUPPORT.md` §1) | unsupported | n/a | n/a |

## 3. Known limitations

Carry over from `SUPPORT.md` §5, §6 and §8, updated at freeze:

- the `0.001` relative-RMSE diagnostic fails for CUDA versus CPU (reference: 24/24 tutorial movies, 0.002899-0.010082; not re-measured on RC0);
- no Tier D scientific gate (#61, #73);
- resume does not detect changed settings (#149 deferred);
- no rollback: a failed movie can leave a truncated or earlier per-movie file and an auxiliary `_PS.mrc`; a failed batch withholds the joint
  output and keeps healthy per-movie products (`SUPPORT.md` §6);
- a failed `logfile.pdf` render is non-fatal outside `--aggregate_only` (pending fix F1, `fix/rc0-logfile-failed-render`);
- host RAM with `--grouping_for_ps` on CUDA (one extra Fourier movie), per-geometry VRAM floor and unqualified out-of-memory behaviour
  (register item QM pending), EER upsampling 2 storage (about 75 GiB estimated for 144 groups, not run);
- decoder trust boundary: pending D1/D2;
- inherited macOS test results (`SyntheticRegression`, `MultiGpuScheduling` fail; `NativeMovieStaging` skips);
- data-dependent patch non-convergence retry (EMPIAR-10641, 10216);
- anything newly found during QF.

## 4. Failed and UNRUN checks

List every check that failed or was not run, with the reason. Do not drop an original failure.

| Check | Status | Reason / evidence |
|---|---|---|
| Native CUDA execution of the CUDA-to-CPU unweighted fallback (#198 C1) | UNRUN | pending RC0 QF |
| Forced out-of-memory on session initialisation (QM) | UNRUN | register item pending |
| Cross-backend CPU versus CUDA `compare_motioncorr.py --gate backend` per movie | UNRUN | needs a CUDA arm and GNU `time -v` logs |
| F1 merged, reviewed and tested | pending | #198 register F1 |
| Linux CPU build and full CTest on the frozen SHA | UNRUN | pending RC0 QF |
| CUDA build (no nvCOMP) full CTest, native | UNRUN | pending RC0 QF |
| CUDA + nvCOMP full CTest, native | UNRUN | pending RC0 QF |
| Real-format rows R1-R12 | UNRUN | pending RC0 QF |
| Example run inventory with Ghostscript installed | UNRUN | not run locally (no `gs`); pending RC0 QF |
| `run_dataset.py` success path on macOS | UNRUN | local attempt failed only because `gs` is missing (`RELEASE_CHECKLIST.md` §8) |
| Multi-GPU 1/2/4 on the frozen SHA, failure injection | UNRUN | pending RC0 QF |
| `SyntheticRegression` on macOS | FAILED (inherited) | max pixel diff 23.649856567382812; unchanged from main |
| `MultiGpuScheduling` on macOS | FAILED (inherited) | tomography endpoint validator; 73 of 74 checks |
| `NativeMovieStaging` on macOS | SKIPPED | Linux-only |
| nvTIFF/LZW, device EER renderer, nvCOMP widening | not in RC0 | #198 register |

## 5. Resource requirements

Peak host RSS and device memory per corpus family. The reference columns are the #186 measurements at main `116eb04a`
(before #178, #187, #195, #196, #197 and #185 merged); the RC0 columns are filled at QF.

Reference provenance. CPU: cpu64, AMD EPYC 7763, 64 cores, SMT off, 226 GB RAM, THP `madvise`, GCC 13.3.0, FFTW 3.3.10, libtiff 4.5.1,
binary SHA-256 `86a43e9f0fa0787ba7eef5270c65eee466857e493d7f6df6daa98de0b28bed53`; config L (`--patch_x 5 --patch_y 5`), dose weighting,
`taskset` to 1 or 8 CPUs, median of the unprofiled runs (`docs/workload_corpus/cpu/README.md`, `cpu/provenance.json`). GPU: 4GPUs GPU0
(A100 80 GB PCIe, driver 570.86.10), `taskset -c 96-103`, `--j 8 --gpu 0`, CUDA 12.8, nvCOMP 5.3.0.16, THP `madvise`, binary SHA-256
`79c88e4ce1f1cb5a445f4da34f195b31edd257d58f4706624678f61fe6d6166c`, inputs in tmpfs; VRAM is the NVML per-process peak (sampled, so a
lower bound) and includes the CUDA context (`docs/workload_corpus/gpu/README.md`, `gpu/provenance.json`).

| Family | Reference CPU RSS GiB, L, `--j 1` / `--j 8` | Reference GPU host RSS GiB, L | Reference VRAM GiB, G / L | RC0 RSS | RC0 VRAM |
|---|---|---|---|---|---|
| tutorial (3838 x 3710 x 24) | 2.75 / 3.19 | 0.4 | 3.2 / 3.3 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10028 (4096 x 4096 x 16) | 2.17 / 2.67 | 1.6 | 2.6 / 2.7 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10361 (5760 x 4092 x 62) | 11.24 / 11.99 | 1.7 | 11.6 / 12.3 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10641 (5760 x 4092 x 70) | 12.75 / 13.50 | 7.0 (includes the retry path) | 13.1 / 14.7 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10441 (11520 x 8184 x 50) | 36.31 / 39.09 | 5.0 | 37.0 / 39.3 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10474 Falcon 3 (4096 x 4096 x 58) | 8.62 / 9.16 | 5.3 | 7.9 / 8.8 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10474 Falcon 4 (4096 x 4096 x 144) | 21.19 / 21.35 | 12.0 | 18.6 / 20.0 | pending RC0 QF | pending RC0 QF |
| EMPIAR-12963 (4096 x 4096 x 39) | 5.91 / 6.47 | 3.7 | 5.5 / 6.2 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10164 (7420 x 7676 x 8) | 3.89 / 5.57 | 2.2 | 4.5 / 4.5 | pending RC0 QF | pending RC0 QF |
| EMPIAR-10216 (4096 x 4096 x 59) | 7.62 / 8.15 | 4.2 | 8.0 / 9.0 | pending RC0 QF | pending RC0 QF |

Source tables: `docs/workload_corpus/cpu/README.md` ("Peak RSS" table) and `docs/workload_corpus/gpu/README.md` ("Per-family result"
table). Rule of thumb from the GPU report: VRAM peak is two resident float32 movies (`2 x frames x nx x ny x 4 B`) plus 0.7-4.2 GiB;
estimates for 24, 40 and 48 GiB cards are arithmetic, not runs. Also record: scratch space per run, pinned host memory
(`MOTIONCORR_NVCOMP_PINNED_MAX_MB`, default 256 MiB per worker, `cuda_movie_session.cu:1544-1545`), per-worker RSS and VRAM at 1/2/4 devices,
and the 8-CPU or other CPU cap actually used. Add the two inherited host/VRAM behaviours: `--grouping_for_ps` on the resident CUDA
path downloads one extra Fourier movie to the host (`src/motioncorr_runner.cpp:3205-3212`), and the resident path needs two float-size
stacks on the device (EMPIAR-10441 peaked at 39.3 GiB). EER upsampling 2 quadruples movie storage (about 75 GiB estimated for 144 groups,
not run).

## 6. Measured performance

One row per measurement. A timing without all fields is not reported. Compare only rows with matching venue, allocation, THP setting,
binary, inputs and storage.

| Field | Meaning |
|---|---|
| source | exact SHA, clean tree |
| binary | path and SHA-256, build type, compiler, CUDA/nvCOMP versions |
| hardware | CPU model, GPU model/UUID, RAM, THP mode, persistence mode, venue |
| resources | CPUs and devices actually allocated, `--j`, `--max_io_threads`, locks held |
| inputs | files and SHA-256, replayed versus distinct movies |
| options | full command line |
| samples | repetitions, interleaving, excluded runs and why |
| variability | min-max or IQR, paired difference with interval |
| output verdict | product comparison performed (tool, profile, result), not only exit status |
| limitations | what the number does not show |

RC0 rows: **pending RC0 QF** (none recorded).

Reference rows (earlier SHAs; context only, not RC0 results):

| Row | source | binary | hardware, resources | inputs, options | samples, variability | output verdict | limitations |
|---|---|---|---|---|---|---|---|
| GPU, tutorial, config L, `--ingest auto` (witness `nvcomp`): 1.43 s whole process, 2 movies | `116eb04a`, clean | SHA `79c88e4c...6166c`, Release | 4GPUs GPU0 A100 80 GB, CPUs 96-103, `--j 8`, THP `madvise`, persistence off | 2 tutorial movies (hashes in `corpus.md`), corpus options, `--gpu 0` | 5 unprofiled repeats, 1.43 [1.41-1.51] s | exit 0 and product count only; no product comparison | tmpfs inputs, one GPU model, process start dominates a 2-movie run (about 1.2 s of 1.4 s) (`docs/workload_corpus/gpu/README.md`) |
| CPU, tutorial, config L, `--j 8`: 10.0 s whole process, 2 movies | `116eb04a`, clean | SHA `86a43e9f...8bed53`, Release `-O3 -DNDEBUG -fopenmp`, GCC 13.3.0 | cpu64, `taskset -c 0-7`, THP `madvise`, `OMP_PROC_BIND` unset | same 2 movies, corpus options, no `--gpu` | 2 of 3 planned clean repeats, 10.0 [9.9-10.0] s | exit 0 and product count; retained tree hashes only | warm page cache, host shared with other users' jobs on other CPUs (`docs/workload_corpus/cpu/README.md`) |
| Dataset endpoint, 24 tutorial movies, 4 x 8 CPUs versus 1 x 32 | `d7339fd` | SHA `ae13ab74...5307d`, Release, CUDA | 4GPUs, 4 A100 (one worker each), fixed 32-CPU budget | 24 tutorial movies, `run_dataset.py`, `--ingest auto` | 6 interleaved reps, publication 10.37 s (IQR 0.82) versus 13.87 s (IQR 0.55), paired difference -4.02 s (CI -4.70, -2.90) | all three arms identical to a single-process single-GPU run on 24 movies (MRC bytes outside the timestamp, normalised STARs, product presence) | host shared throughout; predates #176, #178, #187, #195-#197; not a fixed-budget claim for RC0 (`docs/multi_gpu/scaling/README.md`) |

Per-family GPU and CPU timing tables are in `docs/workload_corpus/{cpu,gpu}/`; do not copy them here without their provenance.

## 7. Sign-off

Maintainer review of this report, the scope decision and the tag are separate steps (`RELEASE_CHECKLIST.md` §10). pending RC0 QF.
