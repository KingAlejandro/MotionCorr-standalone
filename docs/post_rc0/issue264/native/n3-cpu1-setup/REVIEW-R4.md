# Independent review, round 4: #264 CPU-only N3/N4 proposal (cpu1)

Reviewer: fresh delegated task, read-only. Target `3751bd05a95412dff468557141f2e7e01ad21831` (parent `4d3702c2`),
branch `verify/264-native-20261022`. **Binding:** I detached the *supplied* worktree (`t3-6ef05058`) at the exact SHA; `git status --porcelain`
was empty before and after every command (0 lines). The author worktree `t3-96f54dde` was not touched; no git archive export was needed.
Host: macOS arm64, load 3.7–6.8 of 14 CPUs, one process at a time, `OMP_NUM_THREADS=1`. No edits or commits to the repo, no SSH, native binary, build,
GPU, movie, science, push/PR/GitHub/Notion, nested agent. Scripts inspected before execution. No name-based cleanup. Output: this directory only.

## Verdict

**No defect in the grading, receipt, refusal or stop logic that can turn UNRUN/FAIL evidence into a PASS. One material protocol finding (F1)
against the claim "source binding is checked before any build"; two low findings (F2, F3) and informational notes.**
Protocol readiness: **ready after F1 is fixed or the parent performs the live-tree check given below.** Native results: UNRUN. Science: no claim.
F3-old (non-finite models) and F4-old (RELION `ad0b230` parity sign-off, M4/F4) are carried unchanged; not assumed.

## Scope / provenance (verified)

- `git show --stat 3751bd05`: nine files, all under `docs/post_rc0/issue264/native/n3-cpu1/`. `git diff 4d3702c2 3751bd05` outside that directory: 0 files.
- `git diff --quiet 52affe31 3751bd05 -- src tests tools CMakeLists.txt` and `git diff --quiet 4b0e4e73 3751bd05 -- src`: both identical; `git rev-parse 3751bd05:src` = `edd1737d6cea…` as claimed.
  `52affe31`, `4b0e4e73`, `0a1f64ab`, `521fddae`, base `36913740` are ancestors (so a plain bundle of `HEAD` carries them).
- No change to `native/tools/*`, `predictions*.json`, overlay patch, `FROZEN.md`, `n3-iter2/` (diffs 0 bytes vs 0a1f64ab / 521fddae).
- Every sha256 prefix in the author's table and in `check_sources.py` `FILES` matches the committed files (`n3.py 68dcf292`, `runlib.py faa27bfa`, `build.sh e51a7cee`,
  overlay `f82196ac`, `predictions_iter2.json 6ff11cb5…859e`, the seven new files).
- GPL/scope: every new `.py`/`.sh` carries `SPDX-License-Identifier: GPL-2.0-or-later`; stdlib only; no dependency, no third-party code, no change to production, gates, tolerances, thresholds, defaults.
- No GPU path: no `nvidia-smi`, GPU lock, CUDA configure or `--gpu` in `chain_cpu1.sh`/`occupancy_cpu.sh`/`n3_cpu1.py`; `runlib.run(gpu=False)` never calls `compute_apps`;
  `build.sh` with `CFG=cpu` configures `-DCUDA=OFF` only; `run gpu` is refused in code. Builds `--parallel 2` on CPUs 14-15, build lock `flock -n`.

## Independent source reproduction (host, no native build)

I made `git bundle create head.bundle HEAD` at the SHA, cloned five trees from it and reproduced `tools/setup.sh` (patch -p1 overlay on base/cand/mutant, the
`' - Real(0.5)'` x4 removal for the mutant) with `setup_repro.sh` (this directory). Resulting `SOURCES.txt` equals the author's `iteration1_SOURCES.txt` **in every field
(HEAD normalised for the candidate): diff_sha256, status_lines, runner, helper** for all five trees (`70fc2de0…`, `55423793…`, `02d8f5c1…`, `d531871f…`, `8a3a1ad8…`, `439041e3…`).
The real `check_sources.py` against these live trees: `sources PASS []`. So the EXPECT values are correct for this commit.

## F1 (material for the protocol claim; low risk of a false science PASS): `check_sources.py` never reads the trees it claims to bind

`check_sources.py` parses `$G_SCR/SOURCES.txt` (text written once by `setup.sh`) and compares those *strings* to EXPECT. The only live reads are `git diff --quiet <ref> HEAD` on
`src-cand` (compares commits, not the working tree) and the five `FILES` hashes inside `src-cand`. `src-base`, `src-ov-base`, `src-ov-cand`, `src-ov-mut` (the three trees that are
actually built) are not touched. Consequently `FROZEN-CPU1.md` ("checked by `check_sources.py` before any build; mismatch stops the chain", "each tree's runner/helper/diff hashes must equal")
is overstated. Reproduced with the unmodified script (`bt/`, `only/` in this directory):

- Demo A: scratch with only `SOURCES.txt` and a `src-cand` symlink (the three overlay trees and `src-base` do not exist): `sources PASS []`, exit 0. The author's own positive control `sources_bound` is exactly this construction, so it cannot observe the trees.
- Demo B: live `src-ov-mut/src/local_motion_guard.h` replaced with the *centred* helper (`02d8f5c1…`), `SOURCES.txt` untouched: `sources PASS []`.

Backstop: build, run and grade are behavioural, so a wrong algorithm is still caught later (the mutant rows must match the uncentred predictions and N4 needs exactly 5 kills; legacy/finite rows are
decision- and value-checked). Not caught: drift in files that do not change those decisions (other runner/CMake/test edits in an overlay tree, a wrong `src-base` revision that behaves the same),
and nothing is receipted as *enforced*. `build.sh` does print `source <HEAD> dirty-diff-sha256 … status-lines …` into each build stage log, so a post-hoc comparison is possible.

Required before launch, either:
1. (preferred, small, no new math) make `check_sources.py` recompute from the live trees `git rev-parse HEAD`, `sha256(src/motioncorr_runner.cpp)`, `sha256(src/local_motion_guard.h)` (or `absent`) and `git status --porcelain | wc -l` for all five trees, and compare to EXPECT; keep the `SOURCES.txt` comparison as a second witness. Then add a negative control that builds a SOURCES.txt-correct/tree-wrong scratch (Demo B). This is a tool change, so it needs a new freeze commit and a delta review.
2. or the parent runs, after `setup.sh` and before `chain_cpu1.sh`, on every tree: `git rev-parse HEAD; git diff | sha256sum; git status --porcelain | wc -l; sha256sum src/motioncorr_runner.cpp; sha256sum src/local_motion_guard.h`, compares to the table in `FROZEN-CPU1.md`/EXPECT, and after the builds compares the `source … dirty-diff-sha256` line of `cpu1-b-ov-{base,cand,mut}-cpu.log` to EXPECT. Until one of these is done, claims must say "setup-time source hashes", not "source verified before build".

## F2 (low): receipts and run records are not bound after the run

`known-observations.json` is a deterministic function of the hash-pinned predictions file; it proves the planned injected strings, and `run cpu` refuses when it differs (verified, including a
positive control I added: valid receipts let `run cpu` proceed, `r4/receipt_roundtrip.py`, so the tamper refusal is not vacuous). But `n3.grade` never compares `RUN.json` `env.MC264_N3_COEFFS`
to the receipt, nor `binary_sha256` to the build receipt or across rows of an arm. My mocks (`r4/extra_negatives.py`): a row whose `RUN.json` env is all zeros, and an arm whose rows carry
a different binary hash per row (8 rows), both still give `CPU subset PASS`. Backstop: the outputs themselves identify the injected model (accept rows: all 36 published coefficients within `1e-5 + 1e-7|b|`; reject rows: guard delta within 2e-5 relative, which is a function of the fitted model), and base/cand/mut must behave differently on the frozen cases.
Parent post-run check (no tool change needed): for the 21 overlay rows `RUN.json` `env.MC264_N3_COEFFS` == receipt string; per arm one `binary_sha256`, equal to `build-<arm>.binaries.sha256`; three distinct arm hashes. Same classification as F1 option 2 if you prefer to automate.

## F3 (low, launch hygiene)

- `diff_sha256` depends on git's auto abbreviation of `index` lines: in my full local clone the overlay diff hashes to the patch file (`f82196ac…`, 8-char index), in a bundle clone to the recorded `26274cd3…`/`4b01e260…`. A bundle made as `git bundle create X HEAD` (above) reproduces the recorded values; a bundle or clone with a different object count could change the abbreviation and cause a fail-closed stop at `cpu1-sources` (harmless, but burns the new scratch name). Dry-run the exact bundle with `setup_repro.sh`-style steps outside the assigned scratch, or drop the diff hash in F1's fix and rely on the file hashes.
- `chain_cpu1.sh` does not witness its own affinity; the lane depends on the launch line being `taskset -c 14-15 …`. Record `taskset -pc <pid>` in the PID receipt.
- `flock -n /tmp/motioncorr-i61-cpu-14-15.lock true` creates that file if absent and is a point-in-time probe; build/CPU locks follow the required nonblocking pattern.
- "cap 8 GiB" is implemented as a scratch size check at start and end only (`du -sk`); there is no runtime RSS cap or mid-run size check. Sizes here are tiny (768x512x12 fixture, three builds), so I rate this informational; confirm the intended meaning of the cap.
- Early development control runs `-01`/`-02` are not retained (author's `host-controls/README.txt`); not a gate.

## Grading logic: findings that matter for your focus list (all verified by running the real `n3_cpu1.py grade` on mock scratches)

The author's 22 controls reproduce exactly (my run: `author-controls/CONTROLS.json`; `all_controls_ok true`, the 22 (scenario, control_ok) pairs equal the committed record).
Plus my nine (`r4/extra`, 7 asserted, 2 documenting): published coefficient off by 1e-3 or 2e-5 → FAIL (power of the coefficient check; 5e-6 passes by design, STAR prints 5 decimals for negatives);
`idx 35` missing → grader raises, subset FAIL (fail closed); duplicate guard line → FAIL; empty `ov-base-cuda` dir → FAIL; base/cand images identical where decisions differ → pair FAIL.

- **Cannot make aggregate PASS:** `full_n3_n4_aggregate` is the hard-coded string `INCOMPLETE: 16 CUDA rows UNRUN` in every report. Subset PASS needs all of: original grader returned 1 with summary exactly `{PASS 24, FAIL 0, UNRUN 16}`, 24 expected CPU keys all PASS, the 16 expected CUDA keys all UNRUN, no CUDA arm dir, exactly 8 CPU pairs PASS and no CUDA pair, N4 PASS with kills exactly `{A_x, A_y, B_x, B_y, E}` (derived from the predictions). Original `ARMS` is unedited, so the 16 UNRUN rows remain in `RESULTS.json`. Verified negatives: missing GPU/CUDA row evidence is not a problem (it is the expected UNRUN), but any CUDA artefact, missing CPU row, nonzero rc, old 3.3 printed value (fails at `guard value 3.3 vs 3.1818`), absent overlay line, overlay on Z, wrong STAR presence either way, missing MRC (grader raises → fail closed, no subset PASS), changed predictions file (refused at import by sha256).
- **Native failure path:** `n3.run` continues after a nonzero row but returns 1, so `cpu1-n3-cpu` fails and the chain stops before `cpu1-grade`: no `CPU_SUBSET.json` is written. That is fail closed (absence = no verdict); partial rows are retained.
- **Known-observation hook order:** the overlay (`n3_observation_overlay.patch`) sits after the patch alignment and before `MC_STAGE("fit polynomial")`, the guard call and reconstruction, with the same `patch_xs[i]/nx - 0.5` and `patch_frames[i]` the fit uses. Receipts are written by `cpu1-receipts` after the three builds and before `cpu1-n3-cpu`, so the plan is fixed before any run; they record the injected *model* (exact `MC264_N3_COEFFS`, hash, rational coefficients, predicted outcome), not per-observation values, as `FROZEN-CPU1.md` itself says.
- **STAR parser vs real writer (static, since the mock STAR is synthesised from the author's own assumptions):** `Micrograph::write` emits `data_global_shift` and `data_local_motion_model` (`micrograph_model.cpp:248,260`); `ThirdOrderPolynomialModel::write` emits 18 X then 18 Y rows of `(idx, coeff)`; `MetaDataTable` prints doubles as `%12.6f`/`%12.5f` (`%12.6e`/`%12.5e` if `|v|<1e-3` or `>1e5`, in a 12-character buffer) and ints as `%12ld`. `star_blocks` (`len==2 and parts[0].isdigit()`) cannot confuse the 5-column `local_shift` or the float `hot_pixels` rows. Injected coefficients are 0…2095 so nothing is truncated; maximum rounding 5e-6 is inside the `1e-5 + 1e-7|b|` allowance; `RFLOAT` is `double` unless `RELION_SINGLE_PRECISION` (not set in `CMakeLists.txt`). The first native run is still the first real test of these conventions (including `out/km_local_nonsquare.{star,mrc}` naming); a mismatch would fail closed and must be retained, not repaired in place.
- `occupancy_cpu.sh`: awk selects exactly `cpu14`/`cpu15` (tested on a synthetic `/proc/stat` including `cpu140`, correct busy/total), `bash -n` OK for both scripts.

## Actual `data_local_shift` observations: not required; allowed and disallowed claims

`Micrograph::write` fills `local_shift` only on the accept path (`motioncorr_runner.cpp:3935-3945` runs after the guard and RMSD check), so it can never witness the reject rows, which are the discriminating ones (A on candidate; B/E on legacy and mutant; G). Where it exists (accept rows) it would duplicate what the 36 published coefficients already show: a 192-observation exact fit recovered to ~1e-7 relative cannot come from observations other than the injected model. The overlay line (`n_obs`, 768x512, 12 frames) and the guard delta (a scalar of the fitted model, checked to 2e-5 relative) cover the rest. So a new witness is **not material** for the bounded CPU engineering control.

Allowed if the subset passes: "On three TEST-ONLY CPU overlay builds (base+overlay, candidate+overlay, uncentred mutant+overlay) run through the actual runner on `km_local_nonsquare`, seven injected known 36-coefficient models produced the frozen decisions, printed deltas, published/absent local model and base/candidate image relations; the uncentred mutant differed from the candidate on exactly A_x, A_y, B_x, B_y, E." State the commit, setup-time source hashes (or live ones per F1), binaries, command lines, rc, CPUs 14-15 and the lock/occupancy logs.
Not allowed: "observations validated per patch/frame", N3/N4 PASS or CPU+CUDA qualification, anything about CUDA rows/mutant/N2-GPU (UNRUN), motion-estimation accuracy, ordinary-movie or production-binary behaviour (overlay builds differ from production by the patch), timing, CPU parity adoption before M4/F4, or that the original iteration-0a N3 passed (it stays UNRUN; cpu1 is a new iteration with the iteration-2 predictions).

## Carried / informational

- Old F3 (non-finite fitted models accepted by both guards) and old F4 (maintainer parity decision) unchanged.
- R3 I-1 (missing MRC) is exercised and fails closed; I-2 (`Z_no_overlay` has no frozen decision) unchanged and acceptable as an overlay-off control; I-3 (prediction hash binding) is now enforced in `n3_cpu1.py` and `check_sources.py`.

## Statuses kept

Host helper and real-model controls (rounds 1-3): unchanged, not rerun, source identical. Grading controls for cpu1: host-mock PASS (author 22/22 reproduced; my 9 extra as above). Native CPU subset, 16 CUDA rows, CUDA mutant, N2 GPU, native iteration 2: **UNRUN**. N1, N2 CPU, original CTest 77/111/114: parent-verified earlier, not reviewed here. No timing, accuracy or science claim.

## Next bounded action

Author fixes F1 option 1 (and ideally records `taskset -pc` and the F2 post-run comparison in the grade or the parent checklist), freezes a new commit, and a fresh delta review confirms only `check_sources.py`, its control and docs changed. Alternatively the parent adopts F1 option 2 and F2 as written launch preconditions. Then the parent verifies the exact bundle, refreshes occupancy/locks and authorises one CPU launch.

Artefacts here: `REVIEW.md` (+ `REVIEW.sha256`), `setup_repro.sh`, `bt/` (bundle-reproduced trees, `SOURCES.txt`), `only/` (demo A), `head.bundle`, `author-controls/` and `author-controls.log`, `r4/extra_negatives.py`, `r4/receipt_roundtrip.py`, `r4/extra/`, `r4/extra_negatives.log`, `trees/` + `SOURCES.local.txt` (full-clone variant showing the abbreviation dependence).
