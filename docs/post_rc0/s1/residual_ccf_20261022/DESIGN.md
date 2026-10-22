# Frozen residual CCF capture, 2026-10-22

This package is observation/replay only, under GPL-2.0-or-later. Production files
remain unchanged in git. `diagnostic.patch` is applied only to a fresh archived
PR273 source tree (`805d9de27898b4a10e6212e65098d5995a40fdb1`; numerical source
`d751ff28594902eca75d665ff116e662653481aa`). No DC, double-pipeline, convergence,
fit, default, tolerance, dependency or publication change is included.

Before launch, freeze exactly four original hash-matched inputs: integer,
fractional, affine and noisy, from the original NumPy 2.5.3 fixture set whose
MANIFEST SHA256 is 9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc.
Copy, do not regenerate or overwrite old evidence. CPU/CUDA x capture disabled/
enabled = **16 maximum application processes**, run sequentially. Same binary
within each pair. Existing argv, seed, five iterations, 1x1 or 3x3 patch geometry,
fixed ROI, checker and all gates are unchanged. MRC labels are also compared with only the Relion timestamp normalized. Stop on any neutrality failure.
No extra application launch, seed scan or conditioned arm is authorized here.

Capture global calls for all four cases, and local patch (2,1) for affine or
(1,3) for noisy on both backends. Labels are source-verified 1-based (y,x),
flattened as iy*patch_x+ix; batched chunk offset is taken at its real call site.
Every captured alignment invocation has a distinct call identity (including
retries), geometry, actual crop dimensions, search range, B, float/double scale,
weights, iteration/frame identity, current cropped frame spectra, actual
reference spectrum, actual C2R input, float maps, raw candidates and accumulated
shifts before/after frame-zero subtraction. C2R input is saved before the inverse
can destroy it; CUDA capture occurs after the existing Hermitian projection.
CPU boundary projection is implicit in the real inverse and reproduced offline.
All reads use copies; no observed data are written back. Both arms additionally
write full-precision global trajectory and pre-serialization model for strict
neutrality checks. Raw logs retain patch bounds, acceptance and convergence.

Independent NumPy double full-complex inverse reconstructs negative frequencies
with the real-inverse Hermitian convention, uses unnormalized inverse FFT
(the native inverse convention), and preserves CPU row-major/CUDA 256-lane
strict-maximum tie order, signed search window, periodic neighbours, promoted
quadratic fit, native scale and CUDA candidate narrowing. Analytic sign/axis/
zero/known-shift and normalization controls must pass before capture analysis.
Conditional replay of saved C2R input isolates inverse/map/fit loss; double
reaccumulation/product from captured float frame spectra adds reference/product
rounding. Neither recovers earlier forward-FFT, preprocessing or iterative-state
loss, and neither is a full forward-double physical reference or estimator floor.
No known-template oracle is used. Truth-relative trajectories and local point
residuals are descriptive, with affine patch correlation not equated to a point
measurement. Failed checker gates remain failures; process exit 0 is not truth.

Remote resource envelope: hostname 4-gpu-vm; NEW /mnt/clathrin scratch; CPUs10-13
including children; compile parallel2, runtime/numeric1; GPU3 only, UUID
GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d. Build lock and canonical GPU correctness
lock are exclusive/nonblocking. A busy lock is retained UNRUN with owner snapshot,
without wait/retry. Probe/release benchmark lock before GPU admission. Fresh UUID,
idle, app, ECC/full-health samples before execution and after each CUDA arm,
with correctness lock held through posthealth. Hardware failures are fatal.
Final healthy-empty utilization may settle for at most three 1-second samples;
no settling is permitted with an app, changed UUID or hardware error. Detached
PID and exit receipts precede reconciliation; no blind retry or foreign kill.
No timing claims during parallel lanes. Raw arrays/products remain remote and
hash-indexed; compact source, scripts and receipts alone are committed.
