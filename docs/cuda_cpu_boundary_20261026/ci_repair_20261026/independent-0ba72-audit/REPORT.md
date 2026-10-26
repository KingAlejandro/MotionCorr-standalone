# Independent sealed PR288 result audit

CLEAR for bounded numerical/evidence reporting at `0ba72a7197933f5f0c7149491853c04b0d780013`. No numerical discrepancy found. This is not merge, native correctness, scientific acceptance, or M1 clearance.

Reviewer operated read-only against the supplied worktree; its live HEAD was 58cd3a563ac0b0af6999369b60a3377d656abad4 at entry. All committed inputs were extracted with git show from the sealed revision, never live HEAD. Only this scratch directory was written. PR288 was linked; no PR comment, watcher, producer, fitting, or source-review campaign was started.

## Independently performed

72 explicitly selected files, 211,850,824 bytes (202.04 MiB), fetched once via normal configured `ssh -o BatchMode=yes 4GPUs tar -c -f - -C <rawroot> -T -`. Every size and SHA-256 matched the sealed 882-row index. No full-index remote rehash. The local original receipt archive independently matched 1,754,657 bytes, SHA-256 e28fffa6f02366eb8899f47cdb8aa1b4539f3bccf22a64909c5eb07a9687c9ab and 473 members.

Exact expected directory-set equality established 12 RUN and 12 ADMISSION files. All 12 receipts attest exit 0, unchanged inputs, nonempty child-affinity samples each exactly CPUs 80–87, fresh admission true, no recorded overlap/compute conflict, and admission within 5 seconds before start. All fetched output hashes agree with corresponding RUN output_hashes and index hashes. CPU/CUDA input-directory and output-directory argv links were checked. These are receipt attestations of the prior execution; device execution was not rerun.

For all eight valid inputs, CPU RUN input_hashes/spectrum-F.c64 equal the canonical projected-spectrum SHA and valid CUDA RUN input hash and downloaded postprojection SHA. The common-projected directory bytes were not separately fetched; canonical identity uses downloaded projected bytes and both actual RUN attestations. All eight projected packed R2C spectra are exactly conjugate on both self-conjugate columns, all four corners have zero imaginary component, and all arrays are finite. Four PASS newline byte-no-op markers and duplicate CUDA projected-spectrum hashes agree; complete-batch memcmp itself is receipt/helper attestation, not independently rerun. Raw saved spectra are exactly non-Hermitian on these columns as reported.

Recorded geometry agrees across CPU/CUDA captures: real maps 972×972 float32; packed spectra 972×487 complex64; nx=3710, ny=3838, 24 observations, search range 12. Geometry was read, not assumed. Wrapped signed search, double parabolic offsets, and nx/ccf_nx, ny/ccf_ny physical scaling were recomputed independently. All eight CPU/CUDA map pairs have matching unique integer peaks.

All 39 v2 controls were reconstructed from these arrays/records; 39/39 match. 710 scalar comparisons reproduce the covered sealed values with maximum absolute discrepancy 0.0. The 1e-12 reproduction threshold is an audit criterion only, not a scientific gate.

## All eight same-valid-input comparisons

Each pair contains 944,784 float32 map elements; different_bits counts unequal uint32 element patterns. Maximum absolute map difference is 1.1444091796875e-05 for every row. Generic map estimates below use the same double formula on each map; they are not actual native recorded peaks.

| case | stored source | frame | unequal bit patterns | map RMSE | integer peak | CPU map X,Y px | CUDA map X,Y px |
|---|---|---:|---:|---:|---|---|---|
| 00021 | cpu | 0 | 602001 | 2.3177212075426667e-06 | [-2, 2] | -6.52886073207711, 6.30081501369192 | -6.53816110349032, 6.30342357082652 |
| 00021 | cpu | 4 | 597902 | 2.1927865125115043e-06 | [-1, 1] | -3.15194216338007, 3.3633853151397 | -3.15181132310762, 3.36358786770309 |
| 00021 | cuda | 0 | 601994 | 2.3174919271016167e-06 | [-2, 2] | -6.52886073207711, 6.30081501369192 | -6.53816110349032, 6.30342357082652 |
| 00021 | cuda | 4 | 597878 | 2.19270222157709e-06 | [-1, 1] | -3.15194216338007, 3.3633853151397 | -3.15181132310762, 3.36358786770309 |
| 00046 | cpu | 0 | 592620 | 2.1855661325197486e-06 | [-1, 1] | -3.43982575956571, 3.25461245271829 | -3.44562647754137, 3.25695505768182 |
| 00046 | cpu | 4 | 637154 | 2.4499821290756588e-06 | [-1, 1] | -2.56326285928725, 2.61367728208006 | -2.56124490352362, 2.61367728208006 |
| 00046 | cuda | 0 | 592723 | 2.1884386683421142e-06 | [-1, 1] | -3.43982575956571, 3.25461245271829 | -3.44562647754137, 3.25695505768182 |
| 00046 | cuda | 4 | 637123 | 2.4499114023584187e-06 | [-1, 1] | -2.56326285928725, 2.61367728208006 | -2.56124490352362, 2.61367728208006 |

Every covered value matches `evidence/inverse-v2-analysis.json` JSON pointers `/cases/<case>/<stored>/maps/<frame>/same_valid_input_inverse`, `/projected_validity/<frame>`, `/raw_actual_input_is_Hermitian/<frame>`, `/projected_valid_peaks/<backend>/<frame>`, and `/controls`. Duplicate CUDA maps match bitwise. All four captured native CUDA maps match v2 compatibility maps bitwise; actual CUDA saved IFFT-input hashes equal canonical projected input hashes. Raw CPU compatibility maps and old v1 maps were not fetched; their comparisons remain producer-reported.

## All 24 actual native observations per case

CPU f64 and CUDA f32 X/Y arrays were read with their recorded types, checked finite and exactly 24 elements each. Vector RMS is sqrt(mean(dx²+dy²)), not component RMS. All 24 raw and both anchored difference vectors, both native arrays, RMS/max vector/max component, and frame-0 vectors reproduce the original JSON exactly.

| case | raw vector RMS px | mathematical float64 frame-0 anchor RMS px | CUDA float32 subtraction vs CPU double anchor RMS px |
|---|---:|---:|---:|
| 00021 | 0.0033760633343459133 | 0.0091500346638656565 | 0.0091500025929838174 |
| 00046 | 0.0034436611882837169 | 0.0071761308168293066 | 0.0071760904591996223 |

Frame-0 CUDA-minus-CPU vectors: 00021 [-0.009300068856732402, 0.002608867838836737]; 00046 [-0.005800737702964742, 0.0023426940712596434]. Anchoring increases the all-24 difference in both cases; it does not simply cancel. No origin or causal attribution follows. The corrected 00046 anchored value is 0.007176130816829307; the superseded 0.006200 progress number is not used.

Covered original JSON pointers: `evidence/replay-v1-analysis-original.json#/cases/<case>/native_observations/{cpu_raw_px,cuda_raw_px,raw_cuda_minus_cpu_px,raw_delta_vector_px,anchor_adjusted_delta_px,anchor_adjusted_delta_vector_px,native_float_anchor_adjusted_delta_px,native_float_anchor_delta_vector_px,common_frame0_delta_px}`.

## Receipt/index-only and historical coverage

The initial-forward first sampled bit boundary is producer-reported, with sealed-index confirmation of equal sampled preprocessed hashes and different forward-spectrum hashes for both frames/cases. Native capture and forward/window replay were not rerun, and those large arrays were not downloaded. Capture/helper independent source reviews supplied by the parent are trusted rather than repeated. Image-payload source neutrality remains producer-reported; 28 movie RUN bytes were independently checked against producer-ledger receipt hashes and exit-0 records. Whole MRC hashes cannot establish payload neutrality.

Saved endpoint comparator RUN and four committed JSON grades were audited: relaxed gate, required complete coverage, all FAIL only relative image RMSE 0.001, trajectory/STAR predicates pass. Reported RRMSE: 00021-G=0.00589254030911683, 00021-L=0.00571264666095596, 00046-G=0.0119137921445305, 00046-L=0.0107374983664152. These are saved-grade audits, not independent pixel measurements. Original tar lacks endpoint-grades; committed files were read from sealed git. Supplemental archive 11eb7854... was not fetched or verified, and its binding is not conflated with the original tar.

Original 28 replay records remain separate from v2 12 processes. The original four CUDA inverse attempts and four projected-CPU derivatives retain INVALID complete-batch provenance due to the 22 uninitialized slots. The repaired source is 031f333a2863218c74951117989c84423ad9c92e; no old result is promoted because a selected map matches.

Known grader robustness limitation, not a missing-file defect in this packet: sealed `grade_inverse_v2.py:28-30` enforces 12 RUNs but uses all(glob) for ADMISSION and would accept missing ADMISSION files. This independent audit checks exact expected sets and actual coverage is 12/12. No repository fix was made.

## Failures retained and reproducibility

Core `audit.py` first run passed. Ancillary `metadata_audit.py` failed an overstrict assertion equating whole-MRC hashes across baseline/off/off-v2. Original script and traceback remain in `metadata-audit.stderr`. This is a reviewer analysis error, not a source-neutrality failure: whole-file hashes include headers. Additive `metadata_audit_v2.py` records whole-file hashes without inferring payload equality; it passed using already fetched/local metadata, without retrying any producer or remote fetch.

Commands (all run from this scratch; NumPy/BLAS limited to one thread):

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 fetch.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 audit.py > audit-v1.stdout 2> audit-v1.stderr
python3 metadata_audit.py > metadata-audit.stdout 2> metadata-audit.stderr  # retained rc=1
python3 metadata_audit_v2.py > metadata-audit-v2.stdout 2> metadata-audit-v2.stderr
```

`audit.py` is the reproducible analysis entrypoint and can be rerun solely against the retained fetch and receipts. `fetch.py` uses exclusive-create logs/archive and intentionally refuses to overwrite a previous fetch. `fetch-command.json`, `fetch-list.txt`, `fetch-stderr.txt`, `fetch-hashes.json`, `archive-verification.json`, and `SHA256SUMS` retain commands/bindings. NumPy 2.4.2. Scratch approximately 434 MB, below 1 GB; one local numeric thread, no cpu64.

UNRUN: native/GPU/FFT/movie producers, independent double-IFFT oracle (separate parent task), image-pixel reads and comparator rerun, fitting, all-882 rehash, heldouts/Maarten, source campaign, CI, GPU faults, truth/scientific acceptance, later-iteration causal attribution, estimator intervention and performance qualification. Existing 0.001 RRMSE gate unchanged; no candidate, M1 remains HELD.

Completed UTC: 2026-10-26T16:37:15.399684+00:00
