# Independent read-only review: native CCF DC prototype + control admission (PR 289)

Reviewer: Opus (one independent reviewer, read-only). Date 2026-10-26.

## Verdict

**Source at b75039a0: CLEAR for its bounded scope (hooks, iso test weight, witness, tap, oracle and mutants), with one exception.** The `CcfDcRequest` CTest registration is broken (BLOCKING B1, confirmed on the venue by the author and on the host by me). A fix is pending and the delta review is still open.
**Control admission at f293ab9d: NOT YET ADMISSIBLE for runtime-tap scoring.** Three plan issues must be fixed first (M1-M3). None of them is a production-source blocker.
This review does not clear the 16 native movies, a full 100, a merge, M1, a default change or DC adoption.

## Pins

- Production+test source `b75039a04f8d3937660066fcb391c79f6083e1f0`, base C1 `b305b23bc7572aaafb0a7fa9fdfdd0c350fb4ce3` (ancestor confirmed), tested production `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`.
- `git diff b305b23 e77a51a -- src tests CMakeLists.txt cmake scripts` is empty.
- Docs-only head `f293ab9dd9f80b53727832c49fbdcfb7d7a81f4e`. Its tree ids equal b750's: src `80cbd7a8…`, tests `b34bd267…`, CMakeLists.txt `55cd45bd…`. The `b750..f293` diff touches only `docs/post_rc0/ccf_dc_native_compat_20261026/` (5 files).
- Blobs at b750: CMakeLists.txt `55cd45bd5d42`, src/experiment_ccf_dc.h `5b73c108874f`, src/motioncorr_runner.cpp `5632bdc292f4`, src/acc/cuda/cuda_alignpatch.cu `64fab1b0ff6b`, tests/experiment_ccf_dc_stage.cpp `4f02e8b96bc4`, tests/test_ccf_dc_request.py `e264a38c8f69`.
- Blobs at f293 (docs/post_rc0/ccf_dc_native_compat_20261026/): DESIGN.md `f5ce53cb235b`, CONTROL_PLAN.md `1742c4c8a635`, ledger.csv `3373dde4f18e`, pairs.csv `dbfdaa68dce6`, counts.json `eff56455192f`, make_ledger.py `ab35651780d6`.
- PR 289: draft, open, head `f293ab9d`, 0 comments at review time.

## Findings

### BLOCKING

**B1. `CMakeLists.txt:573-576` @b75039a0: the `CcfDcRequest` registration passes empty argv elements.** `$<$<BOOL:${MC_EXPERIMENT_CCF_DC}>:--experiment>` and the `--iso` generator expression expand to `""` when false. argparse then exits 2 with "unrecognized arguments". The test therefore fails in the `def` build (two empty args) and in the `exp` build (one empty arg), and passes only in `iso`. This blocks plan items B1 and B2.
- Host check: CMake 4.4.4 generates `add_test(T "/bin/echo" "--binary" "b" "" "")`, and argparse rc=2 on `['--binary','b','','']`.
- The author reports the same failure on the venue; those logs are retained by the author.
- Fix direction: build the extra args as a list, or use `COMMAND_EXPAND_LISTS` with a list-valued generator expression, so that "false" yields no element. Then show the test passes in all three builds, and fails when given the wrong build flag.
- Delta review stays open for the follow-up commit.

### MATERIAL (control plan / docs; not production-source blockers)

**M1. No unchanged consumer exists for the runtime tap in the K or N tier.** This is a missing future consumer, not a source defect.
- CONTROL_PLAN §3 says K267 is scored "by the unchanged `tools/check_motion_diagnostics.py --case <id>` from the runtime tap and the actual STAR separately". That checker accepts only a motion STAR or a dense `F,Y,X,2` `.npy` (`--candidate`, line 203). It cannot read the tap JSON.
- DESIGN says the tap "is read by the unchanged `tools/check_realistic_motion.py`". That tool needs a realistic-motion `--receipt` with `recipe`, so it does not apply to K267 or N.
- The retained N scorer (`ed1a0e3f:.../native_ncontrols/scripts/score_ncontrols.py`) is not reusable unchanged:
  - it hard-codes the W5 path `/tmp/motioncorr-w5-20261025-7b76b848`, a W6 JSON and the `runs/runs.json` layout;
  - it maps arms `a/DCg/H2g/DCg+H2g`, so `none/both` raise a KeyError;
  - it parses `[align] scope=global iterations=…`, which C1 does not emit (no such string in src), and the old console line `MC_EXPERIMENT_CCF_DC arm=…`, which is now a JSON witness. Both silently become `None`.
- STAR-side K scoring works now.
- Required before runtime scoring of the K/N tiers: a tap→dense-field bridge (no truth input, C1 polynomial convention, `xshifts*prescaling`) and an N adapter that reuses only `common.score/field/rms`. Convergence should come from the C1 log parser (`check_realistic_motion.convergence`), which needs runs without `--skip_logfile`. All of these must be reviewed and parent-frozen, with no gate change.

**M2. A failed run does not always leave the tap placeholder.** `DESIGN.md` ("Runtime-field tap") says "A crashed or failed run leaves the placeholder". The tap is rewritten at `skip_fitting` (`src/motioncorr_runner.cpp:4098-4115` @b750), which is before dose weighting, sum and image writes, and STAR publication. A later failure (write fault, DW error) leaves a complete-looking tap with no status field.
- Correct the sentence.
- State that tap rows count only with producer rc 0 plus publication. Plan §1 already says this for the witness.

**M3. Native stage-arm rows can pass vacuously.**
- Nothing requires the witness to show `frames_eligible>0` for every stage an arm selects, at the expected site.
- B4 says "`cuda_batched` (if the batch path ran)", which fails open.
- The native K267 CLI (patch settings) is not pinned anywhere in the repo or ledger. At 128x96x5 the local stage may not run, so the `local` arm would equal `none` and `both` would equal `global`.
- Requirement: per row, assert eligible>0 at the declared site for each selected stage, otherwise mark the row INCONCLUSIVE, never PASS. Pin the K/N/M CLIs as part of the parent pins.

### LOW

- **L1.** `tests/experiment_ccf_dc_stage.cpp:503-524`: the G6 reuse passes run with whatever arm the main loop left (arm 3, `both`). The fresh references use arm 0. Equality holds only because P=0 makes the DC bin already zero. Set the arm explicitly before the reuse passes.
- **L2.** `--expect-failure` accepts a failure in any gate. This is acceptable because the unmutated oracle must pass and the mutation is deterministic. Per-gate attribution in the output would make a "killed" result more specific.
- **L3.** Stale or inconsistent text:
  - DESIGN "Tests" says "Six restoring mutants" but lists and registers seven (3 CPU, 4 CUDA).
  - The PR 289 body still cites `662ab0fb`, "isotropic not ported", "six mutants" and "open admission question".
  - CONTROL_PLAN §3 says "Jobs … = 64" while §6/ledger K = 96 (the 32 extra rows are the identity rows; the text explains this).
- **L4.** `CcfDcRequest` does not exercise an existing but unreadable tap. The read() probe uses `fopen(...,"rb")` and only `experimentCcfDcPrepareTap`'s `"wx"` (O_EXCL) catches that case. This is structurally correct but untested. The report is created in read() before `parser.checkForErrors()`, so a CLI error leaves an `atexit` witness with zero counts; this matches the documented semantics.
- **L5.** B3's "tiny synthetic movie" and B4's tiny CUDA movie have no ledger rows. The ledger also carries no CLI/config/input pins; the parent pins must supply them.
- **L6.** §3's rule that iso arm none must "reproduce the retained CPU rows" does not say bitwise or tolerance. The arithmetic is identical to PR286 `20e52f57` `ccfWeightAt`/`ccfWeightXNorm` (verified), so bitwise is the natural criterion. The binary differs, as the plan notes.

## Source checks that are CLEAR (b75039a0)

- **Default build:**
  - No hook code is compiled.
  - The additions are one include and `experimentCcfDcCheckRequest` (env reads only; it can only refuse).
  - The `#else` weight expressions are byte-for-byte the original. CUDA passes the same `nfx` value through `const int weight_x_norm`.
  - The CUDA `Key` changes only under the iso macro.
  - Behaviour without the variables is unchanged by construction. B3 must still show it at runtime.
- **Hook coverage, all CCF inverse sites:**
  - CPU `alignPatch` (runner.cpp:4903, after the CCF product, before `inverseFourierTransform`).
  - CUDA `cudaAlignPatchDeviceWithWorkspace` (cu:654), reached by the plain and arena global paths (`cudaAlignPatchDeviceInArena` → WithWorkspace), local per-patch, and retry via `alignPatch`→`cudaAlignPatch`.
  - Batched per-patch loop (cu:1024; every patch slot is zeroed).
  - Movie-session, DW and FFT-prep C2R calls are not CCF and are untouched.
- **Ordering and layout:** every kernel uses the legacy default stream and there is no `cufftSetStream`, so the zero kernel is ordered before `projectHermitianColumns` and C2R. The per-frame stride `ccf_nfy*ccf_nfx` matches the CCF layout. Resident spectra are not written (G4 checks this; mutant `cuda_single_resident` is registered).
- **Isotropic test weight:**
  - The CPU expression equals PR286 `ccfWeightAt`.
  - Local is bitwise unchanged in the iso build: `nfx*nfx` is exact in double, and the CUDA value is unchanged.
  - The CUDA `is_global` key forces re-setup on global→local reuse.
  - The batched path uses its own workspace with `pnx/2+1` (cu:955).
  - The arena workspace is created per call.
  - The CPU weight is rebuilt every call from a const, so there is no cache and no race.
  - Identity is reported in the witness, and CMake refuses iso without the experiment option.
- **Witness:**
  - Counters are atomic.
  - The static state is constructed before `std::atexit` registration, so the handler runs before the state is destroyed.
  - The `atexit` status is documented as not meaning success.
  - `system/popen` children exec, so the handler cannot rerun in a child.
  - An abort leaves `incomplete`.
- **Tap:** exclusive pre-pixel creation after the `--only_do_unfinished`/`--do_at_most` filtering, with zero or several movies refused. The body is the #269 block, verbatim.
- **Mutant harness:**
  - `motioncorr_core` is STATIC, so the mutated object replaces the archive member.
  - A missing or non-unique anchor makes configure fail (FATAL_ERROR).
  - `--expect-failure` returns 0 only on an oracle failure. A setup error returns 2 and a crash returns nonzero, so neither passes.
  - The two CUDA anchors are distinguished by indentation.
- **License:** the new files carry `GPL-2.0-or-later` SPDX and the repo is GPLv2 (LICENSE/COPYING), so they are compatible.

## Performed vs UNRUN

**Performed:**
- git object and tree-identity pins;
- full read of the source/test/CMake diff b305..b750;
- read of DESIGN, CONTROL_PLAN, make_ledger.py, ledger, pairs and counts at f293;
- ledger regeneration;
- one host CMake/argparse check;
- PR286 iso arithmetic comparison;
- inspection of the retained N scorer and the K/realistic checkers;
- gate_contract thresholds (`.001` unchanged) and AGENTS review rule;
- PR 289 metadata.

**UNRUN:**
- any MotionCorr build, CTest, oracle, mutant, native or GPU run;
- G1-G6 results on the venue (they are the author's and still pending);
- the full issue 238/262/36 and PR284/288 discussion threads, which I did not re-read (I relied on the cited commits and docs).

### Host checks (scratch `/tmp/mc-native-ccf-dc-opus-review-20261026-r1`, 128 KiB)

1. **genex-check.** A minimal CMake project with `add_test(... $<$<BOOL:${EXP}>:--experiment> $<$<BOOL:${EXP}>:--iso>)` and EXP=OFF.
   - Generated command: `"/bin/echo" "--binary" "b" "" ""`.
   - argparse rc=2 "unrecognized arguments".
   - sha256: src/CMakeLists.txt `093cc23f…0599`, build/CTestTestfile.cmake `b156b333…77f5a`, ctest-V.out `4583433f…f630`. `cmake-version.txt` = 4.4.4.
2. **ledger-regen.** `python3 -I make_ledger.py --outdir ledger-regen`: rc 0. ledger.csv, pairs.csv and counts.json are byte-identical to f293 (176 jobs, 112 pairs). sha256 is in `ledger-regen/SHA256SUMS`.

No failures were discarded.

## Remaining admission (conditional)

Already-authorized tiny qualification may start only after all of these:
1. The B1 fix is committed and delta-reviewed.
2. On the venue, B1/B2/B2i pass in all three builds, including `CcfDcRequest`, the oracle G1-G6 and every registered mutant rejected.
3. M1-M3 are fixed in the plan, and the bridge/adapter is reviewed.
4. Parent pins for source, binaries, inputs and CLI are frozen.

The 16-movie tier stays HELD until the tiny K/N harm assessment is reviewed.
