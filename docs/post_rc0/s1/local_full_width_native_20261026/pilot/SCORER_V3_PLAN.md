# Scorer v3 criteria (frozen before any v3 code or test exists)

Scope: a pure consumer/admission layer for the HELD local full-width pilot. It launches nothing, reads no movie or
image intensities, and adds no numerical operator: the field operators, dense 72x104 ROI, limits and recipes stay those of
`score_fields_v2.py` (unchanged, imported by pinned hash). v1/v2 files, ADMISSION_DRAFT.json, COMMANDS_DRAFT.json and
PLAN.md are not edited. Answers: Opus review M1 (arm/argv/env/cwd/witness binding) and L1-L4; L6 by a provenance note.

## Public entry
`admit_producer(run_dir, expected, admission, evidence_root)` and `score_admitted(...)`, where `expected` comes from
`resolve_expected_row(commands, admission, case, arm, evidence_root, binary_path, binary_sha256)`. An unresolved draft row
(argv[0] `<PINNED_LINUX_BINARY>`, no binary hash) is never admissible. `field_metrics_lowlevel` is v2's `field_metrics`
re-exported unchanged and stays metadata-only: it is not producer admission.

## Receipt schema (RUN.json, schema `local-full-width-run-receipt-v3`)
`case, arm (OFF|ON), exit (int, not bool), binary_sha256, run_dir, argv, cwd, environment (exact declared dict),
controlled_environment_observed (every child env var named MC_*, OMP_*, GOMP_*, KMP_*, OPENBLAS_*, MKL_*, BLIS_*,
VECLIB_*, NUMEXPR_*), publication (output-relative path -> {bytes, sha256}, the complete rglob of output/), runtime
({bytes, sha256} of runtime.json), stdout ({bytes, sha256} of stdout.log)`. Strict JSON: NaN/Infinity rejected.

## Admission checks (each failure raises AdmissionError with a stable code)
1. SCHEMA: schema string, field types, strict JSON.
2. CASE: receipt case is the requested case and in the admitted case order. ARM: receipt arm is the requested arm and
   not missing/other.
3. EXIT: int 0.
4. RUN_DIR: resolved run_dir == resolved evidence_root/case/arm and equals receipt run_dir (a directory copied into the
   other arm's slot fails).
5. ARGV: receipt argv == expected argv exactly; FLAG_COUNT: `--experimental_local_full_width_weight` occurs exactly once
   for ON and never for OFF (duplicate/missing/wrong-arm flag). BINARY: argv[0] == expected binary path, receipt
   binary_sha256 == expected, 64 lowercase hex. PLACEHOLDER: any `<...>` token in expected argv.
6. CWD: receipt cwd == expected cwd (run_dir/input); INPUT: that directory holds exactly `<case>.star` and
   `<case>.mrcs`, regular files, whose bytes equal the admission fixture pins.
7. ENV: receipt environment == expected environment (exact dict); ENV_OBSERVED: controlled_environment_observed ==
   the controlled-prefix subset of the expected environment (no extra OMP/BLAS/MC variable, e.g. OMP_PROC_BIND).
8. INVENTORY: receipt publication keys == the complete set of regular files under output/ (no unlisted extra, no
   symlink/special file, no escaping path) and == the baseline output names of the case row; PUBLICATION_HASH: every
   listed bytes/sha256 matches.
9. RUNTIME: runtime.json exists, bytes/sha256 equal the receipt, strict JSON, finite, `local_enabled` bool, global 5x2,
   coefficients 18+18. STDOUT: stdout.log exists, bytes/sha256 equal the receipt.
10. WITNESS: output/<case>.log first line is `Working on <case>.mrcs with 2 thread(s).` (LOG_CASE). Lines containing
    `EXPERIMENTAL local full-width weight` must each match exactly
    ` EXPERIMENTAL local full-width weight: x_norm = 42, pnx = 42, nfx = 22`; any other form fails. Count must equal 9
    when arm is ON and the row patch grid is 3x3, otherwise 0; the row's declared count must equal that derivation.

## Scoring binding (`score_admitted`, `field_metrics_bound`)
Manifest sha256 == 9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc; case in manifest; ROI ==
[12,84,12,116] (any other ROI, even in bounds, fails ROI); truth file name == `<case>_field.npy` and its bytes equal the
manifest pin (TRUTH); runtime path == run_dir/runtime.json and STAR path == run_dir/output/<case>.star, both
receipt-hashed (CROSS_CASE); STAR `_rlnMicrographMovieName` stem == case (STAR_CASE). `score_admitted` derives paths only
from run_dir, so a producer cannot be scored against another case's STAR or runtime.

## Admission v3 draft (L4)
New `ADMISSION_DRAFT_v3.json` (version v3, supersedes ADMISSION_DRAFT.json by hash): all original pins plus the comparator
`compare_products.py` 53449d2da682305c8c11e3ed3efb91103530196e481ac075b00f90e3d5ea0f47, the six transitive consumer/
generator files, `score_fields_v2.py`, `score_fields_v3.py`, the v3 tests and builders, lane.py and factorial_common.py,
each with an explicit root key. Final Linux binary, source archive, compiler, venue, lease and clearance fields stay
null; status stays HELD. `COMMANDS_DRAFT_v3.json` is generated from it; its argv/cwd/environment equal
COMMANDS_DRAFT.json. `verify_tool_pins` rechecks every pin against files at caller-supplied roots.
Additive `ADMISSION_AMENDMENT_v3.md` states: staged two-file cwd and new output root versus the retained producers (cwd was
the 33-file fixture directory); retained binary built from production 326f03a0 vs candidate 634e4b48 (src equal at
215c37b0); OFF byte-compatibility with the retained baseline is an empirical gate, and an OFF identity or compatibility
failure stops before ON (`on_launch_permitted` returns False unless OFF compatibility and source identity are both PASS).

## Tests (fixed before running; tests/test_score_fields_v3.py)
Synthetic complete receipts built in scratch (<=100 MB; fake input/output files; real retained noisy runtime.json, STAR,
truth and manifest where scoring is exercised): noisy 3x3 OFF and ON, flat 1x1 OFF and ON.
Positive: all four admit; noisy OFF and ON score (runtime/STAR numbers equal the retained pair's); ON counts 9 witnesses,
the other three 0; real `generate` of the commands equals v1 argv/env.
Isolated negatives, each starting from a valid receipt and changing one thing, each must fail with its intended code:
missing arm; ON receipt in OFF slot; OFF receipt in ON slot; swapped run directories; missing flag on ON; flag on OFF;
duplicate flag; extra unknown argv; wrong binary hash; argv[0] placeholder; env value changed; missing env var; extra
OMP_PROC_BIND; cwd mismatch; extra/missing input file; input byte tamper; witness x_norm 22; pnx 41; nfx 21; 8 lines
on 3x3 ON; 10 lines; 1 line on a global-only ON; 1 line on OFF; non-matching spaced variant; log for another case;
unlisted extra output file; deleted listed file; changed listed byte; symlink in output; runtime.json tamper; runtime
tamper with matching receipt hash but NaN; runtime shape; stdout.log tamper; stdout.log missing; exit 1 with a complete
tap; case swap; ROI [0,96,0,128]; manifest hash swap; affine STAR in noisy run; truth of another case name; non-numeric
types in receipt. Controls: v2 `complete_publication` admits the swapped/omitted-arm, extra-output and
runtime-tamper receipts (documenting the gaps v3 closes). Original negatives: re-run v2's scorer_negatives table
against v3 where it applies; the four retained metadata score pairs reproduce within 1e-12 A through
`field_metrics_bound` and each is still rejected by `admit_producer`.
Every run, including failed attempts, is logged and kept. No criterion is changed after results; a failing criterion is
fixed in code or recorded, never relaxed.

## Not claimed
No producer exists, no native run, no estimator or native acceptance. Oracle numbers remain independently reproduced
direct-field RMS values of a fixed-G family, never a floor to subtract.
