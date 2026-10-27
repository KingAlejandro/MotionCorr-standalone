# Direct physical-field representability check

Status: parent calculation complete; independent numerical review pending. This is an oracle using truth deliberately, separate from the observation-only candidate and its native pilot.

On the original dense72×104 ROI, all five frames and the native18-coefficient local family, the direct RMS optimum with the retained noisy UP-only runtime global fixed is0.0367925269662Å. Its p95 and maximum are both0.0594252919488Å. With the actual STAR global fixed and fullprecision oracle local coefficients, the corresponding values are0.0367926098473Å and0.0594254258138Å. Affine runtime/STAR-global RMS optima are4.58228e-5/4.49601e-5Å.

These particular fullprecision oracle fields satisfy all three field limits. Thus the fixed-global/native local family can represent a passing field on these exposed movies. This says nothing about recovering its coefficients from actual observations, native iteration accuracy, image application or a genuine refitted STAR coefficient roundtrip. The candidate still reads no truth.

The earlier approximately0.465Å perfect-observation nuisance-refit result was an observation-fit outcome, not the direct physical-field RMS lower bound. Treating it as an unavoidable error floor would be incorrect. No historical result was changed.

The oracle supplies an RMS lower bound only for this fixed-global family. Its p95/max are values at that RMS optimum, not separate percentile/max minima. No floor is subtracted from any reported candidate error and no accuracy threshold changes. Raw/scaled rank18 SVD, conditions, orthogonality and independent N5 temporal-null closure, exact inputs before/after, coefficients and runtime are retained in ORACLE_FLOOR_RESULT.json. The frozen pre-calculation plan is ORACLE_FLOOR_PLAN.md; the standalone script is oracle_floor.py. No movie or image intensity was read.
