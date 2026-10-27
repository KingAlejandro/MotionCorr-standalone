# Full-width local x-frequency screen: narrow prediction not refuted

This separately frozen follow-up changes only the local x-frequency denominator22→42 within the same saved-state joint-objective diagnostic. It improves all three point-trajectory metrics at both exposed patches and meets the predeclared directional prediction. This is NOT_REFUTED_ON_TWO_EXPOSED_PATCHES, not a scientifically accepted estimator.

| Patch | Inherited-weight selected RMS / p95 / max (px) | Full-width-weight selected RMS / p95 / max (px) |
|---|---:|---:|
| (62,79), bad | 6.719772 / 12.210140 / 14.847959 | 1.267093 / 1.740545 / 1.773182 |
| (62,47), central | 1.282896 / 2.110999 / 2.264968 | 0.997396 / 1.597027 / 1.726251 |

The predeclared bad-patch RMS reduction of at least0.5px is met (reduction5.452679px); neither patch has an RMS/p95/max increase above the fixed1e-8px numerical resolution. This is a directional point diagnostic, not a replacement accuracy gate. Absolute errors remain substantial. The original full-ROI .20/.40/.80Å contract, actual STAR, native trajectories and harm controls are UNRUN for this changed weight.

## Isolated factor and provenance

The frozen PLAN.md explicitly follows exposure to the earlier joint-objective result. W=float32(exp(-2*150*((kx/42)^2+(signedky/32)^2))) replaces inherited xnorm22; y norm32, B150, DCzero, initial spectra, global G, patch window, core, eleven starts, optimizer settings and300s cap remain unchanged. The original22 baseline outcomes are reused; only22 new optimizer outcomes are produced, all status0/no cap. No native producer, image samples, global-weight change or new control run occurred.

The inherited formula reproduces all704 saved weights bitwise on both patches. The new literal formula and native operation order at xnorm42 also agree bitwise.624 bins change. Active bins with W>.01 excluding the zeroed DC increase18→35 (the worker's raw array counts19→36 include DC). Nyquist maxima remain about2.7e-33. The core's general-weight mathematics has independent review; original C9 FAIL and the rejected post-hoc tolerance relaxation remain retained.

On the bad patch, the two native starts still end in a remote local maximum, while zero and all eight frozen random starts find the higher-valued near basin selected in this arm. This is a basin-order change within the altered objective, not a comparison of raw J across differently weighted arms. All central starts reach one solution; the selected rand4 label is roundoff ordering among practically equal endpoints.

The parent verifies the stage1 seal and independently recomputes all28 new baseline/outcome J values and physical trajectory errors using a separately coded weight formula. Maximum J difference1.78e-15. Truth enters only afterward; it never selects starts or settings. Mapped center-truth J remains below selected J in each arm; patch-support-mean values and variation are reported separately. Point-center recovery and a rigid-patch objective do not establish full motion-field accuracy.

## Disposition

The result warrants a future bounded native local-only frequency experiment, with the inherited global estimator and the harmful global-isotropic control preserved. It does not authorize production adoption, a CUDA port, full100 or relaxed tolerances. Native iteration can behave differently from joint optimization, so reaching this basin in the actual application remains untested. Existing affine/high-signal, N5/9/13/20 and harmful controls plus runtime/actualSTAR field scoring are still required. Trusted venue access is unresolved; no native launch was attempted.

## Package and reproducibility

EVIDENCE_INDEX.json binds verified complete local snapshots, including source-context copies and failed attempts kept outside Git. The root SHA256SUMS binds this compact package. Older author preparation manifests predate appended logs and run outputs; they remain original receipts, not current package manifests. Frozen source/plan/core/runner/scoring hashes, SEAL.json, explicitcommands, environment, statuses and independently scored vectors are included. Required input arrays remain in the pinned native-map bundle; no movie data are duplicated here. Code snippets use the recorded local Python/NumPy/SciPy and captured paths; this is an evidence consumer, not a new application workflow.
