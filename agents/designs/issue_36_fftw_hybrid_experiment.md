# Issue 36: experimental FFTW global CCF on the CUDA path

## Question

Can the current CUDA movie pipeline retain its GPU residency and most of its speed while reducing CPU-relative corrected-image RMSE by making only the global CCF inverse transform and peak decision use the CPU FFTW algorithm?

## Scope

- Branch from PR #51 head `0c7d68f`. Enable the first experiment with `MOTIONCORR_EXPERIMENTAL_GLOBAL_FFTW=1` for global alignment only. After the global-only control, also try `MOTIONCORR_EXPERIMENTAL_ALL_FFTW=1` to use the same FFTW CCF and peak path for global and local patches. Without either flag, normal CUDA remains unchanged.
- Form reference and weighted CCF spectra on the GPU as today. Transfer each global CCF spectrum to host, run single-precision FFTW C2R with `FFTW_ESTIMATE` and no extra normalization, and use the CPU `RFLOAT` peak search and quadratic interpolation. Preserve double-precision recentering, accumulation, and convergence decisions; convert to float only for the existing GPU Fourier-phase input.
- Retain the resident movie Fourier frames and all later CUDA stages. Report host FFTW and transfer time, transferred bytes, and GPU memory. Do not alter any numerical gate or silently use a recorded CPU trajectory.

## Acceptance for this experiment

1. A CUDA build succeeds. With the environment variable absent, corrected pixels and motion metadata remain byte-identical to this branch's base on a fixed movie.
2. On tutorial movies `00021` and `00046`, compare all global shifts, corrected-image relative RMSE, and STAR metadata with a same-source CPU reference. The unchanged image gate is `0.001`; an improvement is reported even if it does not pass.
   If global-only correction passes but the full 5×5 configuration fails, evaluate the all-patches flag against the same CPU reference to isolate the local CUDA alignment contribution.
3. Compare paired full-process wall times and peak whole-device VRAM of normal CUDA and hybrid on the same GPU, build, inputs, and options. Avoid claiming speed preservation from unpaired or contended measurements.
4. Use at most eight logical CPUs on `4GPUs` (`taskset -c 96-103` around the top-level build/run), one MotionCorr benchmark at a time, and leave other users' processes alone. Route independent CPU-only reference work to `cpu64` when feasible.

The Issue #36 FFTW replay and common-trajectory controls motivate this experiment but do not guarantee a pass on the newer resident CUDA pipeline.
