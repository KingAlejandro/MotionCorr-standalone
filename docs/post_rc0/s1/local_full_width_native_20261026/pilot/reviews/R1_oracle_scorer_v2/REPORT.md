# Review: local full-width pilot draft, scorer v2, oracle floor (Opus, r1)

Reviewer: Claude Opus 5.5, read-only. Branch HEAD `ed897ebbf823d157de78531940889a37e5b03923` (PR290 draft); no branch, pilot, or source edits. No native/GPU/SSH/build/movie-intensity work. Local numerics ran on 1 thread (uv CPython 3.13.7, NumPy 2.4.2); scratch is 0.8 MB. Pilot directory byte-identical before and after (`pilot_before.sha256` = `pilot_after.sha256`).

**Verdict: no BLOCK. One MATERIAL pre-admission consumer requirement (M1). Everything else is LOW or CLEAR.** Native stays HELD. The draft cannot be executed and does not claim to be executable.

## CMake follow-up (5bcfa987, ed897 docs-only)
CLEAR. Production `src/` and `tests/` are unchanged from 634e4b48 (`git diff --stat 634e4b48 ed897ebb` touches only CMakeLists.txt and DESIGN.md). The five added lines set `ENVIRONMENT MC_EXPERIMENT_CCF_DC_ARM=none` on `LocalFullWidthWeight` only inside `if(MC_EXPERIMENT_CCF_DC)`. The evidence includes a discriminating negative: the caller's arm is unset, ctest passes 4/4, and running the binary directly without the arm aborts with exit 134. So the test property is what makes the test pass.

## Pilot admission (PLAN.md, ADMISSION_DRAFT.json, COMMANDS_DRAFT.json)
Matches the retained factorial `run_factorial.py` UP_only recipe:
- argv flags are identical, with `--experimental_local_b2` absent;
- the environment is the same set, with the same `MC_DIAG_*`/`MC_EXPERIMENT_*` scrub;
- patch is 3×3 exactly for noisy/affine/pedestal and 1×1 for the other five, so `do_local = patch>2` is false there;
- case order matches; maxiter 5, j 2, DC both, coupled all; no isotropic, half-gain, tolerance or downsample flags.

The 8×19 = 152 baseline pins equal the complete UP_only inventories in `results/RAW_INDEX.json` (sha `735d1435…`). The noisy/affine RUN/metrics/runtime/STAR pins match the local raw bytes, and `baseline_metrics` equals the retained `metrics.json`. The P1 set (affine, pedestal, zero, integer, fractional) is exactly the retained PASS rows. The binary, venue, source-clearance and fixture bytes are explicitly null or missing. Only 2 of the 33 fixture files are present locally (affine/noisy `_field.npy` plus MANIFEST).

## Scorer v2 (score_fields_v2.py, sha in NEGATIVES_RESULT.json)
In `NEGATIVES_RESULT.json` and `SYMLINK_CHECK.txt`, 21 negatives and both positive controls behave as intended. Rejected cases:
- wrong case;
- exit values 1, "0", True, False, 0.0, or missing;
- receipt/expected binary differs, uppercase hex, or 63 characters;
- a missing required name;
- a byte mismatch, or a same-size SHA mismatch;
- a listed file that is absent;
- `../`, absolute-path, and live-symlink escapes;
- a missing tap;
- malformed publication or pin types. These two fail closed via AttributeError/TypeError rather than ValueError.

field_metrics rejects: missing or integer `local_enabled`; 4-frame global; 17 coefficients; NaN; disabled-with-coefficients; truth SHA mismatch; out-of-bounds ROI; wrong pixel size (via `validate_star_rows`).

Module pins: all six local imports are hash-pinned before import and origin-checked after, including the transitive `generate_known_motion_fixture`. No `__pycache__` exists in the pinned source. The four retained score pairs reproduce to ≤6.22e-15 Å. My field_metrics positive control agrees, and the metadata-only fetches fail publication on the intended missing-file check.

**M1 (MATERIAL, consumer requirement before admission):** `complete_publication(run_dir, case, sha)` has no arm binding. A receipt labelled `arm=ON` passed into an OFF slot is admitted, and so is one with no arm field (rows `GAP_arm_*`). Both arms use one binary, so swapped OFF/ON directories pass every adapter check, and P2 ("ON strictly improves over OFF") would be scored backwards. The consumer must verify all of the following from the same run directory:
- the receipt `arm`;
- argv contains `--experimental_local_full_width_weight` iff ON;
- environment and cwd equal the COMMANDS_DRAFT entry;
- the witness count: 9 on 3×3 ON, 0 otherwise.

LOW findings:
- **L1 (witness location):** the witness is written to the per-movie log stream (`output/<case>.log`), not stdout. Its format is ` EXPERIMENTAL local full-width weight: x_norm = 42, pnx = 42, nfx = 22` (runner.cpp:4961-4962 at 634e4b48), one line per `alignPatch` patch call. compare_products treats `.log` as inventory-only, so the 9/0 witness check needs its own parser. PLAN and the manifest do not name the file or the format.
- **L2 (receipt completeness):** unlisted extra output files are admitted (`GAP_unlisted_extra_output_file`). The `runtime.json` contents are not hash-bound: an unparseable tap is admitted, and the error only surfaces later in field_metrics. For OFF, compare_products file-set equality against the retained tree covers this; for 3×3 ON nothing does. Fix: build the receipt by rglob at producer time and add SHAs for runtime.json and stdout.log.
- **L3 (field_metrics pinning):** an in-bounds but wrong ROI is accepted (`[0,96,0,128]`). A cross-case STAR (affine STAR with noisy runtime) is also accepted, because the two cases share geometry and truth bytes. The adapter does not check the MANIFEST SHA or `roi==[12,84,12,116]` itself; it depends on the caller. Note that `fm_wrong_truth_file` ACCEPT is correct by construction: `affine_field.npy` and `noisy_field.npy` are byte-identical (`839c484f…`).
- **L4 (admission pins):** `tools_sha256` lacks the comparator `compare_products.py` (factorial pin `53449d2d…5f0f47`, equal to the repo `global_damping_20261026/scripts/compare_products.py`). It also lacks `score_fields_v2.py`, `generate_known_motion_fixture.py` and `generate_realistic_motion.py`. PLAN line 25 requires the comparator pin.
- **L5 (deviations):** the retained producers ran with cwd = the full 33-file fixture directory, but the pilot stages only `<case>.star` + `<case>.mrcs` and uses a different `--o` root. Neither should change gated products, since compare_products normalises the root in STAR/EPS. However, PLAN line 15 says "match exactly" without stating these deviations. I could not inspect the STAR inputs for other references because the bytes are not available locally. The OFF compatibility gate fails closed if either deviation matters. The retained binary was built from 326f03a and the candidate from 634e4b48. The src delta (local CCF capture; `new_ft` observer defaulting to nullptr) is default-off by design, but OFF byte-compatibility is still an untested empirical gate.
- **L6:** `oracle_floor.py` imports V1 `score_fields`, which lacks the transitive and origin pins. The result is unaffected: my reproduction below imports neither adapter.

## Oracle floor: independent reproduction (oracle_reproduce.py → ORACLE_REPRODUCTION.json)
Method, different from the parent's:
- exact rational temporal projector P_T onto span{f,f²,f³}, f=0..4;
- Householder-QR spatial projector P_S on [1,u,u²,v,v²,uv];
- Kronecker projection on the dense 72×104 ROI over frames 0–4;
- own STAR global parser;
- no parent or consumer imports.

Truth and MANIFEST hashes are checked; plan hash `4b38aeb1…` is the one recorded in the result. File mtimes put the plan (20:08:14) before the script and result (20:11:26/27); that is weak evidence.

| case/G | reviewer RMS floor Å | Δ vs parent | p95 = max at optimum Å |
|---|---|---|---|
| noisy runtime | 0.036792526966214566 | 1.7e-16 | 0.0594253 |
| noisy STAR | 0.03679260984730614 | 3.2e-16 | 0.0594254 |
| affine runtime | 4.582282970e-05 | 2.1e-19 | 7.40e-05 |
| affine STAR | 4.496010060e-05 | 2.3e-17 | 7.26e-05 |

Additional checks:
- Coefficients agree with the parent to ≤1.9e-14 px. Reconstruction closure is ≤2e-13 px, and the Pythagorean split closes to ≤1e-12 relative.
- The native runtime local part lies in the oracle span to 3.9e-14 px. This confirms the coefficient order (3k+s), the frame origin and the coordinate convention, which is stronger than the parent's "native is no better" inequality.

**Interpretation challenge (important).**
- The spatially non-representable sum of squares is ~3e-25 Å². Truth is exactly inside the native family: it is zero at f0 and has no component along the temporal null vector t̂ = [0,−4,6,−4,1]/√69, which matches the exact null projector.
- The floor therefore reduces to a closed form in G alone: **RMS_floor = pixel_size·|t̂ᵀG|/√5**, with the 2-vector over axes. The residual is spatially uniform, so p95 = max = 6/√(69/5) = 1.615×RMS.
- For noisy, t̂ᵀG = (0.06822, −0.06315) px. The closed form reproduces 0.0367925270 Å.

Consequences:
1. Fixing G constrains almost nothing in this family. The spatially constant local term with cubic time dependence absorbs 3 of the 4 free temporal degrees of freedom of any global error. Only G's fourth-difference component is irreducible.
2. The floor carries no information about the local estimator, the patch observations, the CCF weight, or the 10 px fit rejection. It rules out only "fixed G alone makes the gate unreachable", which is what the parent claims.
3. That truth lies exactly in the family is a property of this affine fixture: the four 3×3 cases share one truth file, and the other fixtures were not computed. Do not carry this floor over to non-polynomial truth or other movies.
4. Native noisy is at 1.645 Å RMS, ~45× the floor. That failure is not caused by fixed-G representability. Nothing here predicts that the full-width flag reduces it.

**Existential statement: CORRECT, with these qualifications.**
- The full-precision RMS-optimal field in the fixed-G native-18 family passes all three limits on the noisy and affine movies (noisy: RMS 0.0368, p95 0.0594, max 0.0594 against .20/.40/.80). So a passing field exists in that family for these two exposed G, which is more than "RMS floor < 0.20". p95 and max are values at the RMS optimum, not minima.
- STAR serialisation, reviewer check only (not a native writer round trip): the oracle coefficients are at most 0.384 px in magnitude. Rounded to 5 decimals they still pass (noisy runtime-G: RMS 0.03679, max 0.05942). A worst-case triangle bound of 1e-4 px per coefficient changes the field by ≤0.0235 Å per vector, giving upper bounds RMS ≤0.0603, p95 and max ≤0.0830, all inside the limits.
- Existence says nothing about whether the native 9-patch fit with the inherited rejection can produce these coefficients. No floor subtraction is valid.

## Missing consumer/admission requirements (before any native launch)
M1 arm/argv/env/cwd binding plus the 9/0 witness parser on `output/<case>.log`; L2 rglob-complete receipts with runtime.json and stdout.log SHAs; L3 consumer-side MANIFEST-SHA, ROI and case-path checks; L4 comparator and adapter pins. Already explicitly missing in the draft: the final Linux binary and source archive, compiler/config, venue and lease admission, all 33 fixture bytes at the venue, and the retained 8×19 baseline bytes at the venue.

## Artifacts
ATTEMPTS.txt records two failed attempts: a STAR comment-parse crash, and a non-discriminating dangling-symlink fixture that was superseded by SYMLINK_CHECK. See SHA256SUMS for the scripts and results.
