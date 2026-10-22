# Independent review R1: C1 CPU qualification tooling `cpu1b`

Reviewed commit `6000ec7444e959dcd3f09182b80d74c8d7b3916b` (detached in the supplied worktree; HEAD and index verified clean). Candidate source `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`.
Read-only review: no edits, commits, SSH, builds, native or GPU work. Only host mock tests (macOS, one thread, after an occupancy check) and my own probes in this directory.

## Result

**No launch-blocking findings.** I found no path where an incomplete, wrong-binary, wrong-fixture, nonzero-exit, partial-control or missing-key input produces PASS. Seven lower-severity items are listed below. Items 1 and 2 are worth a parent decision before the go-file is written. The rest are readbacks or notes.
This is a tooling review. Nothing here is native, science or performance evidence, and no `cpu1b` row has run.

## What I checked

| Item | Result |
|---|---|
| Identity and source | `git diff e77a51a2..6000ec74` outside `docs/post_rc0/c1-20261022` is empty. `tools/` and `tools-v2/` are unchanged since packet `4facd76d`. The cpu1 files are unchanged by 6000ec74. |
| Frozen chain hash | `chain-cpu1b.sh` sha256 is `5864c2b25cfd33e43038bf35ea716f6c71c952a417013f9c5e14e149d01e1bcd`, matching the author's frozen `5864c2b2…e1bcd`. The other frozen files (manifest, identities, expanded stages, tools-run list, preflight) are not in the repo, so I could not hash them. |
| Host tests | `test_cpu1b_sums.py`: 18 tests, OK (rc 0). Run with `python3 -B` on macOS, stdout/stderr kept in `stdout.txt` and `stderr.txt` here. |
| Argument order | The chain's `compare`, `v2check` and `decide` calls match the function signatures (`cpu1b_sums.py:84`, `96`, `120`). |
| RUN.json schema | The census runner writes `exit`, `binary_sha256`, `movie_sha256`, `argv`, `env`, `gpu_uuid` (`c1_census_runner.py:60-64`). `run_ok` reads exactly `exit`, `binary_sha256`, `movie_sha256`. The T24 prereq reads `rc` and `gpu_run`, which are the keys `c1_lane.run_case_nb` writes. |
| v2 schema | `eval_v2.py:24,37-49` always writes `case`, `native_exit`, `dc`, `checker_exit`, `checker_message`, `field_px`, `field_angstrom`, `field_gate`, `checker_status` (`ABORT_NO_RESULT` when no report). `sampling_status` is optional. The retained published eval has all 8 cases in order, so the required-key set fits real output, including the ABORT and UNIDENTIFIABLE rows (`noisy`, `flat`, `repeated`). |
| Prereq self-receipt fix | Correct. `c1_stage.sh` creates `cpu1b-prereq.{reserved,cmd,pid,started,log}` before running; the old `cpu1-*` glob would have matched them. The new filter skips only `cpu1b-prereq.*`. |
| No-GPU route | `chain_has_no_gpu_helper` regex is correct (the empty `CUDA_VISIBLE_DEVICES=` export is not matched). `c1_v2.sh cpu` exits before its GPU lock; `c1_census_runner.py` calls `lock_gpu` only for `cuda`; `c1_tutorial24.py run --cpu` passes `gpu=False` so `run_case_nb` takes no lease or `nvidia-smi`. The check is static on the chain text only; the called scripts are as above. |
| CPU allocation | Native stages use `taskset -c 8-9`, `--j 2`, `OMP_NUM_THREADS=2` (census, F control, v2, T24 via `q.CPUS`). `--ingest float` is accepted by CPU builds (`motioncorr_runner.cpp:159-165`). T24 CPU arm arguments equal those of the retained F-cpu baselines (same `BASE_ARGS` in v1 and v2). See item 3 for the unpinned Python stages. |
| T24 comparison | Fail-closed already (tools-v2 `classify`): IDENTICAL only for a complete, consistent report. DIFFERENT or INVALID stops the chain (allowed set is `0`). |

## Fail-closed probes (my own, `probe.py`, sha256 `73e21aa9…1156`)

Mock sums, real `cpu1b_sums` functions:

| Input | `compare` | `decide` |
|---|---|---|
| truncated RUN.json, `exit` as string `"0"` | rc 2 | rc 5 INCOMPLETE |
| RUN.json valid JSON but a list or `null` | **uncaught `AttributeError`, process exit 1** | uncaught `AttributeError`, exit 1 |
| `exit: false` | accepted (`False == 0`) | accepted |
| NaN in C1, F and reference, all equal | rc 1 (`array_equal` is False with NaN) | rc 4 FAIL |
| Inf at the same place in C1, F and reference | equal | rc 0 PASS |
| C1 and F both empty arrays, reference non-empty | different | rc 3 INCONCLUSIVE |

Everything else in the author's 18 tests also behaves as stated: partial, wrong-name and extra sets, nonzero/foreign-binary/unbound runs, partial and wrong-name F control, nonzero F run with an existing MRC, stale comparison file ignored, one- and two-sided missing v2 keys, wrong case names/count/order, wrong `dc`, nonzero native exit.

## Findings

All non-blocking. Severity is for the qualification evidence, not for the science.

1. **Medium, plan-level: an INCONCLUSIVE K269 decision stops the chain before K269 metrics and K272.**
   `cpu1b-census-decision` allows only exit `0`, so `decide` exit 3 (C1 differs from the retained cross-host sums, equals same-host F) writes `chain-cpu1b.stop` before `cpu1b-census-metrics`, `cpu1b-image-cpu` and `cpu1b-image-controls`. Those three stages do not depend on the cross-host comparison. Exit 3 is a defined, informative outcome, and the earlier stage `cpu1b-census-cmp-retained` deliberately allows `0 1`, which shows the author wanted to continue past a difference. This is unchanged from cpu1 and is conservative, but if a cross-host difference is plausible (different CPU, FFTW kernel selection), the K272 CPU image rows would stay UNRUN and need a later iteration. Decide before freezing whether `3` should be allowed for the decision stage (exits 4 and 5 still stop). The authors' rule says no in-place repair after launch, so this is the cheap moment.

2. **Low-medium: a crash in `compare` is indistinguishable from "some differ".**
   `run_ok` (`cpu1b_sums.py:46`) calls `r.get` on whatever `json.loads` returns, so a RUN.json that is valid JSON but not an object raises `AttributeError`; Python exits 1; the chain allows `0 1` at `cpu1b-census-cmp-retained`, so it continues into the F control. `decide` then hits the same exception (exit 1, not allowed) and stops, so there is no false PASS, but the stage receipt reads "differences" for a crash and the comparison JSON is missing. Not reachable with the real runner (it always writes an object). A `try/except` mapping any exception to exit 2 would close it.

3. **Medium, readback: CPU pinning of the Python stages depends on how the chain is launched.**
   Native stages pin themselves. `cpu1b-image-cpu` runs `image_batch.py eval … 2` (two worker processes) with no `taskset`, and the v2/T24 compare/eval, `decide` and metrics stages also set none. If the chain is not launched under `taskset -c 8-9`, those run unpinned. The launch command is not in the repo. Confirm the chain process is started with `taskset -c 8-9` and record `Cpus_allowed_list` of the chain PID in the launch receipt.

4. **Medium, readback: deployed tool directory content is not verifiable from the repo.**
   The chain calls `$V/cpu1_extract_ref.sh` (a cpu1 file, not in packet `4facd76d` or the cpu1b directory), the tools-v2 overlay versions of `c1_tutorial24.py` and `c1_lane.py`, and the derived census runner. The author describes `$V` as packet plus cpu1b files, and the preflight checks hashes of those files but not that each file the chain invokes exists in `$V`. A missing file would stop the chain at that stage (rc 127), after the T24 and v2 rows had spent compute. Repo hashes for comparison against `tools-cpu1b-run.sha256`:
   `tools-v2/c1_tutorial24.py 55a223ba…964e`, `tools-v2/c1_lane.py 85bbe465…aefaae`, `tools/c1_census_runner.py 2caa8566…d2b2`, `tools/c1_census.py 9d687e25…51a3`, `tools/c1_v2.sh 4fcdad25…98ae`, `tools/c1_run_v2_cases.py 051f2597…81aa`, `tools/c1_stage.sh b91a59a2…dbad`, `tools/c1_env.sh 0cc15694…068d`, `cpu1/cpu1_extract_ref.sh 8a0d21cd…4aea4`.

5. **Low: T24 F-cpu baselines are not bound to the frozen F binary in the prereq.**
   `f_cpu_baseline_{G,L}` checks `rc == 0`, `gpu_run` false and the 24/25 product counts, not that the baseline `RUN.json` `binary_sha256` equals the frozen F CPU hash `43cab2b7…` or that its `args` equal the C1 arm's. The baselines are the iteration-1 `F-cpu-*` arms, so the risk is low; a parent read-back of those two RUN.json files discharges it without refreezing.

6. **Low: `v2check` compares field metrics, checker status and message, not the `image` block.**
   `OPTIONAL_V2` keys are compared, `image` (including the published-sum metrics) is not. A C1 summed-image difference with identical STAR fields and statuses would not show in K267. Sums are covered by T24 and the census, so this is a labelling point: describe a v2check PASS as "field metrics and statuses equal", not "all metrics".

7. **Low, notes:**
   - No explicit finiteness check on sums: NaN in both arms reads as "different"/FAIL (fail-closed but mislabelled), Inf at identical positions reads as equal.
   - `exit: false` is accepted as 0; the real runner writes integers.
   - `load_ids` takes the expected counts from the same file it validates, and the file's hash is checked only in the prereq stage, not by `compare`/`decide`. A later replacement by a smaller self-consistent file would pass. The file is frozen and in the job's own scratch.
   - Output JSONs (`census-cpu-*.json`, `cpu1b-*.json`, `v2/*.eval.json`) are written with `write_text`, and the prereq checks only that the directories and stage names are fresh; stage-name reservation prevents re-execution, so this matters only if a file already exists at those paths.
   - v2 `runs.json` records `argv` but no binary hash; binding rests on the prereq binary hashes and immutable binaries.

## Launch readiness versus native evidence

- **Tooling readiness:** adequate to launch, subject to the parent's readbacks in items 3 and 4 and a decision on item 1. The author's claim that the identity, F-control, binding and v2-key fixes are in place is supported by the code and by my probes.
- **Evidence status:** UNRUN for every cpu1b row (T24 CPU G/L, K267 CPU, K269 CPU census with same-host F control, K272 image evaluation). The tooling review establishes none of the native, science or performance claims, and no earlier PASS/FAIL/UNRUN/INCONCLUSIVE/UNIDENTIFIABLE status is changed. The review does not touch the GPU rows or L attribution.

## Files in this directory

`REVIEW.md` (this file), `probe.py`, `stdout.txt`, `stderr.txt` (test run), scratch `probe-*` temporary directories created by `probe.py` (mock data only; safe to delete).
