# C1 CPU (cpu1d) and DC campaign harvest: draft grading report

Collected 2026-10-25 ~17:35-17:50Z, read-only, direct `ssh 4GPUs`. Nothing launched, built or written outside this directory.
No raw movie/MRC payload was rehashed or parsed. Parent verifies the interpretation. Nothing here is posted or pushed.
Every file below is under `/tmp/motioncorr-20261025-c1dc-harvest/`; `SHA256SUMS` covers every other file.

Sources: #282 `a406983b` (tested production source `e77a51a2`), cpu1d startup tree `t3-b50646d5` @ `520bd182`, DC #284 `fdf0c81b`.
C1 scratch: `SC=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb`.
DC root: `R=/mnt/clathrin/alex-motioncorr-dc-fourarm-20261022-3eee0a4b`, source `3eee0a4b`.
Notion plan not read: the notion MCP failed to start and `ntn` is not installed. Its content was taken from the #238 comment 6348535145, which says it mirrors it.

## 1. C1 CPU chain (cpu1d): complete, with a PASS verdict on the bounded rows it covers

| Item | Expected | Observed | Evidence |
|---|---|---|---|
| Frozen stages with `.exit` | 17 | 17, all `0` | `cpu1d_stage_receipts.txt` (started/finished per stage) |
| Wrapper/chain | exit+reaped receipts | `wrapper.exit`=0, `chain.exit`=0, `chain.reaped`, `chain-cpu1d.done` and `.finished` at 01:28:49Z; no `.stop` | `snap/c1/logs/` |
| Launch identity | one launch, binary `5692c6dc…` | wrapper 3311648 and chain 3311661 per the retained startup README; all 100 census `cpu.done.json` carry `binary_sha256` `5692c6dc…` | `snap/c1/img/*/cpu.done.json` |
| Prerequisite | 25 checks | 25/25 ok, `failed: []` | `cpu1d-prereq.json` sha `13fc3528…` |
| T24 CPU G, L vs frozen-F CPU | 24 MRC + 25 STAR per config | both `state: IDENTICAL`, `different_files=0`, 24 movies/24 MRC/25 STAR/341735520 px per arm. Run rc 0: G 658 s, L 1199 s, max RSS 2.84/2.95 GiB; same inputs, STAR sha `fb998f70…`, `--j 2`, CPUs 8-9. No timing claim. | `t24-cpu1d/compare/*.class.json` and `*.run.json`, `RUN.json` |
| Census (100 movies, 10 families x 10) vs retained CPU products | 100 | present 100, equal 100, missing/extra/different 0, errors `{}` | `census-cpu-vs-retained.json` sha `f6e4415e…` |
| Census decision (accepts 0, or 3 = INCONCLUSIVE) | n/a | **`verdict: PASS`**, exit 0 (not 3). Set problems empty, 10 control IDs, C1 == same-host F == retained on all 10 | `census-cpu-decision.json` sha `b8b3528f…` |
| Census metrics | 100 | 100 rows, all exit 0, `converged_lines` 0/0 on all. Mean field RMS 0.468 Å, max 5.79 Å (descriptive) | `census-cpu-metrics.json` sha `1cda2ddc…` |
| Image coverage | 100 `image.json` | 100 `cpu-none/image.json` (all schema `motion-image-truth/1`), 100 `cpu.done.json` (exit 0, `MC_DIAG_CCF_DC=none`, double 0). IDs equal the frozen `cpu1c-identities.json` `all` list, and each `movie_sha256` equals `receipt_movie_sha256[id]` (100/100). | `snap/c1/img/` |
| Image controls (dose1-s00) | truth=truth, oracle, zero, wrong-sign | truth-vs-truth transfer/FRC = 1.0; zero and wrong-sign collapse (FRC in-band 0.058 / 0.011) | `cpu1d-image-controls.json` sha `c9033d64…` |

The parent already verified the copied census/image reports independently. I did not repeat that and rely on the receipt `e9465b4b…`.

**Exit alone is not the grade for the v2/K267 stage.** `cpu1d-v2-check` exits 0 because C1 equals same-host F and the checker contract is valid. Per-row states inside it:

| Row | checker status | checker exit | sampling | field gate |
|---|---|---|---|---|
| zero | PASS | 0 | VALID | PASS |
| integer | FAIL | 1 | VALID | FAIL |
| fractional | FAIL | 1 | VALID | FAIL |
| affine | FAIL | 1 | VALID | FAIL |
| pedestal | FAIL | 1 | VALID | FAIL |
| noisy | FAIL | 1 | OUTSIDE_FIXED_ROI | FAIL |
| flat | UNIDENTIFIABLE | **0** | VALID | FAIL |
| repeated | UNIDENTIFIABLE | **1** | OUTSIDE_FIXED_ROI | FAIL |

Every row has `c1_equals_same_host_F: true`. `v2/cpu-unset.eval.json` and `v2/cpuF-unset.eval.json` are byte-identical (sha `0ec85a27…`).

- By checker status this CPU half is 1 PASS / 5 FAIL / 2 UNIDENTIFIABLE. Two backends give 2 / 10 / 4, which is the historical Tier A total, so it is unchanged.
- That match holds only for the checker-status column. The published cross-host record shows noisy and repeated as `ABORT_NO_RESULT`.
- Three rows have an exit that disagrees with the state: flat (exit 0, UNIDENT), repeated (exit 1, UNIDENT), noisy (FAIL with a non-VALID sampling status).
- A consumer that reads only the exit would mislabel two of these rows.

## 2. What this changes versus the older partial snapshot (RESULTS.md and #238 at 14:36Z 23 Oct)

- "T24 CPU arms UNRUN": now run. CPU G and L are IDENTICAL to frozen F (49/49 products in each config).
- CPU regression and census: PASS. The C1 CPU build reproduces the retained CPU products on 100/100 movies. This is a **Tier A CPU regression** claim only.
- CPU backend, truth and science stay separate:
  - Backend agreement: not applicable here, it needs CUDA arms.
  - Truth: unchanged, since C1 equals F on every v2 row, so the 1/5/2 pattern is inherited, not new.
  - Science (Tier D): none.
- Still unrun after cpu1d, so C1 engineering qualification stays incomplete:
  - CUDA/nvCOMP arms, W1 route witness, L attribution.
  - D12, K267/K269/K272 on CUDA, R12/R9, A1.
  - The old `t24/c1-ds-L` driver failure remains retained.
  - Item 12 / matrix directories are absent (parent confirmed).
- Static tooling precondition, not a run result: deployed `tools-v2.3-run/c1_item12.py` computes `HERE=Path(__file__).resolve().parents[3]/rc0/qf/tools`. That resolves to `/mnt/rc0/qf/tools` when relocated, but to `docs/rc0/qf/tools` in the repo. `c1_item.sh` sets Q but does not export PYTHONPATH. Smallest fix is an explicit `C1_SCR/src/docs/rc0/qf/tools` binding in a separate tooling iteration with an import-only check and an independent reviewer. R12/12ds have not run, so no native failure is claimed.

## 3. DC campaign (#262 four-arm): CPU queue finished, CUDA Tier C stopped, evaluation covers only 736 Tier B records

Queue `snap/dc/queue.json` (sha `7745d453…`) has 1700 IDs. RUN receipts: `dc_run_exits.txt` (sha `8b48deb2…`, 1403 lines).

| Tier | Backend | Queue | RUN.json | RUN exit | Evaluation |
|---|---|---|---|---|---|
| A | cpu / cuda | 40 / 40 | 40 / 40 | all 0 | `eval/A-summary.json` (sha `419807ce…`): 10 backend x arm entries, each `eval_exit` 0, 80 results (8 cases each) |
| B | cpu | 402 | 402 | all 0 | 334 in the frozen snapshot, **68 not evaluated** (all CPU) |
| B | cuda | 402 | 402 | all 0 | 402 in the frozen snapshot |
| C | cpu | 408 | 408 | all 0 | **0 evaluated** |
| C | cuda | 408 | 111 | all 0 | **0 evaluated**; 1 interrupted directory without RUN.json (`C-e12963-03-p3-cuda-both`, partial files at 21:39Z); **296 never ran** |

- Totals: 1403 RUN.json, all exit 0, none non-zero. 1404 run directories (1403 plus the orphan). 1700 − 1404 = 296 never ran. The 1403 RUN count and "1403 RUN0" in #238 match.
- Workers: `worker-cpu-10/11/12.exit` = 0 (09:14:05, 09:14:09, 09:14:52Z on 23 Oct). `worker-cuda-13.exit` = **137**: the parent stopped it at 21:39:57Z on 22 Oct for a foreign process on all four GPUs (`parent-resource-stop-20261022-2140/`). No `gpu-final-*.json` exists. This was a resource stop, not a native failure.
- Evaluated Tier B snapshot: 736 records (734 EVALUATED + 2 CONTROL_ONLY), taken 22:44:59Z on 22 Oct, evaluation finished 23:10:24Z. `EVALUATIONS.json` sha `4ec94412…`, `count=736` (345 reused + 391 new). It excludes the 68 CPU Tier B runs that finished later, and all of Tier C.
- Existing grades (older to newer):
  - `results/tierB.json` (20:45Z snapshot, 345 records): 80 rows, 240 pairs, **371** regressions.
  - Frozen pass-3 (736 records): 80 rows, 240 pairs, **878** per-seed regressions; reviewer-reproduced with 30 nominal improves, 1 nominal harm, 185 neutral/mixed, 12 IN_PROGRESS, 12 UNRUN. All 878 are retained and not collapsed.
  - The 878 count came from 736 records and will change if the 68 later CPU records are evaluated.
- No 1403-record terminal grade exists. Of the 1403 RUN receipts, 80 Tier A and 736 Tier B are evaluated, leaving **587 exit-0 runs with no terminal evaluation** (68 B-CPU, 408 C-CPU, 111 C-CUDA).
- Exit 0 means the native process ran. It is not a truth grade.
- DC CPU13 evaluator: terminated.
  - There is no `evaluate.py` or `matrix.py` process on 4GPUs at 17:42Z.
  - `/proc/3313212`, the evaluator child recorded in `evaluate-child.json`, is gone.
  - `evaluate.out` reaches its final line and `EVALUATIONS.json` was written at 23:10:24Z.
  - The "exit 0" comes from the retained pass-3 README, not from a host-side exit file. The host snapshot dir has no `evaluate.exit`.
  - No MotionCorr, `c1_*` or `taskset` process was found on 4GPUs, and nvidia-smi listed no compute apps. cpu64 had only an unrelated user's python jobs.
- Standalone DC summary v2.2 (`264be46c` / tested `070e3eab` / reviewed `4841c4ae`) has no caller in a campaign path. No full-campaign summary exists.

## 4. Existing-result conflict check (before any new job)

- `RESULTS.md` (T24 CPU arms UNRUN) is superseded by cpu1d. The prior cpu1c FAIL (24/25 checks, glob match of two launch dirs, 16 stages UNRUN) is retained and unchanged.
- #238's "1403 RUN0, DC workers exit 0" is true only for the three CPU workers. The CUDA worker is 137 with 296 never run.
- The `2/10/4` historical total reconciles with the C1 checker-status column (above). It does not reconcile with the published `ABORT_NO_RESULT` column. That is a labelling difference to state, not a new result.
- The 878 regressions in `results/` correspond to a newer snapshot than `results/tierB.json` (371). Both are retained.
- No source/hash conflict found between #238 and the remote stage receipts.

## 5. Smallest snapshot-only consumer (instead of a controller)

`tools/grade_snapshot.py SNAP STAGES RUN_EXITS` joins process exit, recorded state and evaluation presence from copied files only. Output: `grade_snapshot.out.json` (sha `01f6c19e…`).

- It lists the three exit/state disagreements (flat, repeated, noisy).
- It prints the 587 unevaluated exit-0 DC runs by tier and backend.
- The disagreement rule is a simple heuristic. It is not the reviewed v2.2 adapter.
- If a caller is wanted for DC, wire v2.2's two outputs (exit and state) into this join. Nothing else.

## 6. Limitations and minimal remaining work

- Limitations:
  - No raw payload rehash (census MRCs, DC runs, RUN/RECEIPT bytes).
  - DC original input digests are not independently audited (the retained `INPUT_VERIFICATION` lists IDs only).
  - Notion not read.
  - The cpu1d startup snapshot's process identities were taken from the retained README, not re-observed.
- Minimal remaining jobs, none launched or authorized here:
  - DC, no native: evaluate the 68 Tier B CPU records and the 408 Tier C CPU records on a CPU lane (the standard `tools/evaluate.py B|C`). This can be done snapshot-only if the campaign root is copied.
  - DC, native, needs an exclusive window: the 296 CUDA Tier C jobs plus the interrupted `C-e12963-03-p3-cuda-both`. Do not resume in place.
  - C1: the parent-owned CUDA/L/W1 arms. First fix the `c1_item12.py` path binding in a reviewed tooling iteration.
