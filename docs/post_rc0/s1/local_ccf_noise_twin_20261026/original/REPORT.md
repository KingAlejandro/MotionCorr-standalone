# Noise-twin bridge, K267 iteration 1 frame 4 (auxiliary counterfactual; Sonnet 5.5, effort high)

**Conclusion (under this auxiliary single-total-G NumPy bridge, not native):** with the captured global trajectory G, global-shift/crop operator, patch geometry, weight and evaluation points held fixed, removing the additive pixel noise reverses the sign of the aggregate and all four pairwise conditional gaps `D_j = I_j(x_nat) - I_j(x_phys)` at both patches. The remote-basin preference does not persist: in the noiseless twin the physical point scores higher than the captured remote point for every reference. This does not establish native noise causation or a native-twin sign.

## What was measured
- **Twin check.** Manifest recipes differ only in `noise` (4.0 vs 0.0) and the labels `name`/`role` (the pinned generator never reads them). Field and target hashes are equal. Regenerating `PCG64(238262).normal(0,4,(5,96,128))` reproduces `noisy - affine` within float32 rounding at all 61,440 elements (max residual 7.60e-6, bound 7.63e-6; std 3.9873). The manifest was written under NumPy 2.5.3; this run used 2.4.2 and the stream still matched.
- **Inputs.** Both pinned MRCs (noisy 5000fbfc…, affine 1cf918d5…) already existed locally with exact hashes. No SSH was used.
- **Control (noisy bridge vs captured native state), both arms, both patches.** Bridge extents, G (bitwise) and `window-fft == initial-fft` match capture. Patch samples differ by max 4.6e-5 (relative 4.1e-7; none byte-identical), patch FFT by 7.7e-6 to 1.5e-5, consumed cross-spectrum by max 7e-7 to 1.0e-6. Replay of the earlier pairwise gaps from captured F agrees to 3e-9.
- **Native c2r vs NumPy `irfft2` of the captured consumed spectrum:** map max abs 1.4e-7 to 2.2e-7 (all five frames, both patches). The captured iteration-1 CCF spectra are exactly Hermitian, so that c2r is not an invalid-input case. The only invalid-input exposure is the global c2r: the Fourier-shifted global spectra have x-Nyquist-column conjugacy residual 0.11 to 0.16. The bridge's `irfft2` completion reproduces the captured patch samples to 4.6e-5 there. That is an indirect measurement; generic FFTW equivalence is not asserted.
- **Propagation bound, noisy control only** (full-grid Hermitian spectral L1, weighted by `|β(x_nat) - β(x_phys)|`; measured error always inside it): bad patch aggregate `B_state` 5.1e-6 (B32) and 4.9e-6 (B64) plus engine 1.2e-6, total 6.2e-6 / 6.1e-6, against the captured gap 0.0388765; measured bridge-minus-captured gap error 3.8e-6 / 4.2e-6. Pairwise bounds are 1.2e-6 to 2.3e-6 against gaps of 1.6e-4 to 3.8e-2. Central patch: total 1.8e-6 against 0.0200595. Cross-product identity bound held on every bin. These bounds cover that control only.

## Conditional gaps `I_j(x_nat) - I_j(x_phys)` (B64 shown; B32 agrees to ≤3e-7)
| patch | arm | j=0 | j=1 | j=2 | j=3 | aggregate |
|---|---|---|---|---|---|---|
| (62,79) | captured native | +0.038256 | +0.015336 | +0.000159 | −0.014874 | +0.038877 |
| (62,79) | noisy bridge | +0.038257 | +0.015337 | +0.000160 | −0.014874 | +0.038881 |
| (62,79) | noiseless twin | −0.093049 | −0.092546 | −0.091677 | −0.090127 | −0.367400 |
| (62,47) | captured native | +0.002425 | +0.003849 | +0.013128 | +0.000657 | +0.020059 |
| (62,47) | noisy bridge | +0.002425 | +0.003850 | +0.013128 | +0.000657 | +0.020060 |
| (62,47) | noiseless twin | −0.003248 | −0.004402 | −0.004863 | −0.003855 | −0.016369 |

Closure `sum D_j` equals the aggregate within 4e-11 (twin, B32) and 3e-16 (B64). Nearby choices at (62,79) in the twin: integer-point gap −0.0937 to −0.0908, the per-reference stationary candidates refined from the `x_nat` seed (descriptive) are not concave maxima, and the aggregate native-rule integer maximum moves from (10,−8) (value 0.6854) to (0,1) (value 0.8765), with the twin value at the remote point 0.485 versus 0.853 at `x_phys`. Pairwise twin integer maxima are (0,1),(0,1),(0,1),(0,0). Central (62,47): twin aggregate integer maximum (−1,1); its stationary candidate refined from `x_nat` lands at (−0.52, 0.88) with a positive gap (+0.0048), so at the central patch the sign reversal applies to the fixed-point gaps, not to that arm-local candidate. All integer maxima are unique (tie count 1).

## Precision sensitivity (descriptive only)
B32 vs B64 twin gaps differ by 3e-7 or less (aggregate bad patch −0.36739952 vs −0.36739979). This is not an interval on the native twin.

## Limits, stated exactly
- No native run on the noiseless movie exists. The bridge applies one total `-G/pn` phase ramp; the native global alignment applied per-iteration float32 steps whose deltas were not retained. The control shows the bridge matches the noisy native state to ~4e-7 relative in samples; that does not bound a different input.
- The twin result is therefore a conditional result of the two declared bridges. A native conclusion would need a native noiseless run with the same G (not run here, out of scope).
- Evaluation points are fixed from the noisy capture, including the noisy-observed frame-0 offset in `x_phys`; the twin's own frame-0 offset was not used. Pairwise maps are regenerated NumPy auxiliary maps. No global optimality certificate (`UNPROVEN_GLOBAL`). All historical gates remain FAIL; no source, default, threshold or adoption change.

## Chronology and failed attempts (preserved in ATTEMPTS.md, COMMANDS.log)
PLAN frozen 17:28Z (sha c3e25f67…). Phase A (bridge_v1) ran next. The parent then required corrections C4/C5 (no FFTW Nyquist assertion, no twin bound from the control); they are in `PLAN_CLARIFICATIONS_C4_C5.md`, written before Phase B, with `PLAN.md` unchanged. `bridge_v1 --phase twin` stopped on my own check (it omitted the `name` label; no twin values computed; stop record kept). `bridge_v2` repaired only that check and ran Phase B once. No arm switching, no retuning.

## Measured vs UNRUN
Measured: everything above. UNRUN: native noiseless run, per-global-iteration shift replay, noise-seed grid, full-grid/global search, any gate or science qualification.

## Provenance
Model Sonnet 5.5 (`claude-sonnet-5-5`), effort high; no subagents. Python `/Users/alex.konstantinov/.local/bin/python3 -B`, NumPy 2.4.2, single-threaded. Source commit 927a6890…; bundle INDEX 5b3dde3a…; truth field 839c484f…. Files and hashes in SHA256SUMS.
