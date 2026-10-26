# Bounded source review: CUDA inverse replay helper

Reviewed revision: `341386165498b9aba163ebe5f3c62780e359abd4`, `docs/cuda_cpu_boundary_20261026/replay.cu`, plus the used `tComplex` constructor and NewFFT dispatch. Read-only inspection; no build, replay, movie run, or production-source edit by parent.

## Finding requiring correction

At replay.cu:70, the CUDA inverse path allocates `std::vector<fComplex> stack(n*count)` but loads only frames 0 and 4 before copying the entire 24-frame batch to the GPU. `src/jaz/single_particle/t_complex.h` defines a user-provided empty default constructor, so this vector allocation does not initialize the scalar real/imaginary members. The remaining 22 spectra are indeterminate.

The selected frames' outputs might be unaffected by other independent batches, but the full replay input is not defined or reproducible. Requested repair: initialize all slots explicitly to complex zero, retain the original replay attempts, and repeat only affected inverse controls in a new namespace. No recapture, forward/window replay repeat or movie producer is needed. Earlier inverse grades remain provisional until the corrected replay is checked. Production captures and their forward-FFT boundary observation are outside this finding.

## Required interpretation

At replay.cu:72, the CUDA inverse wrapper always applies `projectHermitianColumns` before cuFFT. Its raw-input comparison therefore includes native Hermitian projection and is compatibility behavior, rather than an unchanged-input pure inverse-FFT comparison. For separately valid projected controls, require byte identity of the actual post-projection input and the supplied input before assigning remaining differences to the inverse transform.

## Non-findings / limits

The CPU forward helper prints a separately constructed ESTIMATE plan while execution uses NewFFT's cached-plan dispatch; both use the same default flags and layout/alignment key. This inspection does not independently prove native plan-instance identity. No production operator defect or scientific acceptance follows from this review.

Reviewer: parent Codex / gpt-6.1-sol, high. Findings were sent to the isolated CUDA owner before final replay interpretation. A fix/replay result is not claimed here.
