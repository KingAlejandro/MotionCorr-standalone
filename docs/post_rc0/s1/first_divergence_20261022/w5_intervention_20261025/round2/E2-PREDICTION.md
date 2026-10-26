# E2 prediction, frozen before any de-warp iteration

Test one outer-loop intervention: de-warp ORIGINAL frames by the current
global+local field; run the unchanged residual global alignment and nine
patch alignments; fit the same inherited half-time/zero-extrapolation 18-term
model; add the fitted residual global and local coefficients to the current
estimate. Repeat exactly 12 times. Initial state is the retained full-precision
CPU affine global+model (W5 runtime RMS .402437 Å). No E1 damping is included.
The inner weight B150, search, separable parabola, 5/.5 px stopping, patch bounds,
centres, acceptance and fit basis/convention remain unchanged. Double CCF maps
are the declared offline arithmetic domain; no native-equivalence claim.

Explicit update: q maps to q-C_k(q) in the original movie; residual fit D_k
updates C_(k+1)=C_k+D_k by adding global trajectories and polynomial
coefficients. This is an additive small-correction iteration, not exact
composition of arbitrary deformation maps. Every warp is recomputed from the
original movie, avoiding accumulated interpolation. Do not refit or alter the
truth, evaluator, ROI, gauge, mask or .20/.40/.80 Å limits.

Primary image provider: stored float32 samples, bilinear interpolation with
the pinned source's invalid-edge fallback (clamp the offending floor index,
then use that pixel if either axis is invalid); return float32 images as the
native image carrier does. This introduces no new window or ROI mask.

Separate diagnostic oracle provider: evaluate the SAME pinned continuous
synthetic image function at those sample coordinates and round to float32.
It may supply image values outside the finite detector; it uses the generator
as an ideal image-interpolation oracle, not as an adoptable estimator or a
replacement stored input. Validate it against original stored samples at the
identity warp (max <1e-5 intensity). The provider/fixture recipe is frozen now.
No generator, resampler or edge rule will be selected after seeing a result.

Prediction: residual deformation shrinks under the outer iteration, reducing
the ideal-image arm's affine error. If finite-detector interpolation/window
effects leave nonzero bias even after exact truth de-warping, the stored-image
arm may stall. Merely observing a stall cannot prove boundary bias: the E1
inner-map instability, time convention, finite fit basis and additive update
are retained co-causes. Compare the two fixed providers and the trivial truth
control before attributing a mechanism.

Frozen controls, each provider:
1. Truth-dewarped affine frames: start with exact known affine global+local
   field. Near-zero first fitted update means ROI vector RMS <=1e-3 px. The
   oracle provider is a TRIVIAL positive control by construction, not recovery.
   A stored-provider failure is retained as resampling/boundary counter-evidence;
   oracle success cannot upgrade it or qualify the stored method.
2. Wrong-sign warp throughout, starting at the retained native estimate:
   use q+C_k(q), still add measured corrections normally. Per the user's
   clarification, this is the required negative control. It must NOT meet the
   contract at any iteration, including STAR, or this experiment's positive
   recovery claims are not credited. Never replace it with an easily corrected
   wrong initial estimate.
3. Zero fixture at zero estimate: identity and zero updates must persist.
4. Cheap separate robustness/basin arm: negate the native initial field but
   use NORMAL q-C_k(q) warps thereafter. It is allowed to recover and is not
   the negative control.

Report iterations0..12, complete global+coefficient states, runtime/STAR field
RMS/p95/max in Å, sampling flags, residual update sizes, accepted patches and
warp image hashes. No production adoption. A default-off C++ prototype for
this outer loop would require an actual stored-image previously failing case
to pass both representations with controls valid, rather than an ideal-image
oracle alone. Stop after E1 and E2, without tuning or a third candidate.
