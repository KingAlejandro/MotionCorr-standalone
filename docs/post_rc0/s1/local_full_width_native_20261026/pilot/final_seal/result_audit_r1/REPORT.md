# Independent result audit: native local full-width weight pilot (sealed HEAD 9d5f6ad3)

Auditor: Claude Opus 5.5 (review sub-agent), 2026-10-26, read-only. Inputs: repo HEAD `9d5f6ad382f64923be097e876963be2eeba34b77`
(clean), local bundle `~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-AUDIT-BUNDLE-r1/` (MANIFEST.json sha256
`49698c7ca37fd840b5930063ae13d946604e0407dd1102bf283696b86bbb669e`). No native run, SSH, build, image/pixel read, new fit or agent.
Interpreter: uv CPython 3.13.7, numpy 2.4.2, single-threaded BLAS env. Scratch < 1 MB.

## Verdict
**Not approved for publication as written; wording only.** Every metric, gate, launch-budget and pair-equality claim reproduces.
Approve (CLEAR for bounded reporting) once FINAL_PILOT_REPORT.md lines 24 and 30 are amended per M1/M2. L1-L4 are recommended.
No metric or gate needs to change.

## Recomputed independently (`scripts/02_independent_metrics.py`, own STAR parser and own 18-term basis; no author or pinned code)
- Truth: 8 NPYs, each (5,96,128,2) float64, finite, frame 0 identically 0; hashes equal truth/MANIFEST.json entries; that manifest
  is `9697c203...` (the admission pin). 8 unique case names equal the manifest cases. ROI rows 12:84, cols 12:116 = 72x104 px x 5 frames.
- Runtime and actual STAR fields for all 16 runs, with global frame-0 = (0,0) in runtime and STAR. Maximum difference to DECISION.json
  (noisy P2 values; flat/repeated raw distances in A and px): **7.1e-15**, within 1e-12. P1 gates, P2 strict flags, increases, noisy raw
  gate and prediction all equal DECISION.json.
- Noisy runtime (A) OFF -> ON: rms 1.6453708531561486 -> 1.095426088140216, p95 3.337290305991788 -> 2.240216728988467,
  max 7.284025716813742 -> 4.4692154437241225 (max diff to the expected values 4.4e-16). STAR: 1.645397 -> 1.095423, 3.337279 -> 2.240267,
  7.283784 -> 4.469288. Both fields FAIL .20/.40/.80 in both arms.
- P1 (affine, pedestal, zero, integer, fractional): PASS on runtime and STAR in both arms. Increases over all 8 cases x 2 fields x 3
  metrics (strict ON > OFF, PASS->PASS included): **none**. Affine and pedestal decrease in all metrics; the five 1x1 cases are exactly equal.
- flat/repeated: UNIDENTIFIABLE status in DECISION; raw distances unchanged between arms (rms 2.104421 / 9.012581 A), both FAIL.
- STAR vs runtime roundtrip max: 5.47e-4 px (noisy ON), 4.91e-4 (noisy OFF), <= 1.87e-4 elsewhere; STAR coefficients equal runtime
  coefficients to print precision.

## Checked mechanically (`scripts/01_verify_bundle.py`, `scripts/03_mechanical_v2.py`)
- Bundle: 258/258 manifest entries match bytes and sha256; all files read-only. Unbound on disk: MANIFEST.json, MANIFEST.sha256 and
  truth/MANIFEST.json (the last is bound by the admission pin instead; see L4). Repo final_seal copies of manifest, README, audit tables
  and remote verification are byte-equal to the bundle; final_seal/SHA256SUMS verifies.
- Ledgers: r1 = launching, finished (noisy OFF, exit 0, receipt `ab9ae373...`), STOP COMPARATOR; driver_rc 1, lane_rc 0. r2 = REUSED
  (receipt `ab9ae373...`, r1 ledger and STOP hashes equal the bundled r1 files, launches_before 1, remaining 15, ceiling 16), 15 launches
  indices 1-15, noisy OFF not relaunched, last event **DECIDED** 23:32:19Z (SUPPORTED / NOT_ACCEPTED_NO_AUTOMATIC_ACCEPTANCE,
  launches 15, global 16); no STOP event or STOP.json in r2; driver_rc 0, lane_rc 0. 16 launches, 16 unique receipts, all exit 0,
  none timed out. REUSED_OFF_INDEX receipt equals it. RESULT.json is byte-equal to DECISION.json. DECISION.pair_record_sha256 matches
  the canonical-JSON hash of each pair.json.
- Per run: RUN.json sha equals the ledger receipt and products_inventory; copied runtime/STAR/log/stdout/input-STAR hashes match the
  inventory and receipt; inventory output set equals receipt publication. argv equals COMMANDS_V5_2 after substituting the binary
  placeholder and the root `/tmp/motioncorr-local-full-width-native-20261026` -> `/tmp/motioncorr-lfw-v5-20261026`; env and cwd likewise;
  env identical across runs except MC_DIAG_MODEL_OUT; ledger argv_sha256 reproduces as sha256(json.dumps(argv)). Flag count 1 ON / 0 OFF.
  Binary sha `bb92e061...` in all 16. Witness lines exact, 9 on the three 3x3 ON runs, 0 elsewhere.
- Pairs (all 8): global float64 bits equal; STAR data_global_shift and data_general blocks byte-equal; global coupled-peak counters and
  DC global and local eligible/zeroed counters equal (noisy 10/115, affine and pedestal 15/55, zero and flat 5/0, others 15/0).
  local_enabled True on 3x3, False on 1x1. Five global-only pairs: runtime.json and case STAR byte-equal; saved comparator JSON and
  command hashes match pair.json; verdict IDENTICAL, 10 files, 7 gated, 0 differing, rc 0. Pre-ON: 8/8 PASS, comparator IDENTICAL, JSON bound.
  r1 pre-ON comparator: DIFFERENT, 2 gated files (corrected_micrographs.star, noisy_shifts.eps); r1 STOP unchanged.
- Resource receipts (record only): 16/16 OBSERVED, 7 samples stored each, not truncated, 0 read failures, no first_errors, 0 vanished,
  0 children-file-missing. Recomputed from stored samples: max Threads 2, max tasks 2, process-level Cpus_allowed_list `32-47`, 3 PIDs
  (motioncorr, sh, gs), span 0-123 ms, wall 0.129-0.130 s; stored summaries agree.
- Source: d1c498b8 tree = `033794b4...` (build receipt); src identical to 634e4b48 and CMakeLists.txt identical to 5bcfa987; no src/CMake
  change d1c498b8..HEAD.

## Convergence challenge (requested)
No inconsistency. Every run's stdout.log line 7 has an explicit native marker `[align] scope=global ... converged=1` with
last_rmsd < tolerance_px=0.5 (noisy 2 iterations, last 0.368717; affine/pedestal/integer/fractional/repeated 3; zero/flat 1, last 0).
The case log agrees in iteration count and last RMSD. pair.json `global_converged` and per-patch `converged` are real JSON booleans
(no list/dict truthiness), and agree with my parse. Tally: global TRUE 16, FALSE 0, AMBIGUOUS 0, MISSING 0.
Patches (derived from the final logged per-patch RMSD vs 0.5; there is no per-patch native verdict marker on CPU): noisy 8 TRUE / 1 FALSE
in both arms (Patch (2,3): OFF runs/noisy/OFF/noisy.log:38, 5 iterations, last 1.5895 px; ON runs/noisy/ON/noisy.log:43, 5 iterations,
last 8.36418 px); affine and pedestal 9/9 TRUE; 1x1 cases have no patches.
The earlier nonconverged noisy record (native_b2_20261026/README.md:50; independent_gemini4argon/REPORT.md:27, 5 iterations, final
1.40998 px) is a different configuration (B2 study, OFF runtime RMS 2.343 A). This pilot's OFF equals the B2-factorial `UP_only` baseline
byte-for-byte in runtime.json and case STAR (DIAGNOSIS_BYTES.txt), which converges. Convergence is not equated with accuracy here:
noisy converges globally and still FAILs.

## Findings (FINAL_PILOT_REPORT.md unless stated)
- **M1 (required), line 30** "Not established: full-field or real-movie accuracy" does not separate what ran from what failed. Fixed-ROI
  dense field scoring (72x104 x 5 frames, runtime and actual STAR) was completed for all 16 runs; the .20/.40/.80 contract is met by the
  five P1 cases and unmet by noisy (both arms) and flat/repeated (raw FAIL, UNIDENTIFIABLE). Not scored: pixels outside the ROI (border).
  Not tested: applied-image/application consistency, real movies. Suggested text: "Completed: fixed-ROI field scoring of all 16 runs
  (noisy still FAILs the accuracy contract). Not scored: outside the fixed ROI. Not tested: applied image, real movies."
- **M2 (required), lines 24 and 30.** "identical ... whole-product comparator output" and "byte neutrality beyond the compared products"
  read as raw byte identity. The comparator gates 7 of 10 files after root normalisation (logfile.pdf, logfile.pdf.lst and the case log
  are inventory-only); for the MRC it reports header bytes 0-223 and float32 pixels equal, label block different. Receipt raw sha256
  differ OFF vs ON in 6 of 10 files of every global-only pair (incl. the MRC and the case log). Pixel equality is comparator-reported;
  MRC payloads are not in the bundle. Line 11 "MRC header and payload equal" has the same issue (DIAGNOSIS_BYTES: header[0:224] equal,
  label block 224-1023 differs by timestamp).
- **L1, line 25** "Per-patch rejection counts are not recorded as such ... not derived here": the saved case STAR does show patch
  inclusion: noisy data_local_shift has 40 rows (8 patches) in both arms, centre (104,47) = Patch (2,3) absent; affine/pedestal 45 rows.
  Suggest stating that, and that it matches the one non-converged patch. Also rename "Convergence/acceptance" (acceptance collides with
  NOT_ACCEPTED) and say patch convergence is derived from logged RMSD, global from the native marker.
- **L2, line 25.** "1 not converged in both OFF and ON" hides that the excluded patch ends at 1.5895 px OFF vs 8.36418 px ON. It does not
  enter the fit; worth one clause.
- **L3, line 26.** Mask `32-47` is the process-level Cpus_allowed_list; per-thread masks were not sampled (UNTESTED), and 7 samples at
  20 ms over ~0.13 s can miss short-lived threads.
- **L4, bundle README.md:1-2** says every file is bound in MANIFEST.json; truth/MANIFEST.json is not (it is bound by the admission pin
  `9697c203...`, verified here).

## Not established by this audit
Producer-reported only: build (compiler, flags), binary identity on cpu64, device/host state, lease/flock state, remote file hashes,
comparator pixel equality. Unavailable: MRC/EPS/PDF bytes, full baseline trees. Not tested: native image application, applied-image
consistency, real data, independent noise seeds or N controls, GPU, full100, harm re-qualification, adoption. Noisy is one realization.

## Files
scripts/01_verify_bundle.py, 02_independent_metrics.py, 03_mechanical.py (v1, defective filter), 03_mechanical_v2.py; results/*.json,
*.stdout; attempts/ATTEMPTS.md (system python without numpy; v1 mechanical false alarms) and attempts/03_mechanical_v1.*.
