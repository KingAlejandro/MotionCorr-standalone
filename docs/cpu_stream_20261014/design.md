# Stream CPU unweighted reconstruction

Refs #10. This experiment starts from main `116eb04ad359cd5bf789b28809fc2047ea155b9b`,
independently of draft PR #177's correlation-plan experiment.

The CPU unweighted reconstruction materializes one corrected float image per
movie frame, adds those images in ascending frame order, and keeps the corrected
stack alive through dose weighting. No later consumer needs the stack. A
3710 x 3838 x 24 movie therefore retains about 1.27 GiB of avoidable images.

Replace that stack with a non-owning view of one source frame and one owning
corrected float frame. Reuse the existing interpolation implementations, then
perform the former total and even/odd additions in the same ascending order.
The helper releases its scratch before dose weighting. Source frame ownership
and the CUDA resident reconstruction and fallback selection remain unchanged.

Two numerical boundaries are essential. Interpolation must still store its
result in float before accumulation; fusing the interpolation expression into
the sum changes rounding. A one-element view must evaluate the motion model at
the original selected-frame index. A private trailing frame offset, defaulting
to zero, preserves full-stack calls and both general and polynomial models.
Interpolation arithmetic, clamping, coefficients, parity and output publication
stay as before. The interpolation timing substage now includes accumulation;
use the surrounding unweighted-sums stage for comparisons.

`CpuUnweightedStream` compares the new production helper against the former
materialize-and-add sequence bit for bit, including null, polynomial and general
models, one/four threads, 7/32 frames, two shapes and both split settings. It
checks immutable input aliases and progress output. On GNU/ELF, allocation
wrappers witness N live corrected frames in the reference and exactly one in
the candidate, with no scratch surviving either call. Negative witnesses ensure
the data can detect loss of float rounding or resetting model time to zero.

End-to-end acceptance requires exact canonical products and metadata, existing
regressions and known-motion gates, and bounded alternating measurements of
unprofiled wall time and process peak RSS. Fewer live arrays alone do not prove
a smaller process peak or a speedup. Report host limitations and failures without
relaxing gates. No native GPU performance claim is part of this experiment.
