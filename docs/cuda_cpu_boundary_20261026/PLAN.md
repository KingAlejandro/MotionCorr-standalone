# Frozen two-case CUDA/CPU boundary plan, 26 October 2026

Frozen before new producer measurements. Owner: cuda-cpu-first-divergence branch,
worktree t3-5b6913e1; no changes to PR287/PR282 worktrees.

Base b305b23bc7572aaafb0a7fa9fdfdd0c350fb4ce3, fast-forward from c8844894.
`git diff e77a51a220cb0d91f4ac3c7fac211876d0c6833f HEAD -- .
':!docs/post_rc0/c1-20261022'` is empty. Read AGENTS.md, gate_contract.md,
issue36 latest discussion, issue238 latest discussion, C1 ACCEPTANCE_PACKET.md,
and W4 CLOSURE-AND-MATCHED-RESULTS.md at t3-6c3dca0d. M1 HELD.

## Inventory and choice

C1 current-source binaries and completed CPU/GPU G/L tutorial products exist at
4GPUs:/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb.
CPU 5692c6dc..., CUDA 34e76812..., nvCOMP d7c4e2e3.... C1 products used
CPU8-9/GPU3 and different ingest/build configurations. Reuse them for descriptive
endpoint context, not same-state operator or matched-resource cost claims.
Historical issue36 captures remain under /home/alex/MotionCorr-issue36-*;
their source predates C1 and they cannot establish a current first divergence.
W4 captures use 805d9de2/#275, CPU allpatch closure already complete; no repeat.
No current-source stage capture hook exists in src at this base. Refresh capture
inventories by checking these specific retained directories and their receipts.

Predetermined pair: tutorial 20170629_00021_frameImage.tiff and 00046.
The C1 packet does not identify a better same-state pair. Do not select cases
from new outcomes. Source/input/config/binary hashes precede each producer.

## Resources

Only 4GPUs (4-gpu-vm), GPU2 UUID
GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598; CPU80-87, max8 threads.
15:13:48Z hardware: A10080GB PCIe, AMD EPYC7452, 124 logical CPUs,
594GB scratch free; all GPUs idle/1MiB and no listed held MotionCorr locks.
Conditional recheck at launch: append-open flock -n correctness GPU2, CPU80-87,
bench exclusion probe, build lock when building; no foreign process termination,
no lock removal. Inspect active thread affinities, preserve receipts on failure.
Scratch fresh /mnt/clathrin/alex-motioncorr-cuda-cpu-boundary-20261026,
20GB maximum; symlink original inputs, no copies of unrelated evidence.

## Ordered experiment and stopping

1. Hash/inspect retained current-source G/L products for both cases; no new
   full24/100 campaign. Freeze exact single-movie STAR and gain/movie hashes.
2. If captures absent, narrow default-off MC_BOUNDARY_DIR diagnostic: only global
   first iteration, preprocessed and forward-FFT frames0/4 plus all24 CCF-window
   inputs, reference, weights, weighted spectra, maps and raw subpixel results.
   Capture with complete dimensions and explicit float32/complex64/f64 metadata.
   No estimator/default/gate change. Independent source review before captures.
3. Use one source/configuration/binary for CPU and native CUDA, --j8 --seed1
   --use_own --dose_weighting --dose_per_frame1.277 --bfactor150
   --expected_frames24 --gainref Movies/gain.mrc --ingest float;
   default global-only and local5x5 are distinct endpoints. Optional origin
   interpolation remains OFF; tied versus unique maxima reported separately.
   Run baseline flags-off against existing production binary; demand identical
   MRC payloads and movie-STAR fields, then capture-on versus flags-off neutrality.
4. Compare preprocessed input then initial FFT before global iteration. Compare
   reference/weights/weighted spectra/maps/peak on identical stored upstream state,
   using native CUDA windowed entry point and native FFTW replay. Bind exact backend
   selector, normalization, layout, Hermitian validity, FFTW threads and planning.
   Pure inverse
   FFT replay runs both saved spectra on both backends. Do not attribute later
   trajectory differences as first causes. Record first bit mismatch separately
   from materially amplified peak/shift difference (>1e-4px diagnostic routing,
   not a changed acceptance gate).
5. Global-only vs local endpoints report global trajectory, observations/acceptance,
   fit field and reconstruction separately. Missing fullprecision local captures
   stay UNRUN; no repeat of W4 CPU fit. Expand captures only for a remaining
   discriminating boundary. Stop/adjust after two cycles without new evidence.

Candidate only if a narrow mechanism supports ONE default-off intervention;
independent source review before candidate native campaigns. No CPU-FFT fallback,
precision rewrite, prior falsified H7 package, or relaxed tolerances. All eight K267 cases AND separate retained N5/9/13/20 and global-only
controls including harmfulvel1N20iso are required if estimator changes; truth recovery, image preservation and CPU compatibility remain separate.
Original Gate2 relativeRMSE0.001 retained. Runtime cost only paired resources,
no throughput or scientific acceptance claim. Parent owns interpretation.
