# Resident patch retry (issue #192)

When a resident patch alignment reports `converged=no`, the runner retries the patch through the
non-resident `alignPatch`. The retry used to download the whole real-space movie
(`downloadRealFrames`) and prepare the patch from host frames. It now builds the same input from
`d_Iframes`, which is still valid during patch alignment (`docs/vram_live_ranges.md`):
`CudaMovieSession::downloadPatchSpectra` runs `preparePatchInVram` without a window and copies the
full spectra to `Fpatches`. `cudaPreparePatch` forms the same group sums in the same frame order,
uses the same batched R2C plan and the same scale, and the retry still aligns through `alignPatch`.

The retry is kept. A failed first preparation, or a failure in the new step, takes the old download
path; a fatal error is classified as before.

## Evidence (4GPUs, A100, Release, 8-CPU lane; main `116eb04a` vs this branch)

- Stage split on EMPIAR-10641 L, steady movie, main, `--profile`, median of 3 passes (ms): patch
  alignment 10 398 = retry prep 4 900 + align 880 + download 4 656 (the remainder not inside any
  sub-stage). After: 1 411 = prep 687 + align 722.
- `mcprof compare`, 10641 L, 10 pairs: wall 29.21 -> 7.42 s, resolved faster
  (median B-A -21.84 s, CI -21.99..-21.68, noise 0.15 s). Peak RSS 7.0 -> 2.1 GiB.
  Report: `resident_patch_retry/compare_10641_L_report.md`.
- Product identity (`mcprof` identity: MRC header+payload, STAR, EPS): identical on 10641, 10216,
  10474 Falcon 3 and 12963, for L and for L with `--even_odd_split --save_noDW`. Normalised
  per-movie logs (timing/memory lines dropped) also match, including every retry RMSD line.
  Retried patches: 41 of 50, 30 of 50, 4 of 50, 2 of 25.
- Negative control: a build where every group gets group 0's spectrum fails identity on 10641 L
  (5 files, MRC core header at byte 76) and differs in 498 log lines.
- ctest on the candidate (Release, CUDA): 83 of 84 pass, including the #69 suites
  (PatchRetryState, CudaFaultMatrix, CudaErrorClass, CudaPreprocessingFailurePaths, CudaPatchBatch).
  `CiFailClosedControls` fails with "source archive without git metadata" because the tree was
  staged with `git archive`; it was not run on main.

## Limitations

- No retry converged in any run here, and none did in 12 further movie runs with 4x4, 6x6 and 7x7
  patch grids on 10641 and 10216 (main only). The product comparison therefore cannot see a retry
  preparation error by itself on these inputs; the log RMSD comparison and the negative control are
  what exercise it. The issue's "1 of 41 retries converged" did not reproduce.
- Two movies per family; the retry frequency over a dataset is not measured.
- Identity is against main built on the same host with the same flags; same-backend equality is not
  a scientific-equivalence claim.
- STAR optics (pixel size, 300 kV, Cs 2.7) were reconstructed from the EMPIAR metadata; the retry
  counts match the issue's table exactly.
