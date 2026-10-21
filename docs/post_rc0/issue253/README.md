# #253: CUDA inverse boundary projection

Candidate under POST_FREEZE_TEST_PLAN §9, class CUDA/shared. Base: main
`3691374061f782bc84531fd1c79d017ddcb5a7c2`. Implementation: `e539660c`; final
CUDA-test oracle: `adf990fd9801e1124814e3c4fcb30a3a7fd8ff42`. All subsequent
changes through `8b55d5da` were documentation/evidence only. The
[2026-10-21 review response](review-20261021/README.md) adds deterministic
test-only C2R invariant checks and supersedes the numerical mutant contract below.
[PR #254](https://github.com/KingAlejandro/MotionCorr-standalone/pull/254).

The CUDA inverse consumption scratch is projected on kx=0 and (only for even
nx) kx=nx/2: each ky pair becomes `(F(ky) + conj(F(-ky)))/2`.
Self-paired rows become real. Each thread owns both entries, so no in-place
read/write race is possible. Interior bins and resident spectra are unchanged;
projection is performed at consumption, rather than after each cumulative shift.
This chooses the existing FFTW real-inverse result, to rounding, including at
Nyquist corners; it does not introduce a separable Nyquist interpolation policy.
CPU code, peak fitting, convergence, gates and tolerances are unchanged.
Intentional CUDA product differences correct the invalid C2R input contract;
maintainer sign-off is required before merge (§9.2).

All five `cufftExecC2R` sites in `src/` can receive non-Hermitian input:

| Site (base line) | Input provenance | Action |
|---|---|---|
| `cuda_movie_session.cu:2120` | Full globally shifted resident spectrum, copied to inverse scratch | Project scratch, batch-one plan |
| `cuda_fft_prep.cu:254` | Host globally shifted spectrum, copied to device scratch | Project scratch, batch-one plan |
| `cuda_realspace_dw.cu:388` | Globally shifted spectrum with real symmetric dose weights; weights do not restore conjugacy | Project weighted scratch, owned or borrowed batch-one plan |
| `cuda_alignpatch.cu:625` | Weighted cross spectrum of shifted frames/reference; reduced-grid cutoff becomes a new x Nyquist boundary; cropping does not fold its omitted partner | Project CCF scratch for all frames before batched inverse |
| `cuda_alignpatch.cu:988` | Same CCF construction on windowed stacks in the batched patch path, including cumulative fractional shifts | Project each active patch's CCF scratch for all frames |

`rg -n cufftExecC2R src` finds no other site. `projector.cpp` uses forward R2C
and D2Z only. The alignment projection satisfies the real inverse contract and
matches FFTW's treatment of the existing cropped buffer; it does not change the
crop/folding policy or establish scientific correctness of that policy.

The new `CudaHermitianInverse` feeds identical FFTW R2C plus fractional-shift
bytes to the production session inverse, host fallback inverse and dose-weighted
inverse. It checks both frames and resident-spectrum preservation. The fixed
4096² case must agree with FFTW. The original compiled session mutant used a
numerical mismatch as its negative control; that hardware-specific contract is
superseded by the deterministic five-site invariant/mutation coverage linked
above. Small integer,
zero, x-only, y-only, combined and even/odd controls cover boundary geometry.
`--matrix` also characterises unprojected `cufftMakePlanMany` batch 1/2 and the
fixed production paths at all five requested full-frame sizes. Raw plan results
are characterisation, not the production regression's pass condition.

## Venue and test policy

4GPUs (`4-gpu-vm`), NVIDIA A100 80 GB PCIe, GPU3 UUID
`GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, CPUs `88-95`, eight threads for
movie processing. The GPU3 correctness flock was held, the benchmark lock
checked, and the other attribution campaign used a separate lane. Scratch:
`/mnt/clathrin/alex-motioncorr-253/`. Release builds use CUDA 12.8.61,
cuFFT 11.3.3 (`11303`), GCC 13.3.0 and optional nvCOMP 5.3.0.16.
The supplied standalone source was copied unchanged to `original-alex-c2r2.cu`
in that scratch and hashed. It was not executed; the production regression and
PlanMany controls provide the native record here.

The existing dose test keeps all 100 exact null/polynomial, timed/untimed
reconstruction checks and 1,365 exact weighted-Fourier-frame checks. Its inverse
oracles now apply the boundary policy independently on the host, including the
small R2C conjugacy roundoff encountered by the synchronization control. The
normalization, interpolation, resident-spectrum preservation, allocation,
completion, failure and exact-byte checks remain. The launch count includes
one projection launch per inverse. No existing numerical threshold was relaxed.

## Native fail/pass and plan geometry

Identical FFTW-generated half-spectrum bytes, shift `(0.3, 0.2)` pixels,
4096×4096; maximum error divided by maximum absolute FFTW output:

| Production path | Main | Fixed |
|---|---:|---:|
| Session global inverse | 0.0121215384 FAIL | 5.22078981e-7 PASS |
| Host fallback inverse | 0.0121215384 FAIL | 5.22078981e-7 PASS |
| Dose-weighted inverse (zero-dose equal weights) | 0.0121215657 FAIL | 4.64054968e-07 PASS |

The session launch-removal mutant gives the main-sized error and the normal test
exits **1**. The fixed test exits **0**, main exits **1**. In the original
evidence, the mutant's
`--expect-mismatch` control exited **0** only after detecting a numerical mismatch;
a CUDA/setup error is not an accepted mismatch. The new test's bounds were set
before measurement: maximum relative error and normalized RMS error ≤2e-6.
All small integer/zero/fractional and even/odd controls pass on the fix.

Full-frame production uses `cufftMakePlanMany`, rank 2, **batch 1**, looping over
frames with the session's shared work area. Both resident frames are checked.
The supplemental raw batch-2 control samples its first output frame. The raw
controls deliberately retain the invalid input and are characterization, not
passes of the production regression. Values below are maximum relative error:

| Width × height | Raw PlanMany batch 1 | Raw batch 2, first frame | Fixed production maximum (all three paths) |
|---|---:|---:|---:|
| 4096 × 4096 | 0.0121215384 | 0.0121215384 | 5.22078981e-07 |
| 5760 × 4092 | 6.04861459e-07 | 6.04861459e-07 | 6.04861459e-07 |
| 3710 × 3838 | 6.25863692e-07 | 6.25863692e-07 | 6.80898456e-07 |
| 7676 × 7420 | 6.95158292e-07 | 6.95158292e-07 | 6.95158292e-07 |
| 11520 × 8184 | 5.67283366e-07 | 5.67283366e-07 | 5.94222386e-07 |

The leak is reproduced in the actual production plan at 4096². No leak above
rounding is observed in this fixture at the other four sizes. This is a result
for CUDA 12.8.61/cuFFT 11.3.3 on this A100, not a claim about all cuFFT versions.

## Movie products

Input: `FoilHole_14961495_Data_14966722_14966723_20180615_1739_Fractions.mrc`,
SHA-256 `f399bd30bfe1a9807bd494c348bfcf7d4aee312ccc18140b05abb1453ac23a56`.
The input STAR has 0.517 Å/pixel and 300 kV. Recipe:
`--use_own --dose_weighting --save_noDW --bfactor 150 --seed 1 --dose_per_frame 1.0 --expected_frames 59 --j 8`,
with no patch arguments for G, and `--patch_x 5 --patch_y 5` for L.
`--save_noDW` retains both requested products. CUDA arms use `--gpu 0 --ingest auto`.
Main and fixed GPU arms both use **CUDA-only Release** builds. Main's CPU
reference is the CUDA-linked executable without `--gpu`; the fixed CPU reference
is the CPU-only executable. Their CPU outputs are controlled below.

Eight runs exit 0. Every CUDA arm has a PID-joined witness on the lane UUID,
the resident global/DW reconstruction log markers and no CUDA/cuFFT or fallback
errors. All image numbers are `RMSE / population_std(CPU pixels)` from
`compare_motioncorr.py --gate backend`, with complete coverage and GNU `time -v`
logs. Every backend record remains **FAIL** (including absolute image-RMSE
failures); these records are not an acceptance gate for this defect fix.

| Alignment | Source | Non-DW relative RMSE | DW relative RMSE | Backend record, non-DW / DW |
|---|---|---:|---:|---|
| Global only | main | 0.019640608003 | 0.0165908778956 | FAIL / FAIL |
| 5×5 local | main | 0.823504057221 | 0.434362159063 | FAIL / FAIL |
| Global only | fixed | 0.0193900369914 | 0.0164632326694 | FAIL / FAIL |
| 5×5 local | fixed | 0.0369229932125 | 0.0173290738245 | FAIL / FAIL |

The global-only runs have no local model. For 5×5, the published STAR polynomial
is compared both as its 36 serialized coefficients and as a field evaluated at
all 59 frame indices `z=0..58` on a 21×21 normalized square `[-0.5,0.5]²`.
Each relative RMSE divides by the population standard deviation of the matching
CPU coefficient/field samples. This measures the **serialized model**, including
its formatting precision; it is not an in-memory full-precision model capture.

| Source | Coefficient relative RMSE | Field relative RMSE | Field RMS difference (px) | Field maximum difference (px) |
|---|---:|---:|---:|---:|
| main | 0.374524019005 | 0.206828688832 | 1.18096611666 | 6.26187694016 |
| fixed | 0.00784136384586 | 0.00472495757589 | 0.0269789207255 | 0.1762377734 |

CPU controls, G and L: non-DW and DW pixels/core headers are identical, MRC
labels match after timestamp normalization, and movie STAR bytes are identical.
The 5×5 discrepancy is substantially reduced in this movie; global-only
relative image error changes little. **S1 is not closed**, and these results do
not establish downstream scientific equivalence or attribution across families.

## Release CTest and re-entry scope

| Configuration | Tested source | Passed / collected | Failed | Skipped |
|---|---|---:|---:|---:|
| CPU Release | `e539660c` | 74 / 74 | 0 | 0 |
| CUDA Release | `adf990fd` | 110 / 110 | 0 | 0 |
| CUDA+nvCOMP Release | `adf990fd` | 113 / 113 | 0 | 0 |

`e539660c..adf990fd` changes only `tests/cuda_dose_normalization.cpp`, which is
excluded from the CPU build. CPU production/build sources are identical; its
full CTest was not repeated for that CUDA-test-only delta (§9 tests-only rule).
All three collection validators pass. The adapted QF #123 compact-ingest matrix
also passes **16/16 cases, 28 native arms per CUDA build**, with gain-effect and
UUID controls, source `adf990fd`, 0 modified files. The full suites include the
relevant truncation, reconstruction, patch retry, failure/publication and D11
controls; the matrix adds native route/product controls.

Retained earlier results are not silently discharged: the initial full nvCOMP
suite at `62b63b75` is **111/113**, failing the old launch-count assertion and
unprojected inverse oracle. The independently projected exact oracles pass,
then the **entire** nvCOMP suite above is rerun. The initial inverse harness
also has two superseded setup failures (missing caller-owned dose output and
odd-stride multi-frame alignment); their exit-2 logs are retained separately.
The final main/fixed/mutant evidence uses the corrected identical test source.

Not rerun on this candidate: the full seven-family QF route campaign, the full
EER/#204/resident-retry dataset replays, multi-GPU publication, optional
`CudaU16FailurePaths` (not registered without its external fixture), sanitizer,
macOS/other toolchains, other GPUs/cuFFT versions, D14 timing and downstream
CTF/FSC/B-factor tests. Their existing RC0 records retain their earlier SHAs;
this PR does not requalify those rows, change supported configurations or set a
new tag. Independent review, current-head CI and maintainer sign-off on the
intentional CUDA product difference remain merge requirements.

## Retained evidence

- [validation.json](validation.json): revisions, counts, witnesses, input identity and build configuration.
- [inverse-matrix.csv](inverse-matrix.csv), [products.csv](products.csv), [products-summary.json](products-summary.json): full-precision results and definitions.
- [raw.tar.gz](raw.tar.gz), indexed by [raw-index.json](raw-index.json): configure/build logs, full CTest/JUnit, fail/pass/mutant logs, per-arm commands/hashes/time logs/witnesses/STARs, all backend JSON reports, matrix records and execution scripts. No movies, images, executables or libraries are committed. Full MRC products remain in the owned remote scratch.

Scripts are retained as execution records, with their venue-specific paths.
Use a fresh scratch directory when replaying them. Main is a git archive of the
base SHA plus a test-only CMake/source overlay; no main production source is
changed. The supplied standalone source is retained on the host, not substituted
for the production regression.

Implementation CI on `adf990fd`: [run 39351741856](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39351741856)
passes Ubuntu build/smoke and CUDA compile-only. The latter is compilation,
separate from the native records above. The GPU lane was released after all
native work; the other campaign's processes and evidence were left intact.
