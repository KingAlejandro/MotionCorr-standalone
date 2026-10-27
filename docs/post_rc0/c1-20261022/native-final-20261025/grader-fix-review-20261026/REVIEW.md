# Review: C1 i8 multi-device grader fixes and ingest-poison applied text (PR #282)

Reviewer: Opus 5.5 (high), read-only, 2026-10-26. Branch `integration/c1-20261022` @ `19162f43`, worktree `t3-b91ca8c4`.
Evidence: `docs/post_rc0/c1-20261022/native-final-20261025/` (`tools/`, `summary/`, `c1-i8-evidence.tgz` extracted fresh, read with `python3 -I`).
No GPU use, no edit to the C1 branch, nothing posted.

| Item | Verdict |
|---|---|
| (a) Fix 1, StopIteration / lazy `first_ret` (+ `--regrade` mode) | **APPROVED-WITH-NOTES** |
| (b) Fix 2, widened digest regex (`i8d-redigest`) | **APPROVED-WITH-NOTES** |
| (c) PASS verdicts for d1, d2, dshim, d4, dpoison, d4poison, dpoison_both | **APPROVED-WITH-NOTES** |
| (d) Negative control for the fixed grader | **APPROVED** (none existed; built here, 21/21 mutants caught) |
| Ingest-poison applied text (Opus round-1 low items) | **APPROVED-WITH-NOTES** |

No material defect found. The multi-device row's PASS stands. The notes below are limits on what the retained records can show, not reasons to rerun anything.

## (a) Fix 1: grader bookkeeping

`grade_dataset` in `tools/c1_item12_mg.py` (sha256 `6e6ba987…`, same as `tools-v3c-run`/`-v3d-run` in the tarball) differs from the frozen `tools-v2/c1_item12.py` only at lines 365-373. `digest_tree` is unchanged.

- For non-faulting workers, `tut` and `ret` are never read: the healthy branch at :389-395 uses `SHARDS[n][k]` directly. Before the fix, the code raised `StopIteration` for d4poison w0, whose shard `[0]` holds no 10641 movie. After the fix it does not.
- For faulting workers whose shard holds a 10641 movie, the computed `tut` and `ret` are the same as before.
- For a faulting worker with no 10641 movie, the fix adds a new failure (:370-371). It does not skip the worker.
- No expectation was dropped, made optional or skipped for any arm. The arm table passes `fault_worker` explicitly: dpoison uses 1, the same as the old hard-coded value, and d4poison uses 3.

Notes on `--regrade` (:455-459), which is part of the same fix:
1. `rc` is rebuilt from `dataset_status.json`: PASS gives 0, and `Worker phase exited N` gives N. For d4poison, the rc check is therefore not independent of the failure-reason check. The observed process rcs for d1, d2, dshim, d4 (0) and dpoison (3) were printed before the crash (`logs/i8-mg-item12.log`). d4poison's real process rc was never recorded, and `d4poison.driver.log` is empty. The per-worker rcs `[0,0,0,1]` in `workers/status.json` were observed.
2. The leftover-process check is replaced by `leftovers=[]`. For d4poison, the substitute evidence is `process_cleanup.complete=true` and `logs/occupancy-i8-mg-item12-post.txt` (23:55:40Z), which shows no compute app and no motioncorr process on CPUs 96-103.
3. The regrade is not strictly read-only. Line :481 deletes every `*.mrc`/`*.pdf` under `c1-item12/dataset`. This is inherited design, but it removed the MRC payloads, so their identity can no longer be checked again (see (c)). The packet's "read-only follow-ups" should say this.
4. In d4poison, the faulting worker's shard is `[3]`, so the rule that a healthy movie before the faulting movie keeps its products is vacuous there (`tut=[]`). That rule is exercised by dpoison w1 (00031 kept). d4poison adds a stronger check: w1 also holds a 10641 movie (A002) on GPU0 and completed with `fault=off`, which shows that the fault was selected by UUID.

## (b) Fix 2: widened regex

`tools/i8d_redigest.py` `digest_tree` is AST-identical to the grader's `digest_tree` after renaming the parameter `r` to `root` and substituting `(?:item12-retry|c1-item12)` for `item12-retry`. Nothing else in the restated copy differs.

What it can mask: the pattern `c1-item12/dataset/[A-Za-z0-9]+` stops at `/`, so it replaces only the arm tag (`d1`, `d2`, `dshim`, `d4`).

What the differing lines were (`grader_controls.json` → `digest.line_diff_d1_vs`):
- Under the inherited regex, each of the 12 logs (d2, dshim, d4 × 4) differs from d1 in exactly one line: `Written aligned and dose-weighted sum to …/c1-item12/dataset/<tag>/workers/wN/Movies/<movie>.mrc`.
- Line counts are equal (241/241, 592/592, 490/490).
- Under the widened regex, zero lines differ.

Mutants of the retained trees, each scored by the committed `i8d_redigest.py`:
- A changed shift digit in a d2 log: DIFFERENT.
- A wrong movie name in the normalised path line: DIFFERENT.
- A changed value in a dshim STAR: DIFFERENT.
- A row dropped from the d2 joint STAR: DIFFERENT.
- A d2 log naming d1's directory: IDENTICAL. This is expected, because a write into another arm's directory is masked by design, as it already was by the QF regex.

Limits:
- **EPS content is not retained**: the `_shifts.eps` files were excluded from the tarball and listed in the index only. The IDENTICAL result for EPS therefore cannot be reproduced offline. The circumstantial evidence fits a single tag occurrence per file:
  - byte sizes are equal for d1, d2 and d4 (92345, 92343, 57414, 88511);
  - each dshim file is exactly +3 bytes, which is `len('dshim')-len('d1')`;
  - the shifts STARs the plots are drawn from are identical;
  - the six aggregate EPS files have the same sha256 across all arms.
- The inherited `time` filter also drops a content line, `nvCOMP ingestion: pinned staging pool grown to … (worker lifetime)`, which appears in d2, dshim and d4 for 00031 but not in d1. Here it is benign: in the single d1 worker the pool was already grown by the earlier movie. It is inherited, not introduced by this fix, but the filter is broader than it appears.

## (c) PASS verdicts against the raw records

Running the fixed grader offline on the retained trees gives `[]` problems for all seven arms (`grader_controls.out`). The first-stage grader (`tools-v3-run`, `a72b7871…`) reproduces `StopIteration` at d4poison and gives the same result on the other six arms. Hand-checked records:

| Arm | dataset / ready / failure | worker rcs | devices = witnessed (distinct) | wrapper | merged |
|---|---|---|---|---|---|
| d1 | PASS / true / – | [0] | b2cb2c39 (1) | – | yes |
| d2 | PASS / true / – | [0,0] | b2cb2c39, eddb42fe (2) | – | yes |
| dshim | PASS / true / – | [0,0] | same (2); shim counter 41 = d1 retried 41 | – | yes |
| d4 | PASS / true / – | [0,0,0,0] | b2cb2c39, eddb42fe, cd5b9f86, 063e5232 (4) | – | yes |
| dpoison | FAIL / false / Worker phase exited 3 | [0,1] | 2 distinct | w1 `fault=on cvd=GPU-eddb42fe…`, injected + refusal ×2; w0 `fault=off` | no |
| d4poison | FAIL / false / Worker phase exited 3 | [0,0,0,1] | 4 distinct, pid 3818904 → 063e5232 | w3 `fault=on cvd=GPU-063e5232…`, injected + refusal ×2; w0-w2 `fault=off` | no |
| dpoison_both | FAIL / false / Worker phase exited 3 | [1,1] | 2 distinct | both injected + refusal; process rc 3 observed (`logs/i8c-mg-item12-both.log`) | no |

- Refused movies have no STAR: dpoison w1 A004, d4poison w3 A004, and dpoison_both w0 A002 and w1 A004. The worker logs have no `Written aligned` line for them.
- Process cleanup is complete in every arm, with no ownership errors.
- STAR identity d1 vs d2/dshim/d4 reproduces offline: `i8d_redigest.py` on the retained trees gives IDENTICAL.

Limit: **MRC identity and presence cannot be re-verified**, because the payloads were deleted (see (a) note 3). They are attested only by the i8c stage record (`summary/item12-dataset-regrade.json`): the d1 comparison covered 30 files including the MRCs, and only the 8 log/EPS files differed. They are also attested by the per-movie `Written aligned … .mrc` log lines. The packet's wording, "MRC and STAR were identical in-stage", is accurate.

## (d) Negative controls (built here)

`grader_controls.py` lifts `grade_dataset` and `digest_tree` by AST, so no QF or lane code runs. It grades private copies of the retained trees after rewriting the VM paths, and reconstructs MRC placeholders from the log `Written` lines. Mutants (`grader_controls.out`), each detected for the targeted reason:

- d4poison:
  - healthy w1 STAR deleted
  - w2 per-worker joint STAR deleted
  - w3 refusal removed
  - w3 published its refused movie
  - fault line injected on healthy w1
  - w3 `fault=on` changed to `off`
  - w2 rc 1
  - w3 rc 0
  - merged joint STAR present
  - dataset PASS / ready
  - graded with `fault_worker=0`: this fires the new "no 10641 movie" check
  - device order reversed
  - w3 console missing
- dpoison: tutorial movie before the faulting movie lost its STAR; healthy w0 lost an MRC.
- dpoison_both: refusal removed; verdict PASS.
- d4: merged STAR deleted; witness reports 3 distinct devices; w1 rc 1.
- dshim: counter does not match the retried patches.

Result: **21/21 detected**, and the unmutated baseline passes.

## Ingest-poison applied text (round-1 low items)

`tools-v3c-run` → `tools-v3d-run` (the repo copy, and the copy that ran `i8e-*`) applies all five items as described:

- **Single-line regex** (`c1_ingest_poison.py:41`): `re.S` was dropped. The native fault consoles carry the message on one line (`ingestCompressedTiffStrips:2066`).
- **Exact-empty witness** (:95).
- **Build-input pins** (`c1_ingest_build.sh:14-18`): fail closed.
- **Symbol check** (:38): `' T __wrap_cudaLaunchKernel'` replaces a grep that always matched.
- **`except Exception` in `grade`** (:213-215).
- **Healthy-arm refusal text** (:122): also changed in the same diff, to the reachable `Refusing CPU fallback`.

Tests: `test_c1_ingest_poison.py` passes 7/7 locally.

Mutants (`ingest_test_mutants.out`):
- Reverting the regex: a test fails.
- Reverting the witness check: a test fails. The two new tests can fail.
- Disabling the generic-exception handler: all tests still pass. The healthy-arm refusal-text change is also untested. Both are low severity: the handler is defensive and the healthy arms passed natively.

Native negative controls (`ingest-fault/result.json`): both reject at the first requirement, "fault did not execute exactly once". They show only that a run with no fault is rejected. The host mutants cover the other requirements.

## Files
- `grader_controls.py`, `grader_controls.json`, `grader_controls.out`: (a)-(d). Run as `python3 -I grader_controls.py <extracted tgz> <tools dir> out.json`.
- `ingest_test_mutants.sh`, `ingest_test_mutants.out`: ingest test suite and reverted-item mutants.
