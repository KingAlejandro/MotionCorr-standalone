# Bounded independent reproduction and interpretation corrections

Independent direct B64 bridge reproduction passes: all 16 fixed-point pairwise gaps (two patches × two movies × four references) match within `1.95e-16` raw objective units. The same pinned MRCs are used, and the 61,440-pixel noise difference matches the declared PCG64 noise stream within the float32 rounding bound. No native job or estimator was run.

Under the declared single-total-G B64 bridge, the bad patch's aggregate gap changes from `+0.0388807367` on noisy input to `−0.3673997851` on noiseless input. Frame0 changes `+0.0382568957→−0.0930490989`; frame1 `+0.0153373529→−0.0925459852`; frame2 `+0.0001602705→−0.0916773103`; frame3 `−0.0148737825→−0.0901273907`. All four noiseless terms favor the fixed physical scoring point over the captured remote point. At the central patch, all four positive noisy gaps become negative. The B32 result and the worker's spectral bounds/local searches are not independently audited here.

Two reporting corrections supersede the original REPORT wording:

1. “Reverses the sign ... of all four ... at both patches” is incorrect. Bad-patch reference3 was already negative and remains negative. The supported statement is that all four noiseless terms are negative; the positive noisy terms flip, and the already opposing term becomes more negative.
2. “All historical gates remain FAIL” must mean that previous failing outcomes remain failures. Other retained gates already passed and remain passed. This analysis changes no gate status.

The worker's statement of sample discrepancy as “max 4.6e-5” rounds the B32 value; the independently reproduced B64 discrepancy reaches `4.7687455e-5`. Use `≤4.8e-5` across these B64 noisy patch samples. This does not alter the objective-gap conclusion.

## Limit of the conclusion

The global phase ramp is applied once at the captured final G. The native run used per-global-iteration float32 shifts whose individual deltas were not captured. The noisy bridge agrees with the captured state closely, but that measurement does not bound another input. B32/B64 agreement is descriptive precision sensitivity, not a native noiseless error interval. The captured first-iteration CCF inputs are Hermitian; the full-frame global shifted arrays expose invalid-column cases handled by the declared NumPy completion. No generic FFTW extension is inferred.

Thus removing additive noise is sufficient to remove this fixed-point remote preference **under these auxiliary bridges**. This supports investigating noise-sensitive objective/reference behavior; it does not establish native noise causation, a global optimum, a new estimator, or scientific acceptance. The fixed physical point uses the noisy run's observed frame0 gauge and is not asserted to maximize a finite-window CCF.

Original PLAN, pre-twin clarifications, scripts, results, failed precondition attempt and report are retained unchanged in the adjacent original archive. The parent check uses a separately written FFT/ramp implementation and the earlier independent Fourier-series evaluator, NumPy2.4.2, BLAS/OpenMP caps1. No source/generator/gauge/ROI/tolerance/default or native budget was changed.
