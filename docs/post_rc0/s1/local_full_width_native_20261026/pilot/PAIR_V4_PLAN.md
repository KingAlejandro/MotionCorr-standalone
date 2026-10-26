# Pair and decision layer v4: criteria (frozen before any v4 code or test exists)

Answers Opus R2 M2 (missing pair/decision layer) and its LOWs (W1, P-anchor, expected-dict trust, T1-T3). Pure consumer layer:
launches no producer, reads no movie or real image intensities, adds no estimator and no new numerical operator. v1-v3, the
oracle, reviews, logs and tests are untouched. A passing v4 gate is a *condition* for a parent driver, never permission or a
native job. Native stays HELD: the final binary, source archive, compiler/config, shared libraries, venue and lease fields
of the admission are null, so the real admission can never satisfy `pre_ON_gate`.

## Trust roots
`pair_decision_v4.py` loads ADMISSION_DRAFT_v3.json and COMMANDS_DRAFT_v3.json itself and refuses unless their sha256 equals
module constants (hashes of the unchanged v3 files: no circular self-hash). It also pins `score_fields_v3.py` by hash. No public
v4 function accepts an `expected` dict, an admission dict or a commands dict; expected rows come only from
`score_fields_v3.resolve_expected_row`. The v4 file and its tools are bound out of band by the parent's review/release index.
`verify_tool_pins` runs before use, including the comparator (53449d2d...5f0f47) and `factorial_common.py`.

## Public API
`admit_single(case, arm, run_dir, ...)`: v3 `admit_producer` unchanged, then a case-insensitive prescan: any line of
`output/<case>.log` matching `local\W*full\W*width` (re.I) must equal the exact witness line, else WITNESS_VARIANT.
`pre_ON_gate(case, off_dir, baseline_dir, ...)`, `admit_pair(case, off_dir, on_dir, baseline_dir, ...)`,
`decide_pilot(evidence_root, baseline_root, fixture_dir, ...)`. Common arguments: evidence_root, roots (consumer_source, repo,
pilot), binary_path, binary_sha256, decision_dir. decision_dir must lie outside every run, baseline and evidence directory.
Every failure raises PairError(code) and writes decision_dir/STOP.json with the code and message; failures are retained.

## pre_ON_gate (derives, never accepts a typed PASS)
1. Anchored admission/commands load; status not HELD_* and every launch field (candidate_binary, source_archive,
   compiler_and_config, shared_libraries, venue_identity, fresh_venue_resource_admission, independent_source_clearance) non-null,
   else HELD. A placeholder or unresolved row, or a non-hex binary hash, cannot pass.
2. Tool pins at roots verify.
3. OFF admitted by `admit_single` (arm OFF).
4. Baseline directory holds exactly the 19 pinned retained files (rglob equality; no extras, no symlinks); every byte count and
   sha256 equals the admission row pin.
5. OFF runtime.json and output/<case>.star equal the baseline files byte for byte (compare sha256 and length).
6. The pinned `compare_products.py` is run as a subprocess (`sys.executable -B`, empty-ish env, cwd = decision_dir) on
   baseline/output vs OFF/output with the JSON written into decision_dir/pre_on/<case>/. Command, return code, stdout, stderr
   and JSON are retained there. Pass requires rc 0, JSON parse, verdict IDENTICAL, `n_gated_differing` 0, roots equal to the
   resolved arguments.
7. The record binds, by sha256: OFF receipt, OFF runtime, canonical OFF output inventory, canonical baseline pin inventory,
   comparator JSON, comparator command line, comparator file, admission file, commands file, tool pin set, binary path+sha,
   and the identity fields. `binding_sha256` is the hash of that canonical set.
`verify_pre_on_record` recomputes every bound item from disk and rejects any drift; it does not rerun the comparator but checks
the retained JSON hash and verdict.

## admit_pair
1. The pre-ON record for the case must verify against the current OFF.
2. Both arms are admitted by `admit_single` with the same resolver, same binary path and sha256, same identity fields; receipts
   must carry equal binary_sha256 and argv[0] (PAIR_BINARY).
3. Global trajectory: runtime `global` parsed as float64 and compared as uint64 bit patterns (shape 5x2); the STAR
   `data_global_shift` block text equal, extracted with the pinned `factorial_common.star_blocks`.
4. Manipulation counters parsed from each stdout.log with the pinned `factorial_common.manipulation`, extracted by AST (the
   module has top-level venue path side effects), exactly those two functions, with `check` replaced by one that raises PairError;
   no numeric logic is copied; the extracted source hash is recorded. Required: DC arm both and `manipulation`'s own coverage
   checks; global eligible > 0; 3x3: local eligible > 0 on both arms; global-only: local eligible == 0 and coupled patch peaks 0;
   global DC and global coupled counters equal pairwise; local counters may differ and are recorded.
5. Global-only pairs also: runtime.json bytes equal, case STAR bytes equal, and the pinned comparator run on OFF/output vs
   ON/output is IDENTICAL (command, rc, JSON retained in decision_dir/pair/<case>/).
6. Recorded separately, not as truth surrogates: `local_enabled` per arm, patch convergence/acceptance via the pinned
   `check_realistic_motion.convergence` on output/<case>.log (a parse failure is an error, never a pass).

## decide_pilot
Cases must be exactly the admission case order, unique, each with OFF and ON directories and no unlisted case directory
(CASES). For each case: pre-ON record verification plus `admit_pair`, then v3 `score_admitted` on both arms. Rules, all
computed here:
- P1: affine, pedestal, zero, integer, fractional ON gates PASS on both runtime and STAR under the unchanged 0.20/0.40/0.80 A
  rms/p95/max limits (OFF gates recorded).
- P2: noisy ON rms, p95 and max are each strictly lower than OFF on both runtime and STAR (a tie fails).
- `noisy_raw_gate` is PASS only if both noisy ON gates PASS; an improving P2 never changes a FAIL.
- Every strict increase ON > OFF of rms/p95/max (A), per case and field, including PASS->PASS, is listed with its gate
  transition.
- flat and repeated are always UNIDENTIFIABLE with their raw ON/OFF distances retained and no gate verdict.
- `prediction` is SUPPORTED only if P1 and P2 hold, else NOT_SUPPORTED; `acceptance` is always
  NOT_ACCEPTED_NO_AUTOMATIC_ACCEPTANCE; no full100, adoption, image or CUDA meaning.

## Tests (fixed before running; tests/test_pair_decision_v4.py)
Synthetic receipts and tiny fake byte products only (valid minimal MRC: 1024-byte header + 16 payload bytes; STAR/EPS texts
embedding their own resolved output root so the comparator's normalisation is exercised); real retained noisy runtime/STAR
for the 3x3 branch; the actual comparator subprocess; a test copy of the v3 admission/commands whose launch fields are filled,
whose input/baseline pins match the fake bytes, and whose hashes replace the module anchors (a documented test double).
Positives: baseline/OFF/ON valid 3x3 branch; valid global-only branch; decide_pilot over eight synthetic cases with scoring
delegated to v3 for noisy/affine and to a crafted-metrics test double only for cases whose truth fixtures are absent.
Isolated negatives (one change each, intended code required): real HELD admission refused; a launch field null; altered
anchored admission/commands file; hand-edited commands (max_iter 9, OMP 8) with a matching receipt; hand-built patch grid
cannot bypass the entry (a 3x3 ON run with 0 witnesses fails); baseline extra/missing/changed byte; baseline runtime or STAR
differing from OFF; comparator-detected differences in MRC header, MRC payload, STAR, EPS and file inventory; missing OFF
runtime; pre-ON record absent, tampered, or bound to a different OFF byte; stop before ON (failure writes STOP.json and ON
is never admitted); same binary path with different sha; changed global runtime bit (1 ulp) and changed global STAR block;
global-only changed payload (comparator), runtime or STAR; missing DC stage, zero DC counter, global counter drift,
3x3 local eligible 0, global-only local eligible > 0, coupled/DC coverage mismatch, duplicate or absent counter line;
convergence log unparsable; P1 pass lost on one case/field; P2 one metric regressed, one tied; PASS->PASS increase listed;
raw FAIL stays FAIL with improving P2; flat/repeated stay UNIDENTIFIABLE; missing, duplicate, extra, reordered cases;
forged caller PASS strings and dicts rejected by the public signatures; unresolved placeholder.
Additional v3-gap tests (R2): lowercase/hyphen-less/underscore witness variants (WITNESS_VARIANT); T1 extra staged file whose
bytes match its pin and a missing movie with all other pins matching; T2 runtime `1e400` with a matching receipt hash (NONFINITE);
T3 a real symlink in output listed in a self-consistent receipt (INVENTORY).
Guard-removal controls (tests/mutation_controls_v4.py): weaken one guard per scratch copy and require the intended tests to fail;
a guard that the suite shows to be shadowed is reported as shadowed, not claimed as killed. Every run, including failures, is kept.

## Not claimed
No producer exists or obeys; synthetic receipts test consumer logic only. No native run, estimator accuracy, byte neutrality
of any real run, or acceptance. The oracle is unchanged and not rerun.
