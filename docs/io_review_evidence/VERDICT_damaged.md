# PR #91 (issue #86) — evidence verdict matrix

Gathered 2026-09-27. **Evidence only: no merge, no production source change.**

## Pinned identity

| | value |
|---|---|
| PR #91 code head | `cb9c0a202d2fb12649560ff683c866a6679b13df` |
| base (main) | `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26` |
| PR #91 HEAD tree | `f826d8bbae56c533fb9190294ecf2f3962eb2f06` |
| main HEAD tree | `fbe9469af3401d618fca0698ccd6f120d335679f` |

`git write-tree` on the staged working tree equals `rev-parse HEAD^{tree}` on
every machine used, and `git status --porcelain -uno` is empty — the only
untracked entry is the out-of-source build directory. Nothing was compiled from
a path that differs from the code head
(`raw/cpu/source-tree-identity-cpu.txt`).

| binary | sha256 |
|---|---|
| main, CPU | `28918ae8438f1e953eda6648d6178544fc3b431158c41cf9907d67f3d8513a1d` |
| pr91, CPU | `0dcb11a35c395bd94303bfda00225ce3ad8107b3ec4e7128d1a36f3afea3fd0e` |
| main, CUDA | `1d4dd13cb675b6bb563787070ed209e9479f9b4b9f0a7f1a170c816f387d80b8` |
| pr91, CUDA | `e8de1cb7fc3e0ca2734abf9c4579d463605c481ddb7957400c00bb66f231abc1` |

Build configuration, CPU: `Release`, `CUDA:BOOL=OFF`, `TIMING:BOOL=ON`,
`/usr/bin/c++`. CUDA: `Release`, `CUDA:BOOL=ON`, `sm80`, `TIMING:BOOL=ON`,
CUDA 12.8.0, configured and built inside the exclusive A100 allocation.

The harness copies in `harness/` are the ones that ran, verified by digest
against the executing machine rather than assumed:

| harness file | md5 |
|---|---|
| `damaged_matrix.py` | `413ecbf902c05fb712c19f8fce551a76` |
| `resume_matrix.py` | `349023a5c074c7be52973d9a4bdf201c` |
| `compare_outputs.py` | `e2dfd9c828be5303243a7d82c30ecf62` |

CPU host `small-refmac-machine`, 64 cores, shared. The damaged and resume
matrices were pinned to disjoint core sets (48-55 and 40-46) so they could not
contend with each other; neither is a timing measurement, so other users' load
on the box does not affect their verdicts.

## Verdict matrix

| # | acceptance item | verdict | evidence |
|---|---|---|---|
| 1 | truncated / missing / corrupt-header input, damaged first and last, `--j 1` and `--j 4` — 12 graded rows | **PASS 12/12** | `raw/cpu/pr91_damaged_matrix_pr91.json` |
| 2 | nonzero, non-signal exit on damaged input | **PASS 12/12** | same, `checks.clean_failure_not_signal` |
| 3 | failure names the damaged movie | **PASS 12/12** | same, `failure_naming` |
| 4 | healthy per-movie image + model complete on a failed batch | **PASS 12/12** | same, `products.per_movie` |
| 5 | joint STAR and PDF withheld on a failed batch | **PASS 12/12** | same, `products.joint` |
| 6 | pipeline failure marker written, success marker absent | **PASS 12/12** | same |
| 7 | `--only_do_unfinished`: healthy not regenerated (hash **and** mtime) | **PASS** | `raw/cpu/pr91_resume_pr91.json` |
| 8 | `--only_do_unfinished`: damaged movie retried, per the runner's own work list | **PASS** | same |
| 9 | after replacing damaged input with healthy data: completion + joint outputs | **PASS** | same |
| 10 | same matrix on `main` (is any of this new?) | **main FAILS 6/12 — see §10** | `raw/cpu/pr91_damaged_matrix_main.json` |
| 11 | 24-movie same-backend A/B vs main, CUDA | **PASS (graded)** | `raw/cuda/pr91_outputs_cuda_j8.json` |
| 12 | native CUDA execution witness | **PASS** | §5 |
| 13 | unit suite at the code head, CPU | **PASS 11/11** | `raw/cpu/ctest-cpu-all-heads.log` |
| 14 | silent short-decode of a partially truncated TIFF | **OBSERVED — not graded, not fixed** | §4 |

## 1–6. The damaged-input failure contract

Batches of three tutorial movies, one of them damaged, run with
`--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5
--bfactor 150 --gainref Movies/gain.mrc --seed 1` and `--pipeline_control`.
Four damage modes × damaged-first / damaged-last × `--j 1` / `--j 4` = 16 rows,
of which 12 are graded contract rows and 4 are observation rows (§4).

Every graded row: 9/9 checks true.

```
nonzero_exit               true
clean_failure_not_signal   true      <- not a SIGABRT from an escaping exception
damaged_movie_named        true
healthy_outputs_complete   true
damaged_output_absent      true
joint_star_withheld        true
joint_pdf_withheld         true
failure_marker_written     true
success_marker_absent      true
```

`signal_deaths: 0` across all 16 rows. This is the point of the change: an
exception escaping an OpenMP structured block calls `std::terminate`, and the
matrix distinguishes a clean nonzero exit from a signal death rather than
accepting "it failed" as sufficient. The `--j 4` rows exercise the
multi-threaded path, where the failing frame is the one whose exception is
rethrown serially.

Damage modes, with the boundary measured rather than assumed:

| mode | what it is | result |
|---|---|---|
| `truncated` | 1 MiB prefix of a 131,245,904-byte movie — no complete IFD survives | graded |
| `missing` | file absent | graded |
| `corrupt_header` | first 8 bytes overwritten with `00 ff 00 ff de ad be ef` | graded |
| `truncated_partial` | 43,748,634-byte prefix — some complete IFDs survive | **observation, §4** |

Healthy movies in a failed batch are complete, hashed, and their decoded frame
count is read back out of the runner's own log (`Movie size: X = 3710 Y = 3838
N = 24`), so "complete" means the full 24 frames, not merely that a file
exists.

## 7–9. `--only_do_unfinished` resume

Three runs, same working directory.

**run1** — damaged input present. Exit 1, clean failure, both healthy movies
complete, damaged output absent, joint STAR and `logfile.pdf` withheld, failure
marker written, success marker absent. 7/7.

**run2** — rerun with `--only_do_unfinished`. Exit 1. For each healthy movie,
both the corrected image **and** the model file are unchanged by sha256 **and**
by mtime (`mtime_ns` recorded on both sides; the harness sleeps 1.1 s between
runs so the filesystem timestamp granularity cannot mask a rewrite). The
healthy movies do not appear in the runner's printed work list; the damaged
movie does, and is named in the error. Joint outputs still withheld, failure
marker written. 8/8.

The work list is the runner's own, not the harness's reading of the
filesystem — run1 scheduled all three movies, run2 scheduled one:

```
run1  scheduled: 20170629_00021_frameImage, 20170629_00022_frameImage, RESUME_frameImage
run2   to correct beam-induced motion for the following micrographs:
       (skipping all micrographs for which a corrected movie already exists)
        * Movies/RESUME_frameImage.tiff
run2  ERROR: Image::openFile cannot open: Movies/RESUME_frameImage.tiff
```

**run3** — damaged input replaced with healthy data, `--only_do_unfinished`
again. Exit 0, all movies complete, the formerly damaged movie now produced,
the previously finished healthy outputs *still* not regenerated,
`corrected_micrographs.star` and `logfile.pdf` present, the joint STAR covering
all movies, success marker written and failure marker absent. 9/9.

`main` passes the same three runs identically (`raw/cpu/pr91_resume_main.json`)
— the resume behaviour is not something PR #91 introduces, and the evidence says
so rather than crediting it.

## 10. The same matrix on `main` — what the change actually buys

The identical harness, identical inputs (same
`damaged_input_sha256` per mode), identical options, run against the `main`
binary `28918ae8…`. This is the row that stops §1–§6 from being a list of
things that were already true.

```
main   rows 16   graded 12   pass 6   fail 6   signal_deaths 0   overall FAIL
pr91   rows 16   graded 12   pass 12  fail 0   signal_deaths 0   overall PASS
```

All six `main` failures are the same single check, and they fall in one place:

| row | main | pr91 |
|---|---|---|
| `truncated_damaged_first_j1` | **FAIL** 0.01 s, healthy 0/2 | PASS 81.74 s, healthy 2/2 |
| `truncated_damaged_last_j1` | PASS 81.16 s, healthy 2/2 | PASS 81.57 s, healthy 2/2 |
| `missing_damaged_first_j1` | **FAIL** 0.01 s, healthy 0/2 | PASS 82.19 s, healthy 2/2 |
| `missing_damaged_last_j1` | PASS 81.01 s, healthy 2/2 | PASS 83.56 s, healthy 2/2 |
| `corrupt_header_damaged_first_j1` | **FAIL** 0.01 s, healthy 0/2 | PASS 82.73 s, healthy 2/2 |
| `corrupt_header_damaged_last_j1` | PASS 80.92 s, healthy 2/2 | PASS 82.72 s, healthy 2/2 |
| `truncated_damaged_first_j4` | **FAIL** 0.01 s, healthy 0/2 | PASS 33.61 s, healthy 2/2 |
| `truncated_damaged_last_j4` | PASS 34.04 s, healthy 2/2 | PASS 33.84 s, healthy 2/2 |
| `missing_damaged_first_j4` | **FAIL** 0.01 s, healthy 0/2 | PASS 34.73 s, healthy 2/2 |
| `missing_damaged_last_j4` | PASS 34.84 s, healthy 2/2 | PASS 34.37 s, healthy 2/2 |
| `corrupt_header_damaged_first_j4` | **FAIL** 0.01 s, healthy 0/2 | PASS 33.86 s, healthy 2/2 |
| `corrupt_header_damaged_last_j4` | PASS 34.58 s, healthy 2/2 | PASS 33.66 s, healthy 2/2 |

The failing check is `healthy_outputs_complete`, and only that check — the
other eight are true on every `main` row too. `main` exits 1 cleanly, names the
damaged movie, withholds the joint outputs and writes the failure marker; what
it does not do is *finish the rest of the batch*. When the damaged movie is
first in the list, `main` aborts in 0.01 s having written nothing at all, and
the two healthy movies that would have taken ~81 s (j1) or ~34 s (j4) are
simply lost. When the damaged movie is last, `main` passes — not because it
isolates the failure, but because there was no work left to lose.

That ordering dependence is the defect, and it is why grading only
damaged-last rows would have shown nothing. Under PR #91 the wall time and the
healthy output set are the same whether the damaged movie is first or last.

The failure message also changes. `main`:

```
ERROR:
Cannot read file Movies/DAMAGED_frameImage.tiff It does not exist
```

PR #91 keeps the underlying error and adds an aggregate at
`motioncorr_runner.cpp:640`:

```
ERROR:
Motion correction failed for 1 movie(s): Movies/DAMAGED_frameImage.tiff.
Successful per-movie outputs were retained; joint output was not generated.
```

so `failure_naming` reads `damaged_movie_named: true, aggregate_message: true,
retention_message: true` on PR #91 against `true / false / false` on `main`.
The harness grades only `damaged_movie_named`, which both heads satisfy; the
other two are recorded, not graded.

`signal_deaths: 0` on **both** heads. The `std::terminate` risk from an
exception escaping an OpenMP structured block is real in the source, but it was
not observed on either head in these 16 rows — so PR #91's exception-capture is
recorded here as *not regressing* the exit discipline, not as fixing an
observed crash. Claiming otherwise would overstate what the run shows.

## 4. Observation: a partially truncated TIFF is decoded short, silently

**This is recorded, not fixed, and it is not caused by PR #91.**

A tutorial movie truncated to 43,748,634 of its 131,245,904 bytes is accepted.
The reader decodes **8 frames of 24** and the run completes:

```
exit_code 0, exit_kind "clean_success"
DAMAGED_frameImage: frames_decoded 8      (healthy movies: 24)
corrected image written, model written
corrected_micrographs.star  present
logfile.pdf                 present
success marker written
```

The short count *is* recorded, in the per-movie log: `Movie size: X = 3710
Y = 3838 N = 8`. It is simply not treated as an error. libtiff's complaints
(`TIFFFetchDirectory: Can not read TIFF directory count.` /
`TIFFReadDirectory: Failed to read directory at offset 49168762.`) go to stderr
and stop nothing.

Where the boundary sits, measured by feeding prefixes of a real movie to the
reader:

| prefix | outcome |
|---|---|
| 64 KiB | read fails, exit 4 |
| 1 MiB | read fails, exit 4 |
| 8 MiB | decodes as **1** frame of 24, run completes |
| 40 MiB | decodes as **7** frames of 24, run completes |
| 43.7 MiB (1/3) | decodes as **8** frames of 24, run completes |

So the contract rows in §1 use a 1 MiB prefix — short enough that the *read*
fails, which is what the failure contract is about — and the partial case is
carried as a labelled observation row excluded from the grade. Both code heads
behave the same way on it, so this is pre-existing behaviour of the TIFF reader
and not a regression introduced here.

### What this means for PR #91's scope

Stated plainly: **PR #91 does not catch all damaged input.** It changes what
happens *after* the reader rejects a movie — the failure is isolated, named and
aggregated, healthy outputs survive, joint outputs are withheld. It does not
change *when* the reader rejects a movie. A truncation that destroys the TIFF
directory chain is caught (§1); a truncation that leaves a prefix of intact
IFDs is not caught by either head, because the reader reports success with a
smaller `N` and nothing downstream compares that `N` to anything.

This is a gap in the reader's damage detection, not a defect in this PR, and it
is the reason the four `truncated_partial` rows are labelled OBSERVED rather
than FAIL: grading them would be grading `main`'s reader through PR #91's
diff.

### Proposed follow-up acceptance criterion (for a separate issue, not this PR)

Offered as a testable criterion rather than a patch; no production source was
changed to satisfy it.

> When the frame count decoded from a movie is smaller than the frame count
> the input metadata declares for that movie, the runner must treat the movie
> as damaged and route it through the same failure path as an unreadable
> movie — nonzero non-signal exit, the movie named, healthy per-movie outputs
> retained, joint STAR and PDF withheld, failure marker written.
>
> Negative control the criterion must survive: a genuinely short movie whose
> declared and decoded frame counts agree must still process normally, so the
> check cannot be "N < 24".

Two notes for whoever picks that up. First, the declared count has to come
from somewhere authoritative — the input STAR or an explicit `--n_frames`-style
option — because the truncated file's own directory chain is exactly what is
untrustworthy. Second, the existing harness already produces the input for such
a test: `harness/damaged_matrix.py` builds the partial-truncation fixture and
reads the decoded `N` back out of the runner's own log, so the criterion can be
graded by flipping those four rows from OBSERVED to graded once a fix exists.

## 11. Twenty-four-movie same-backend A/B on CUDA

`main` and the PR #91 head, same exclusive A100 allocation, same options, same
input, complete 24-movie tutorial inventory.

```
artifacts_total 109   artifacts_pass 105   artifacts_fail 4
corrected_images_compared 24   corrected_images_pass 24
total_pixels_compared 341735520
star_files_compared 25
per_movie_exact_gate_pass 24 / 24
controls_all_detected true
overall_graded PASS   overall_auxiliary FAIL
```

The four auxiliary failures are `header.pdf`, `batch.pdf`, `all_batches.pdf`
and `logfile.pdf`. A **main-vs-main control** — the same binary run twice into
two output directories on the same allocation — fails on exactly the same four
files, with exactly the same counts
(`raw/cuda/selfcontrol_main_vs_main_cuda_j8.json`). Inflating the PDFs' Flate
streams shows why: Ghostscript's `CreationDate`/`ModDate`/XMP timestamps and
generated `DocumentID`, plus the absolute path of the `_shifts.eps` file drawn
as visible text in the plot together with the text-matrix offset that follows
from that string's rendered width. The offset is a consequence of the glyphs,
so no normalisation can remove it. The comparator reports it as FAIL anyway, in
its own `overall_auxiliary` field, rather than hiding a difference it cannot
explain.

Corrected images are bitwise identical over 341,735,520 pixels; headers are
compared in full including the label block, with the RELION clock stamp
normalised and that normalisation disclosed in `normalization_patterns`.

## 5. Native CUDA execution witness

Compile-only evidence is not counted.

**Positive.** `Using CUDA acceleration on GPU device 0 for global alignment.`
in every run (`raw/cuda/run-*.stdout`). `nvidia-smi --query-compute-apps`
sampled every 2 s *during* each run names the `motioncorr` binary resident on
the device — 14 samples for the pr91 run, at 428–3262 MiB
(`raw/cuda/gpu-sample-pr91.txt`). `ldd` shows `libcudart.so.12` and
`libcufft.so.11` from CUDA 12.8.0 (`raw/cuda/cuda-linkage.txt`).
`ctest -R Cuda` → `CudaWrapperUploadFailure` passes on the hardware
(`raw/cuda/ctest-cuda-pr90.log`).

**Negative.** `--gpu 99` on the CUDA build exits 1 with `Invalid GPU device ID
99. Found 4 CUDA device(s).` (`raw/cuda/negctl-bad-device.log`). The CPU build
of this same head (`CUDA:BOOL=OFF`, zero CUDA libraries linked) rejects
`--gpu 0` with exit 1 and `--gpu was specified with --use_own, but MotionCorr
was built without CUDA support (-DCUDA=ON).`
(`raw/cpu/cpu_negative_control_gpu.log`) — the marker cannot be printed by a
build with no CUDA in it.

Allocation: SCARF `-p gpu --gres=gpu:1 --exclusive --constraint=scarf23`, node
`gn3000`, 4×A100-SXM4-40GB, no other compute apps on the device at job start.
Builds ran inside the allocation.

## What was deliberately not done

* No independent-dataset acquisition; the tutorial inventory already present is
  the whole input set.
* No fix for the observation in §4. Preserving the failure and reporting it was
  the instruction; changing the reader is outside evidence ownership.
* No relaxation of any existing comparator, gate or threshold.
* No merge, no new PR, no source change.

## Standing caveat

Every comparison here is *same-backend*: one backend, two code heads. It does
not speak to CPU/CUDA agreement, to RELION parity, or to scientific
correctness. The historical CPU/RELION Gate 2 failures and the noisy-truth
characterisation recorded elsewhere in the repository remain open.
