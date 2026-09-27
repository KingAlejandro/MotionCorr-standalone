# Issue 77 reviewed CUDA validation

## Exact code and venue

- Baseline: `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26` (current main at test launch).
- Characterization candidate: `5b9e5a4b7e441e6e056b4a9a1f6cf4e2bcf28bce`.
- Final candidate: `4934db76583fbfa62e5da6bda0c1bfd18ea79207` (alignment errors now throw; ordinary nonconvergence unchanged).
- SCARF gn3000, A100 SXM4 40GB, CUDA 12.8.61, GCC 11.5.0, exclusive allocation. Requested one GPU/eight CPUs; scheduler granted entire node. MotionCorr uses device 0, `--j 8`; builds use at most eight jobs.
- Release, CUDA ON, sm80, TIMING ON. Both final executables use identical flags; final baseline reuses the original immutable executable.
- All 24 RELION tutorial movies, gain reference, seed 1, 5x5 patches, B factor150, dose1.277/frame, optics from original STAR. Actual commands, input hashes, compiler cache and binary hashes are retained.

## Final source results (job3510657)

Completed exit0. Baseline executable SHA256 `5299ebd0aedce467ba0d0f605aaf2554fd940690656f7daaa694c40e5cbd0ab1`; final executable SHA256 `871626fc3c65f28d260d152fc4c150ede23b42b8f4fc670207e675ce181ee87c`.

Two full dataset comparisons (initial A/B and timed repeat):

- 24/24 corrected images, 341,735,520 pixels, normalized MRC headers, 25 STAR files, and 24/24 exact per-movie gates pass.
- Required coverage is fixed at24 images/25 STARs/24 per-movie pairs; zero/partial outputs fail closed.
- Native device process witnesses plus per-movie resident FFT/global/local/dose-weighted reconstruction witnesses pass all24 movies, without fallback markers.
- Missing/pixel/header targeted controls and incorrect output-root STAR control detect their specific defects. These are component controls, not full pipeline failure injection.
- Final baseline and candidate outputs in both runs have stored MRC payload bytes identical to the original baseline, including dimensions/mode/length/extended-header checks.
- Auxiliary comparisons remain FAIL:24 intentionally changed memory labels and4 PDFs. Every normalized log differs solely in the intentional label. Original overall FAIL records are retained, rather than weakening the numerical comparator.

Test-only LD_PRELOAD injection on real tutorial movie00021:

- Actual global alignment cache cudaMalloc failure: exit1, injected marker and allocation error, no successful global marker, no corrected image or joint STAR.
- Actual global alignment cufftPlanMany failure: same fail-closed outcome, with plan-creation error.
- Shim is separately compiled/hashed, never linked into production and never active for timing runs. These cases do not establish a complete device-error/local-stage/resource-exhaustion fault matrix.

One final paired timing:33.987s baseline vs31.308s candidate. This is n1 characterization, not proof of a stable7.9% end-to-end gain. Recorded patch alignment1.597s vs0.854s; global alignment0.276s vs0.251s; dose-weighting stage1.351s vs1.300s. Sampled process memory at200ms reached3486MiB for both; sampled maximum is not true high-water.

## Historical characterization of 5b candidate

Six retained paired full-dataset timings (no outlier exclusion):

| Pair | Baseline seconds | Candidate seconds |
|---|---:|---:|
| Initial1 |49.044|30.762|
| Initial2 |32.079|30.981|
| Initial3 |30.269|31.516|
| Confirmation1 |29.818|31.300|
| Confirmation2 |32.339|29.861|
| Confirmation3 |31.761|31.948|

Median paired ratio0.98585 and median paired delta-0.4555s. Variation includes candidate slowdowns and a large baseline outlier; full-run benefit is not established. The outlier mainly lies outside recorded stages; cause is unknown.

Patch alignment stage benefit reproduced: initial medians1.596->0.852s, confirmation1.595->0.849s (about47% lower). Custom patch kernel profile in initial pair1 was147.46->139.95ms (about5%); the large stage gain must not be described as47% faster kernel instructions. Dose kernel229.66->228.37ms was nearly unchanged.

All seven retained comparison sets pass required numerical/metadata gates. Payload repeatability passes13 trees against initial main. Original staging failure, path-normalization failure, v2 reports, stricter per-side v4 reports and all logs remain available. This characterization source had an error-handling regression subsequently fixed in4934; it is not the final merge candidate.

## Artifacts

- `issue77-final4934-complete-evidence.tar.gz`: SHA256 `e6d7957b849fe7f50e6b1d5b27f374b4ac2fcf9eea602a14453297f2aed21084`.
- `issue77-5b-characterization-evidence.tar.gz`: SHA256 `a4e76a6278861bac690f9ac11d8ae405f5359ce17c6e9e9e47ae6a7649e1b628`.
- Extracted final records: `raw-final/final-head-3510657`.
- Extracted characterization records: `raw-characterization/evidence-3510495`.

No CPU/RELION agreement or scientific equivalence claim is made by these same-backend regression checks. No merge was performed by the validation worker. No GPU jobs remain from this assignment.
