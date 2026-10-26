# Additive provenance clarification before native capture

Original START/RUN receipts are immutable. The early harness unconditionally
recorded `hook_source`, including baseline runs. That field alone does not
identify the baseline binary's source. Interpret binary source by the following
explicit mapping and actual binary SHA256, not the early field name:

- `baseline` (8 arms): unchanged e77a51a220cb0d91f4ac3c7fac211876d0c6833f
  production source, plain CUDA binary 34e768128b83f7c94eb4a41ee6bb9a795c52c531a5d646ce4116df83d8d3535a;
  built by C1, reused read-only. No capture-hook source compiled into it.
- `off` (8 arms): diagnostic source 0e055c154ac12af73ae87a98132a8400f1b11dbe,
  MC_BOUNDARY_DIR absent; retained motioncorr-0e055c15 binary. Source-reviewed
  capture gaps were found before any capture, then corrected; these flags-off
  results are not evidence for the amended capture hook.
- `off-v2` (8 arms): diagnostic source 7a1bde5db99c94bc4332bae3f3aff6e0bfccaabd,
  MC_BOUNDARY_DIR absent, binary 930ed6b6e600b002d7ff38725e627caca134f409718421014398307c331776a3.
  Flags-off8/8 MRC payload and movie-STAR text exact to production baseline.

Those 24 producers had phase-level GPU/lock/CPU-affinity snapshots; they did NOT
have the amended per-producer CPU-load/compatible-lock/input-rehash/scratch-cap
assessment. Do not claim that later admission retroactively covers them. No
producer is repeated to repair this resource-coverage limitation; no timing
claim is requested or made. The manifest binds all eight exact baseline argv.

Before the first capture the amended harness adds per-producer admission:
frozen movie/gain/STAR/binary hashes, current target-GPU occupancy and lock
compatibility (including overlapping holder CPU masks), half-second CPU80-87
load, foreign compute masks, actual parent/child/thread affinity, scratch use
plus 1GiB incremental headroom under20GiB. Refusal is retained and stops the
phase; no signals, lock removal or blind retry. Updated START separates
production source, optional hook source, source-manifest binding and harness
SHA256. Source-manifest268files verified before capture. Scratch inputs are
symlinks, not duplicated movies. Raw receipts preserve all original failures.

Known preparation failures: first archive included nonexistent cmake/; first
build configuration consequently incomplete; first replay compile used a GCC
linker option directly with nvcc; first analysis used system Python without
NumPy. Each is retained separately. None was a MotionCorr producer/capture.
Corrected staging/build/interpreter records are additive. No numerical gate,
C1 acceptance record, default, estimator or publication policy changed.
