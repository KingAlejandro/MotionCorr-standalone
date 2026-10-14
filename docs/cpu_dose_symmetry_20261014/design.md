# Reuse symmetric dose weights, retaining independent spectra

Refs #10. This is separate from the full-frame plan/copy and first-touch work
already owned by another agent. Base is main `116eb04`.

The scalar dose model depends on `ly*ly`, not the sign of ly. For y in
1..floor(ny/2), its negative-frequency partner ny-y has identical Ne, weights
and ascending-frame normalization. Calculate these scalars once per pair,
but apply the original complex multiply and divide separately to both rows.
Do not copy one row's pixels to its partner: the spectra are not interchangeable.
DC and the even-height Nyquist row must be processed only once. Odd heights
have no Nyquist singleton. Disjoint row pairs remain safe for OpenMP workers.

No FFT, plan, frame-buffer allocation, input-preservation, interpolation or output code changes.
No recurrence, approximate exponential, fast-math, combined multiply/divide or
reordered reduction. In particular, retain the existing complex operators and
their float-store boundaries, even where a scalar simplification seems natural.
There is no frame-sized extra storage or cross-movie cache.

A 64-frequency tile stores original RFLOAT weights and normalizers per worker
(12.5 KiB for 24 frames; 32.5 KiB for 64 frames). Scalar evaluation retains the
original frequency formula and ascending-frame reduction. Then frame-major
multiply and divide passes visit contiguous pixels in one partner row at a time.
Separate passes preserve the intermediate complex float stores. This avoids
processing two full movie rows in the same inner frame loop. The first row-only
prototype and its subnormal-stress measurements are preserved separately;
normal-data timings are a distinct population.

An archived main implementation supplies a bitwise complex-spectrum control.
Test odd/even/tiny heights, tile boundaries/tails, DC/Nyquist, asymmetric pixels, zero/nonuniform doses,
pre-exposure/scaled doses, subnormal/signed-zero and nonfinite spectrum values,
and one/four threads. GNU/ELF wrappers must witness ny*nfx*N exponential calls
in the original and (floor(ny/2)+1)*nfx*N in production. The benchmark is a
separate unwrapped target; no exp-count instrumentation enters its timings.

Run bounded alternating mechanism measurements and end-to-end product checks.
Use whole-job elapsed time and peak RSS for product claims. Even perfect halving
of a 3.3-second weight stage saves at most 1.65 seconds in a 47.7-second job;
complex pixel traffic is unchanged, so the real gain must be smaller.
