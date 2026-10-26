# Local joint objective: stronger optimization alone does not repair the retained noisy case

The frozen bounded search improves its explicit alignment objective but worsens the selected all-five-frame physical trajectory error at both exposed patches. This is a NO-GO for stronger optimization alone as the recovery remedy on this retained case. A separate full-width local-frequency screen follows under its own freeze; it is not part of this experiment's original prediction.

| Native patch center | Native RMS / maximum (px) | Highest-J selected RMS / maximum (px) |
|---|---:|---:|
| (62,79), bad | 6.703455 / 14.812340 | 6.719772 / 14.847959 |
| (62,47), central | 1.189972 / 2.041873 | 1.282896 / 2.264968 |

These are physical cumulative local-trajectory errors at two points over five frames, including frame0. They are not full-ROI fitted-field scores or the scientific gate's p95/max. No rigid registration, scalar floor subtraction or Tr-reporting offset was applied. Torus errors are separately recorded.

On the bad patch, zero and eight random starts reach a lower-valued local maximum (J2.241810, RMS1.384847px), while the two native starts reach the higher-valued remote maximum selected by the frozen rule (J2.254992, RMS6.719772px). The native endpoint already has J2.254629. Both captured native steps increase this objective; an objective decrease is not claimed. The selected value exceeds both mapped center-truth J2.202007 and support-mean-truth J2.201958. This proves a preference over these two rigid truth mappings on this data, without proving generic objective inadequacy or a global optimum.

All eleven central-patch starts reach effectively the same local solution. The selected rand2 label reflects roundoff-level objective ordering, not evidence that it is a superior start. All22 runs report SciPy status0, no caps and negative Hessian maximum eigenvalues; some stop on the function-value condition with gradient above the nominal gtol, so no universal gradient-threshold pass is claimed. Total author wall time0.24s is report-only numerical-tool cost, not native performance.

## Frozen method and independent checks

Source927a6890, the immutable 612-file native-map bundle and initial captured float32 spectra/weights are unchanged. No new MotionCorr producer or image samples were read. Native integer slices are linked to the explicit raw signed-frequency half-plane pair objective. The exact core is independently reviewed by Opus5.5HIGH; Sonnet5.5HIGH implements the calculation. Nyquist contributions are negligible for this B150 geometry, which is not a generic FFTW/Hermitian assertion.

The parent explicitly reconstructs all20 native maps over all961 search-box integer lags each, maximum discrepancy2.227494e-7 against the unchanged5e-6 bound. Sign/axis/omitted-DC/doubled-x0 mutants are rejected; suppressed Nyquist/Hermitian variants are labeled unobservable. A/B/C map/phase consistency and the vacuity guard pass before optimization, with the largest discrepancies8.1e-8/3.2e-8/5.2e-8. Eleven starts per patch and all optimizer settings were frozen before captured optimization; no extra starts, restart or tuning occurred.

Stage1 sealed all results before truth was loaded. The parent independently evaluates all28 baseline/outcome trajectories and objective values; maximum objective difference8.89e-16. Primary physical point-center scoring and supplementary patch-mean/spread scoring were fixed before the run. Maximum within-patch truth variation about its support mean is0.462800px; center-to-mean mapping differences are explicitly retained. They are not subtracted as a model floor.

## Control failure retained

Original C9's1e-3 L1 sensitivity margin FAIL remains. The author's post-hoc reduction to1e-6 is NOT ACCEPTED. No all-controls-PASS or estimator-qualification claim follows. Independent unchanged C2/C5 reference/derivative checks reject every sign/axis mutant, and saved-spectrum shifter/native-grid checks provide additional convention evidence. The calculation is limited mathematical characterization; it does not turn the failed auxiliary criterion into a pass. Original attempts and the rejected repair remain archived.

## Limits and next step

No native changed estimator, applied reconstruction, STAR writer, full field, image retention, GPU, harmful control or scientific acceptance was tested. Global optimality is UNPROVEN. This result motivates investigating the objective/reference observation rather than extending iterations alone. A separately frozen one-factor local full-width-frequency screen tests that next question on the same upstream state. Both are development diagnostics; no default, gate, production source or qualification disposition changes.

## Package and reproducibility

EVIDENCE_INDEX.json binds verified complete local snapshots, including source-context copies and failed attempts kept outside Git. The root SHA256SUMS binds this compact package. Older author preparation manifests predate appended logs and run outputs; they remain original receipts, not current package manifests. Frozen source/plan/core/runner/scoring hashes, SEAL.json, explicitcommands, environment, statuses and independently scored vectors are included. Required input arrays remain in the pinned native-map bundle; no movie data are duplicated here. Code snippets use the recorded local Python/NumPy/SciPy and captured paths; this is an evidence consumer, not a new application workflow.
