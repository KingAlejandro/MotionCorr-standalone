# Ablation C: two alignment telemetry waits

Parent: workspace-only PR130 `1420c8c`; production snapshot8bf7c1f. Compare **workspace A versus A+C**, not baseline+global FFT. No global FFT, ingest/output/scheduler/kernel arithmetic changes.

Remove only reference/CCF-stop and peak-stop timing waits. Preserve cuFFT-stop, both blocking D2H copies and D2H-stop, phase-shift-stop and total-stop. Read k1 after cuFFT-stop and k2 after D2H-stop, before the reusable kernel-event pair is re-recorded. Keep float timing accumulation order, all events, kernel launches/status checks, shifts and host convergence.

[NVIDIA CUDA12.8 events](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-runtime-api/group__CUDART__EVENT.html) specifies that re-recording overwrites event state and incomplete elapsed-time reads can returnNotReady. Later checked same-stream boundaries complete the earlier event generation; do not read timing after its events are reused.

Failure path: once a valid device is selected and this call might have submitted kernels/copies, checked drain before owner cleanup must retain late fatal status and the original failure. Pending tracking starts before submission/check, including both H2D copies; no CUDA call added to device-enumeration/invalid-device/poisoned-refusal paths. Existing failure state and owners remain authoritative.

Native controls: event generations/read order and preserved convergence/input mutation; one/multi-frame, nonconvergence and warm cache; kept-boundary faults refuse later work/success; immediate cuFFT/D2H failure after submissions drains before cleanup, retains cleared-slot fatal and forbids reuse. Missing-drain/premature-timing mutants require target-specific failures. Fault returns do not physically poison hardware.

Only after those pass: ten option/output comparisons, three alternating complete24-movie screens, exact full normalized/extended headers/pixels, STAR/trajectory/complete non-PDF inventory and physical/backend witnesses. Confirm only a promising application effect. One-movie gain remains separate, no stage-savings extrapolation or numerical gate relaxation. Same dedicated SCARF allocation, UUID/CPU masks/options/binaries/inputs pinned; no concurrent timing/build/profile.

1277 prior instrumented iterations imply a **calculated**2554 fewer event waits; this is not measured wall savings. Retain even a negative experiment; no merge authorization.
