# Independent review R2: C1 CPU qualification tooling `cpu1c`

Target commit `67beb5f59382a74bbc64b10bfa488ab3d549dc0c`; candidate native source `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`.
Read-only review. No SSH, native binary, build, GPU, movie or science run. No edits, commits, pushes, PRs, comments, Notion writes or nested tasks. Only host-side mock/fixture controls (macOS, one numeric thread, after an occupancy check) and my own probes in this directory.

**Worktree note.** The supplied worktree was at `1f0a58bf`, not detached at `67beb5f` as the brief said (HEAD and index were clean, and I changed nothing). `67beb5f` and `e77a51a2` exist in the shared object store, so I exported both with `git archive` into `src/` and `e77/` here and reviewed those.

## Result

**No launch-blocking findings.** I found no path where an invalid, incomplete, wrong-binary, wrong-fixture, nonzero-exit, non-finite, non-object or checker-ABORT input produces PASS. The parent's false-PASS control is rejected, and every real checker output I generated (including FAIL, UNIDENTIFIABLE and outside-ROI rows) is accepted. Five lower-severity items follow; item 1 is an expectation to set before launch, and item 2 needs a parent readback.

This is a tooling review. Nothing here is native, science or performance evidence. Every cpu1c row is **UNRUN**, and no earlier PASS/FAIL/UNRUN/INCONCLUSIVE/UNIDENTIFIABLE status is changed.

## What I checked

| Item | Result |
|---|---|
| Scope | `git diff --name-only e77a51a2 67beb5f5` outside `docs/post_rc0/c1-20261022/` is empty, so production source is unchanged. `tools/`, `tools-v2/`, `cpu1/`, `cpu1b/` are unchanged since `6000ec74`. The new `cpu1c` files carry no licence or copied third-party text (GPL check: nothing to find). |
| Frozen chain hash | `chain-cpu1c.sh` sha256 `f82d7b4c3139e9f07e2bc82419b3ebb4a0bcf4111dbb9d76ad0dcf9058e69647` equals the author's frozen `f82d7b4c…69647`. The other frozen files live only on the remote and I could not hash them. |
| R1 retained verbatim | `cpu1c/review/CPU1B_R1_REVIEW.md` sha256 `14517c28…ed3b` equals my R1 `REVIEW.md`. |
| Host tests | `test_cpu1c_sums.py`: 19 tests OK (`stdout.txt`, `stderr.txt`). |
| Checker contract vs real code | Read `tools/check_motion_diagnostics.py:65-84,160-217` and `eval_v2.py:23-50`. Exit is `1 if sampling != VALID or (role == gate and accuracy FAIL) else 0`, and `2` for `INPUT ERROR` (no report). `accuracy_status` is UNIDENTIFIABLE only for `flat`/`repeated`. Roles: gate = zero/integer/fractional/affine/pedestal, characterization = noisy/flat/repeated. `cpu1c_sums.py:146-166` encodes exactly this. |
| Real-checker cross-check (`probe_real_checker.py`) | I generated the e77 #267 fixtures locally and ran the **real** e77 checker CLI on 7 candidate variants × 8 cases (truth, +0.3 px, +1.5 px, +5/+9 px x, −9 px y, +13 px x). Rows built the way `eval_v2.py` builds them were fed to `v2check`. All 7 variants returned exit 0, including gate FAIL with exit 1, noisy FAIL with exit 0, and UNIDENTIFIABLE with `OUTSIDE_FIXED_ROI` and exit 1 (`probe_real_checker.out`). So legitimate truth FAIL/UNIDENTIFIABLE rows are accepted. |
| PASS-outside-ROI rule | `cpu1c_sums.py:163` rejects PASS with sampling outside the ROI. The checker computes accuracy independently of sampling, but truth sampling margins on these fixtures are 4.0–12.0 px against a 0.904 px gate (`margin.py`), so that combination cannot occur on real data. The rule cannot reject real evidence. |
| Parent control | CLI `v2check` on `parent-control/{c1,F,published}.json` returns **2**; the old `cpu1b` helper returns 0 on the same files (asserted by the test). The retained old-schema published eval, used as both arms, also returns 2. The control files lack `sampling_status`, so the missing-key rule fires first; the null-metric, ABORT-status and exit-2 rules are exercised by other tests and by my mutants (see item 3). |
| Real RUN/identity binding | `c1_census_runner.py:51-64` writes `exit` (int), `binary_sha256` (computed from the binary actually run), `movie_sha256`, and `argv`/`env` into `<arm>/RUN.json`. `run_ok` (`cpu1c_sums.py:71-85`) requires a strict JSON object, integer 0 exit (bool/float/string rejected), the expected binary hash and the fixture receipt's movie hash. Identity counts are the module constants 100 and 10, with control exactly `dose1-s00..09` (`:60-68`). At the real 100/10 contract with mock sums: clean → compare 0 / decide PASS; a NaN-token `exit` and a missing `movie_sha256` → compare 2 / decide 5 (`probe_helpers.out`). |
| Finite sums, decide path | C1 and F both empty on the 10 controls, reference non-empty → decide **5** (R1 had accepted INCONCLUSIVE). Identical Inf/NaN → invalid (author tests). |
| Stale output | `decide` recomputes every comparison from raw sums and RUN files and ignores any comparison file (`:202`, tested). `eval_v2.py:26-36` consumes only a fresh private-path checker report. Result directories are created with `mkdir(exist_ok=False)` (`c1_run_v2_cases.py`, T24 `run` refuses an existing dir), and stage names are reserved atomically (`c1_stage.sh`). |
| Chain text | 15 `go` lines, 17 stages after the `G`/`L` loop. Arguments match function signatures: `compare` 7, `v2check` 4, `decide` 8, `image_batch.py eval … x 2` gives 2 workers. Pure-text prereq checks run locally against the real chain: no GPU helper regex match, empty `CUDA_VISIBLE_DEVICES` export present, every `$V/` script the chain uses is in the repo-derived tool set. The chain differs from `cpu1b` only by the stated changes (diff reviewed: header comments, `.cpus` readback and pin stop, prereq arguments, `"0 3"` on the decision stage). |
| Whole-chain affinity | The chain records `Cpus_allowed_list` from its own `/proc/self/status` and exits with a `.stop` unless it is `8-9`; the prereq re-checks it. Children inherit it, native stages add `taskset -c 8-9`, `--j 2`, `OMP_NUM_THREADS=2`. The image stage's two worker processes inherit the mask. |
| F baseline pins | The T24 C1 CPU arm builds `['--i','movies.star','--o','<d>/out/','--j','2',BASE_ARGS minus --ingest]` + patch flags for L (`c1_tutorial24.py:40-48`), which equals the argv the prereq asserts for the F-cpu baselines. Binary hash, argv, cwd, mask, env and rc are asserted, not only the pinned copy hash. |
| F control flags | The frozen F source (`6d68e2d6`) defines `--ingest` and `--ingest_witness` (`src/motioncorr_runner.cpp:158-159`), so the F control run does not fail on unknown options. |
| Exit allow sets | `cpu1c-census-cmp-retained "0 1"` (1 = some differ, 2 invalid stops). `cpu1c-census-decision "0 3"`: 3 INCONCLUSIVE continues to the independent metrics and image rows; 4 FAIL and 5 INCOMPLETE stop, as does any other code. All other stages allow only 0. The image rows only run after `decide` has validated all 100 C1 and 10 F runs. |

## Mutation check of the guards (`mutate.py`, 20 effective mutants of `cpu1c_sums.py` plus one no-op placeholder, author's 19 tests)

14 killed: metric dictionary and finite checks, bool exit, non-finite sums, binary hash, fixture binding, run exit, count-from-file, control names, `c1==F`, PASS-outside-ROI, checker-exit rule, `sampling_status` required, status-vs-gate. 6 survived; none exposes a hole in the code:

- *Accept checker exit 2* and *accept ABORT status*: equivalent, the later `want`/gate-agreement rules still reject.
- *F-run binary unchecked in the c1-vs-F loop*: equivalent, `f_ref` already validates F runs.
- *Strict JSON off*: equivalent, NaN/Inf then fail the integer-exit or finite-metric rule.
- *Empty-sum guard removed*: survives only because `np.max` raises on empty arrays in `compare`; the guard is not covered on the `decide` path (item 3).
- *`main()` catch-all narrowed*: survives because the tests never reach it (item 3).

## Findings

All non-blocking. Severity is for the qualification evidence.

1. **Low-medium, expectation: the retained K267 evals show ABORT rows; a real e77 row may or may not.** All four retained evals (`docs/post_rc0/s1/synth_combined/evidence/v2-comb-{cpu,cuda}-{none,both}.eval.json`) have `noisy` and `repeated` as checker exit 2, `ABORT_NO_RESULT` ("candidate samples outside fixed valid detector region") and no `sampling_status` key. They predate `66952415` (retain field diagnostics for invalid candidate sampling), which is in e77. Truth sampling is valid for all eight cases (checker run with the truth field as candidate: all VALID), so the abort came from the candidate sampling. With e77's checker such rows should become `OUTSIDE_FIXED_ROI`, exit 1, which `v2check` accepts. If a real row still aborts (an invalid summed image also gives exit 2), `v2check` exits 2 and the chain stops at `cpu1c-v2-check` after only the two small v2 native stages, before T24 and the census. That is correct fail-closed behaviour, but the parent should expect it as a possible outcome and not read it as a C1-vs-F regression. `cpu1c_sums.py:158-165`.

2. **Low, readback: the tool manifest count.** The author says the frozen manifest has 32 files. My reconstruction from git (tools packet 27 files, with the six `tools-v2` overlay files replacing same-named ones, plus `test_c1_t24_failclosed.py`, `cpu1_extract_ref.sh`, `cpu1c_sums.py`, `cpu1c_prereq.py`) gives **31** (`repo-derived-tools-manifest.sha256`, sha256 `d5a03e1b…71af`). The extra file is probably one of `OVERLAY.md`, `cpu1_sums.py`, `cpu1_prereq.py` or `make_manifest.py`, or something not in git, in which case "git-derived" is imprecise. The prereq enforces exact set equality against the frozen manifest either way, so launch safety does not depend on this. The parent should list the remote manifest names, diff them against my file, and name the 32nd before writing the go-file.

3. **Low, test gap (code correct, verified by probe).** (a) The empty-sum guard on the `decide` path is not covered by a test (`cpu1c_sums.py:100`); my probe shows decide returns 5. (b) `main()`'s catch-all (`:234-236`) is not covered: the author's test passes through the inner handlers. CLI probe with wrong arity returns 2 / 5 / 2 for compare / decide / v2check as claimed. (c) The "actual control files" test uses rows without `sampling_status`, so on its own it does not isolate the ABORT-specific rules.

4. **Low, labelling: what "equal" means.** Census, `decide` and the T24-independent parity use `motion_field.read_mrc` (`tools/motion_field.py:247-256`), which decodes any mode to float32 and ignores the header and trailing bytes; I confirmed float64-vs-float32 equal values compare equal. Say "decoded sum payload equal", never "byte-identical" (output is not byte-reproducible anyway, per prior findings). `v2check` covers field metrics and checker statuses only; the `image` block is not compared (the author labels this correctly).

5. **Low, receipts.** (a) `chain-cpu1c.{cpus,pid,started,stop}` are written with `>`. A second launch while `logs/chain-cpu1c.go` exists overwrites them before `c1_stage.sh` refuses the duplicate `cpu1c-prereq` (exit 4). No compute can repeat, but copy `.pid`/`.started` after the one launch. (b) `chain-cpu1c.done` means the chain ran to the end, not that every stage passed: `cpu1c-census-decision.exit` may be 3. The aggregate verdict must be built from the stage `.exit` receipts and `census-cpu-decision.json`, with INCONCLUSIVE carried through. (c) `census-cpu-vs-retained.json`, `census-cpu-decision.json` and `census-cpu-metrics.json` do not carry the `cpu1c` prefix and the prereq does not check them for absence; every writer runs only after its stage reserves a fresh name, so a stale file cannot be read after a successful stage.

## Not asserted by the tools (author-disclosed or design)

- `runs.json` for K267 carries `argv` but no binary hash; binding rests on the prereq binary hashes of immutable binaries.
- `decide` and `v2check` do not compare C1 and F `argv`/`env`/mask; same-host F parity relies on the identical frozen runner invocation in the chain text.
- The T24 F-cpu baselines are the iteration-1 runs, not same-session reruns; their binding is the pin/RUN.json check in the prereq.

## Launch readiness versus evidence status

- **Tooling readiness:** adequate to launch, subject to the parent's own readbacks: the remote frozen hashes and 25-check preflight under `taskset -c 8-9` (the author reports 25/25; unpinned fails only the affinity check), the F-cpu RUN pins `05cf608d…`/`4b2ffd1f…`, and reconciling the 31-vs-32 manifest count (item 2). Earlier cpu1 partial-control, nonzero-F-exit and missing-key fixes have not regressed (tests and mutants).
- **Evidence status:** UNRUN for every cpu1c row (K267 CPU field/status parity, T24 CPU G/L identity, K269 census vs retained sums and the 10-movie same-host F control, K272 image rows). cpu1 and cpu1b remain unlaunched and unmodified. The review establishes no native, science or performance claim.

## Files in this directory

`REVIEW.md` (this file); `SHA256SUMS.txt`; `stdout.txt`/`stderr.txt` (test run); probes `probe_real_checker.py` (+`.out`), `probe_helpers.py` (+`.out`), `probe_empty_decide.py` (+`.out`), `mutate.py` (+`.out`), `margin.py`; `repo-derived-tools-manifest.sha256`; `src/` and `e77/` (exports of the two commits); `fx/` (locally generated #267 fixtures and truth-probe outputs); `probe-tmp/` (mock data, safe to delete).
