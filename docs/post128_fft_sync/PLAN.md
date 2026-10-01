# Ablation B: global FFT synchronization only

Fresh baseline: c499b1d3 (merged128). Separate from workspace-only draft PR130. No workspace, ingest, output, scheduler or arithmetic changes.

## Toolchain contract

Installed CUDA12.8. NVIDIA cuFFT [streamed transforms](https://docs.nvidia.com/cuda/archive/12.8.0/cufft/index.html#streamed-cufft-transforms) orders work relative to its user stream (defaultstream0 for the current unattached plans). Each *concurrent* execution needs an exclusive work area. Current single-host-thread operations are sequential in the same stream. NVIDIA Runtime [API synchronization behavior](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-runtime-api/api-sync-behavior.html) documents default-stream synchronous-API D2D copy without host synchronization.

Inference for current source: forward executions may queue on the same plan/workspace; inverse copy-to-preservation-tile, C2R, nextcopy must remain in that same ordered stream. Keep a checked boundary before forward scaling and inverse consumers. This does not authorize overlapping plans/streams or changing batched transforms.

## Failure requirement

Removing waits permits prior frames to remain pending when a later cuFFT execution or inverse D2D copy fails immediately. Record original API failure, retrieve/record pending CUDA status and drain prior operations before returning to any fallback. Do not clear or mask fatal state. No consumer/scaling or redispatch after fatal failure. Use existing session CudaFailureState.

Native controls must call actual production methods, demonstrate exact multi-frame Fourier/real arrays and preserved inverse input, count/order synchronization, and inject failures at final boundaries and later queued operations. A missing-boundary/drain negative control must fail. Existing healthy tests alone cannot prove this.

## Measurement

New dedicated SCARF allocation, quota-safe scratch, one physical UUID and verified payload logical CPUs0–7/j6/io6, same compiler/CUDA/nvCOMP/options/input/output per arm. Recheck occupancy and record identity/environment. Three alternating screens; five confirmation pairs only if a useful benefit exceeds observed spread. Exact complete non-PDF products and required option matrix. One-movie measurements separate. If retained, measure workspace+FFT combination independently; do not infer additivity from PR130. No timing during build/profile/competing work.

Keep failures, inconclusive and UNRUN rows. No gate changes, no merge authorization. PDF content and scientific truth acceptance are separate from same-backend product checks.
