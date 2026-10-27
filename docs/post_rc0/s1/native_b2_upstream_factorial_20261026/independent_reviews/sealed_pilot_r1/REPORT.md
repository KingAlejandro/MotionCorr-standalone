# Independent sealed B2 pilot result review

**CLEAR for bounded result reporting; no material inconsistencies found. Scientific promotion remains blocked.**

Reviewed sealed head **`e28ffb10c9189a5a5054bf7e6e51027f560766a6`**, using sealed files throughout.

- **Independently recomputed:** all four frozen movies’ OFF/ON runtime and actual STAR fields using unchanged scorers, analytic truth, fixed 129×129 ROI and `.20/.40/.80 Å` limits. Saved metrics agree within `1.6e-15 Å`. Both consumers retain dose1 **FAIL→PASS**, dose05 **FAIL→FAIL**, dose4 **PASS→PASS**, pedestal32 **FAIL→FAIL**. Dose4’s runtime maximum regression `0.289033143→0.513834609 Å` remains explicit. See [README lines 17–35](https://github.com/KingAlejandro/MotionCorr-standalone/blob/e28ffb10c9189a5a5054bf7e6e51027f560766a6/docs/post_rc0/s1/native_b2_20261026/README.md#L17).

- **Compatibility independently reproduced:** maximum native/W8 difference `4.602322493821259e-6 px`, below frozen `0.01313142874082845 px`. W8/native globals agree exactly. Actual STAR roundtrip losses reproduce separately; this comparison bound is correctly distinguished from truth gates.

- **Noisy harm independently reproduced against saved truth:** runtime RMS `2.342955203→3.587249812 Å`, maximum `9.903898811→19.563704822 Å`; STAR also fails. Verified identical observations/global trajectory, both local-enabled, nine converged patches and nonconverged global alignment. Both checker receipts retain `OUTSIDE_FIXED_ROI` and `application_consistency_status="NOT_TESTED"`. The changed nuisance-adjusted RMS estimand is disclosed, without claiming unchanged flagged acceptance. See [README lines 50–54](https://github.com/KingAlejandro/MotionCorr-standalone/blob/e28ffb10c9189a5a5054bf7e6e51027f560766a6/docs/post_rc0/s1/native_b2_20261026/README.md#L50).

- **Provenance/coverage audited:** manifest totals reproduce **1,466 files / 1,069,023,998 bytes**, covering **14 pilot + 56 tiny producers**. Verified 64 targeted raw files against index hashes and receipt/model/STAR links. Saved index hashes support eight K267 baseline/OFF and sixteen N OFF/ON runtime/case-STAR identities. Original failures remain retained; tiny-input pinning is explicitly retrospective.

- **Claims remain bounded:** seven image reports retain transfer-up/FRC-down/border-RMS-up; timing ratios independently recalculate to `0.994699055`, with AA nulls `1.008233467/0.989755732`. Neither supports general image improvement or speedup. Gemini’s exact report hash matches; the endpoint identity is valid before spatial projection, and raw-observation L2 sensitivity is not presented as physical noise variance.

Native build/CTest and image measurements remain **producer-reported evidence**. I performed no native reruns, fits, image-pixel reads, full archive rehash, or production-source re-review. Full100, full CPU qualification and native GPU/CUDA execution remain **UNRUN**.



Recorded orchestration provenance: `codex / gpt-6.1-sol`, options `[{"id":"reasoningEffort","value":"high"},{"id":"serviceTier","value":"default"}]`. Task `node:delegated-task:command%3Amcp%3A85cda455-999f-4db1-83eb-ec91d0fea950%3Adelegate-task%3Anative-b2-sealed-result-review-20261026-r1`.

