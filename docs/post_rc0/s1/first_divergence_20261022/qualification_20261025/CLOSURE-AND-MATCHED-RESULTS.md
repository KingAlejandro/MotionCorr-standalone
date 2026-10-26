# Full-precision fit closure and same-input peak attribution

These are additive CPU-only diagnostics on the same noise-free128×96×5 affine realization and retained source805d9de2/#275 overlay. They use existing captures, with no native rerun, new CUDA capture, estimator implementation/adoption or scientific qualification.

## Captured fit inputs close

The full45-row table is retained at `cpu-observation-closure/actual/cpu-observations.json`, with each input byte bound to its original capture/index/protocol record. Nine patch selectors, five frames each, exactly the logged centres. Final shifts derive `obs[g]=after[g]+0.5*after[1]` at `z=g+0.5`; fit/apply conventions unchanged.

- Maximum component difference from STAR print values4.44444444445e-6px, inside the5e-6 print-rounding control.
- Full-precision least-squares rank18, design condition4069.25364. Fit-plus-global vs retained full-precision runtime field differs at most1.51772e-14px over the fixed ROI at integer frame time.
- Observation residual sum of squares is0.755968x /0.604868y; matching the runtime fit does not mean exact interpolation of every observation or physical accuracy.
- All7structural negative controls passed before the one actual consumer run. Field RMS/p95/max0.20/0.40/0.80Å remains unchanged, runtime/STAR evaluated separately; this closure does not re-evaluate truth or claim science PASS.

The earlier STAR-rounded reconstruction gap is now closed for CPU. There is no CPU fit-arithmetic explanation for the physical field error at this precision. This does not prove the upstream global/local estimator or inherited time convention correct. CUDA allpatchfullprecision observations remain unavailable without a separately reviewed capture protocol.

## Same native input, all patches and iterations

The matched-native pass checks all213stored capture files over13patch-iterations; all14controls PASS, including exact native state updates, stop rule, axis/sign mutants and the already-passing(2,1) oracle. Regression differences there are0 /3.33e-16 /3.60e-16 for the declared terms.

| Ordered chain term | RMS over9patches × frames1–4, px |
|---|---:|
| Native minus double native-rule replay (float32/tie effects) |0.223977|
| Double separable parabola minus continuous local refinement |0.215698|
| Native stopping minus continuous fixed point |0.064894|
| Native-window fixed point minus reconstructed-window fixed point |0.000008519|

Native-final minus pipeline reference remains0.228171px RMS. The same-sample terms across13iterations are0.318914px for native-minus-double-map parabola and0.314068px for parabola-minus-local-refinement. The prospectively frozen materiality routing gives MIXED:float32_ties+integer_parabola. These are ordered, path-dependent vector terms that can reinforce or cancel; do not sum their scalar RMS values or call them independent causes. The float32 term includes CCF/weight/shift/replay arithmetic, not proof that every error is an exact tie. Local Newton stationary points are not certified global optima.

Input reconstruction contributes only8.5e-6px in this ordered end-to-end comparison; it does not explain the0.228px residual here. The continuous objective on actual stored inputs still has0.274907px residual vs known at the patch centres, so perfect peak arithmetic alone is not a motion-truth cure. The earlier time/anchor and observation co-cause qualifications remain.

## Next discriminating item and holds

Select DC completion from the already-run campaign before adding an estimator: the material float32/CCF term makes conditioning evidence relevant. First inventory and prospectively bind only the68late TierB CPU outputs for the unchanged evaluator on cpu64, without rerunning736records or starting a new native campaign; then regrade with unchanged v2.2, preserving878and371snapshots. This preparation is not an evaluation result. New estimator/weight work must keep the five-frame failures and N5/9/13/20 plus11.833px harmful counterexample visible. C1 engineering gaps and scope remain as published; C2/M6/held-out, new noisy acceptance cohorts, production adoption and performance integration remain held.
