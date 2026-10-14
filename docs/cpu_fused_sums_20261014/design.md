# Fused total and even/odd reconstruction sums

This experiment is stacked on #178 at `e8f3eb8ea6165edae73613751df5a2e92ff4f955`, independently of the full-frame FFT and dose-weighting experiments. #178 lowers peak RSS by retaining one float interpolation scratch image. Its current caller adds that image to the total in parallel, then performs a serial second scan into the selected even/odd image.

Move the parity selection before accumulation. When that product is requested, one OpenMP pixel loop loads the stored float once and adds it separately to the total and chosen split. A separate total-only loop retains the prior behavior when the selected split is absent. Each output pixel remains owned by one worker in a frame, and the outer ascending frame loop is unchanged. Interpolation still writes its float scratch, uses its original frame time, and completes before accumulation. No interpolation/add fusion, reduction reassociation, thread-local frame sums or SIMD arithmetic flags are introduced.

The even image still receives selected-frame indices 0, 2, 4 and the odd image indices 1, 3, 5. This does not reinterpret parity as the original acquisition-frame index. Both split pointers may independently be null. Call-site dimensions remain identical.

The existing streaming test is expanded to 288 cases covering 1/2/7/32 frames, j1/j4, rectangular and vector-tail shapes, all four split-pointer combinations, null/polynomial/general models, exact original full-stack output and an additional frozen #178 separate-scan control. The existing float-rounding, time-offset, immutable-input-alias and one-frame-allocation witnesses remain enabled on GNU/ELF.

`cpu_fused_sums_bench` compares the actual production streaming caller with the frozen #178 caller in one process. It includes scratch allocation, interpolation and accumulation, resets sums outside timing, alternates arm order, excludes one warmup pair, and checks all three output images bitwise after every pair. Synthetic pixels are deterministic finite normal values. It is a reconstruction-stage test, not a complete movie speed claim. Representative tutorial geometry and odd-frame geometry, j1 and j4, should be recorded under the shared CPU benchmark lock. Whole-movie product and timing evidence remains separate.

Potential payoff is restricted to unweighted/noDW/even-odd work. Dose-only jobs that never run unweighted reconstruction are unchanged. Savings from #178 memory reduction and this scan fusion must not be added as independent whole-movie wall gains.
