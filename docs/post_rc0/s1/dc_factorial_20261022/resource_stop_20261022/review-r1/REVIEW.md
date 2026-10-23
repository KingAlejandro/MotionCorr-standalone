# Independent review R1: #262 GPU resource stop packet and gpu_worker_v2 (proposed)

Target `e84ea024c31df097d4223f6c9ffb447d5d10a219` (`experiment/262-four-arm-20261022`), reviewed in a
detached isolated worktree (clean index, HEAD verified equal to the author worktree HEAD). Author
worktree not modified. No SSH, GPU, native, build or remote action. One host mock run on macOS.

Scope: `docs/post_rc0/s1/dc_factorial_20261022/resource_stop_20261022/**`,
`docs/post_rc0/s1/dc_factorial_20261022/tools/gpu_worker_v2.py` (`610dca3b…f98f`),
`.../tools/test_gpu_worker_v2.py` (`52b05104…07a8`); context read: `.../tools/campaign.py`
(`8701cf24…eae`), `tools/multi_gpu/process_ownership.py` (`8de59b8c…08cb`),
`tools/multi_gpu/run_multi_gpu.py::_terminate_process_groups`, `tools/matrix.py`, `src/experiment_ccf_dc.h`.
(The brief's `tools/{gpu_worker_v2.py,test_gpu_worker_v2.py}` are under the docs packet's `tools/`.)

## Verdict

- Resource-stop evidence packet: **acceptable**, minor notes only.
- `gpu_worker_v2.py`: **5 material findings (M1–M5)**. Not ready for GPU deployment.
- Linux host-only mock on 4GPUs: **ready after a small fix round** covering M1–M3 and the harness
  cleanup in m10, with controls for each. Running the current harness on a shared host is not
  advised because its fallback cleanup SIGKILLs PIDs without a birth-identity check.

## Verified (no finding)

- Local receipts byte-equal to originals: `stop_own_dc_gpu_worker.py` `11fef8c1…`,
  `dc-gpu-resource-stop-2140.json` `d137f1a2…`, `resource-conflict-preflight-2137.json` `7d9a9e9c…`.
  The three remote receipts (`pre` `df2f76d8…`, `coordinator-stopped` `4b854383…`, `post` `10c97168…`)
  match `receipts/INDEX.json`; the reviewer could not re-hash the remote originals (no SSH allowed).
- Stop script acted only on exact PID 3119383 with UID 1004, start ticks 815401887 and exact argv;
  `post.json` shows a single SIGKILL to that PID, no SIGTERM to children (child finished on its own),
  foreign PID 3276184 not signalled, CPU workers 3119420/3119494/3119584 alive.
- `incomplete-runs.json`: `C-e12963-03-p3-cuda-both` is INTERRUPTED/INCOMPLETE, `time -v` exit 0 is
  recorded as unadmitted, not EXIT0/PASS, not rerun in place. The three `B-dose05-s04-cpu-*` rows are
  marked IN_PROGRESS for live CPU workers, not interrupted.
- `gpu2-foreign-overlap.json` is internally consistent: 553 CUDA RUN.json = Tier A 40 + Tier B 402 +
  Tier C 111; 107 nonempty GPU2 snapshots = 53 before + 54 after; the 54 records are the contiguous
  CUDA Tier C positions 57–110 (`C-e10216-07-p5-cuda-global` … `C-e12963-03-p3-cuda-local`), all
  `FOREIGN_OBSERVED`, all exit 0, ECC 0. The packet states the before/after-only limit and does not
  claim during-run occupancy.
- `proposed-resume-gpu-r2.json` (`80120b7c…`): 297 entries, no duplicates, all `cuda`/`C`/`cuda-exp`,
  `--gpu 0 --ingest auto`; id order equals positions 111–407 of the CUDA Tier C order reconstructed
  from the committed `campaign.build_queue` (first = the interrupted job, then 296 unrun).
  `proposed-contention-replicate-gpu-r2.json` (`081b3b97…`) ids equal the 54 affected records in order.
  Limit: frozen `queue.json` (`7745d453…`) is not committed, so entry bytes were checked against the
  generator logic, not against the remote queue file.
- Commit touches only `docs/post_rc0/s1/dc_factorial_20261022/`; `campaign.py` unchanged since
  `b427037f`; `src/` unchanged since `3eee0a4b`; `tools/multi_gpu/` identical to #273 `805d9de2` and
  main `36913740`. No RUN.json or run data are in the commit.
- The Mac `pkill -f "sleep 300" -U <uid>` incident and the non-retention of the pre-fix control runs are
  disclosed in the packet README without invented outputs.
- Licence: new files `SPDX-License-Identifier: GPL-2.0-or-later`, stdlib only, importing in-repo
  GPL code; compatible with the repository's GPL-2.0.
- Reproduction: `test_gpu_worker_v2.py` 9/9 PASS with the same worker/test hashes (receipt
  `controls-review.json`, launch record `controls-review-launch.json`: PID 72789, UID 502, own
  session, 12.2 s, exit 0; post-run scan found no leftover mock/sentinel/`sleep 300` processes).

## Material findings

**M1. Unbounded `p.wait()` makes in-job cleanup failure hang without any record**
(`gpu_worker_v2.py:184-186`, with `terminate_owned:104-115`).
Scenario: timeout or SIGTERM while the ownership observer has an error (`own.errors` non-empty, e.g.
an unreadable owned identity) or `verified_group` fails. `terminate_owned` refuses every signal, waits
5 s on the root, appends an error, and returns; `run_job` then calls `p.wait()` with no timeout and
blocks forever. No RUN.json, no `CLEANUP_FAILED_LEASE_HELD` receipt, and the `finally` block is never
reached. The lease is held, but with no evidence of why. The author's own `mutant-no_kill.json` shows
exactly this (`"receipts": []`, worker still running at 60 s). Related: exit code 5 is unreachable
(`signal.pause()` loop at :254 never returns; SIGTERM only sets `cancel`), and the main loop never
checks `own.errors` / `own.is_alive()` before a launch, so a dead observer is discovered only when
cleanup is needed. Fix: bounded wait; on failure write RUN.json `CLEANUP_FAILED` plus the lease-held
receipt; refuse launch if the observer has errors or has stopped; add a control that injects an
observer error and asserts the receipt.

**M2. Exceptions after `mkdir` or in the admission query leave an orphan directory and a FINAL
receipt with `code=0`** (`:138-152`, `:231`, `:249`).
Scenarios: `nvidia-smi` exceeds the 30 s timeout (`TimeoutExpired`), malformed compute-apps row
(`int(...)` `ValueError` at :73), `campaign.admit` hash mismatch (`RuntimeError`) or missing input
(`OSError`), `own.refresh()` failure at :188, or `FileExistsError` from a concurrent worker at :138.
Each propagates out of the loop; `finally` writes `FINAL` with `code` still 0, releases the lease, and
then the process exits 1 with a traceback. No STOP receipt; the job directory (if created) has no
RUN.json. The docstring's "any failure, including an unreadable query, stops before launch (exit 75)
with a STOP receipt" holds only for a nonzero `nvidia-smi` exit. Conversely, if only the FINAL
`smi.query()` (:249) times out, the worker writes `CLEANUP_FAILED_LEASE_HELD` and pauses forever even
though cleanup and `restore()` succeeded. Fix: catch per-stage, write STOP/RUN.json with the
exception, set a nonzero code before `finally`; separate final-health failure from cleanup failure.

**M3. Silent expected-count reduction through PRESERVED_EXISTING** (`:226-228`, `:159-163`).
Any existing directory is skipped and the queue still ends with exit 0 ("queue done"), whatever it
contains. The worker itself creates such directories: `NOT_LAUNCHED` (pre-launch recheck), `TIMEOUT`,
`CANCELLED`, `EXITED_WITH_OWNED_SURVIVORS`, and M2 orphans. Re-invoking on the same `--runs-dir` after
a 75 stop therefore never runs those jobs and reports success; only the `preserved_existing` list in
FINAL reveals it. Fix: at the end, classify every queue id (EXITED / other status / no RUN.json /
absent) and exit nonzero unless all are `EXITED`; or require a new namespace per invocation and
refuse a non-empty `--runs-dir`. Add a control that resumes after a NOT_LAUNCHED stop.

**M4. Queue and binary binding are not enforced or recorded** (`:210-213`, `:142-148`; README
"Command once approved").
The worker runs every entry in `--queue` with no backend filter (unlike `campaign.worker`) and appends
`--gpu 0` and the GPU2 `CUDA_VISIBLE_DEVICES` to all of them. The README command reads
`--queue <frozen queue>`; if an operator passes the frozen `queue.json` (`7745d453…`) instead of the
297-entry proposal, v2 would launch every Tier A/B/C job, including `cpu-*` builds with CUDA
settings, into the fresh namespace. Neither the queue path/hash, `binaries.json` hash nor expected job
count is checked or written to RUN.json/FINAL. Fix: require `--queue-sha256` and `--expected-jobs`,
assert all entries are `cuda`, record queue and binaries hashes in every RUN.json and receipt, and name
the exact proposal file in the README command.

**M5. RUN.json drops the route witness and breaks the existing tooling** (`:153-158`, `:194-201`).
v2 records omit `gpu_witness_uuids` (campaign.py's sampled UUIDs on which the job's own descendants
appeared), `host` and `bench_lock`. The job's own presence on the target UUID is therefore not
witnessed; only the absence of foreign PIDs is. `tools/matrix.py:31` reads `r['gpu_witness_uuids']`
(KeyError) and `r['exit']` (absent in NOT_LAUNCHED), and `matrix.py`/`evaluate.py` read only
`ROOT/runs`. The README's "evaluation reads both namespaces" is not implemented. Fix: restore the
route witness and provenance fields with the original names; add an explicit status column and a
namespace-aware reader before any r2 data are evaluated.

## Moderate findings

- **m6. Mid-job sampler cannot show it observed anything** (`:168-177`). `st, _ = self.smi.query()`
  discards `problems`; a failing mid-job query yields `target_pids=[]` and looks like a clean sample.
  No sample count or failure count is recorded, so `foreign_on_target_during: {}` cannot distinguish
  "sampled clean" from "never sampled". Also `th.join(15)` is shorter than the 30 s query timeout, so a
  sampler still running can mutate `foreign` while RUN.json is being serialised. Record
  samples/failures and join after the query timeout.
- **m7. Cancel during admission still launches one job.** SIGTERM arriving during the main-loop or
  `run_job` query (up to 60 s) is checked only after `Popen` (:181). Check `cancel` immediately
  before `Popen`.
- **m8. `owned_pids` ignores birth identity** (`:87-90`). Keys of `identities` include long-exited
  PIDs; a foreign process that reuses one is treated as owned and hidden from the foreign check. Use
  `known_live()` identities. Low probability on 4GPUs, but the guard is cheap.
- **m9. Hung `nvidia-smi` in uninterruptible sleep** is not handled: `subprocess.run` kills and then
  waits without bound. The fake SMI only exits 9; no hang control exists. State it as a limitation or
  run queries in a bounded helper.
- **m10. Harness cleanup and mutant evidence** (`test_gpu_worker_v2.py`).
  (a) The timeout fallback (:183-188) SIGKILLs PIDs from `own.txt`/`tree.json` without a birth-identity
  check; macOS PIDs wrap at 99,999. Use `ProcessTable` identities recorded at creation.
  (b) Non-timeout FAIL paths (:193-202) and the `subprocess.run(timeout=120)` crash path (:99) leave
  mock descendants (`sleep 300`) running. That is the situation that led to the manual `pkill`. Every
  exit path should reap the control's own processes by verified identity.
  (c) Mutant sources (`62074b3e…`, `414f8f89…`) are not committed, so the rejection results cannot be
  reproduced. Commit the two patches.
  (d) The sentinel runs in its own session and is never a candidate group, so "sentinel not signalled"
  cannot fail. The worker's own-group exclusion (:97, :101) is uncovered. A sentinel in the worker's
  process group would test it.
- **m11. Production prefix untested.** Controls use `--prefix ''`; production uses
  `taskset … /usr/bin/time -v`, so the GPU process is a grandchild. Classifying it as owned before the
  first sample sees it is a race that can produce a false foreign stop (safe, but it would halt the
  resume). Run the Linux mock with a `/usr/bin/time` prefix.
- **m12. Contention replicate lacks a null.** A byte comparison of the 54 replicated jobs cannot
  attribute a difference to contention until CUDA run-to-run byte stability is shown on jobs that had
  no foreign occupancy (e.g. a sample of Tier C positions 0–56 or Tier B). The comparison tool does
  not exist yet.

## Minor

- `incomplete-runs.json` has no scan UTC (only `scan_utc_note`).
- ECC `[N/A]` is accepted as clean (inherited from campaign.py); on A100 with ECC enabled, `[N/A]`
  would mean the query is not reporting ECC.
- `--lock` is not cross-checked against `--gpu-index`.
- Continuous `nvidia-smi` polling every 0.25 s perturbs job wall time. Records already say
  `wall_s_unqualified`, but v2 must not be used for timing.

## Readiness

- GPU deployment / resume: **not ready** (M1–M5; plus the exclusive lane, which is not this review's
  decision).
- Linux host-only mock on 4GPUs: run after fixes for M1–M3 and m10(a,b), with new controls for
  observer error during timeout, admission exception, resume after NOT_LAUNCHED, and a `/usr/bin/time`
  prefix. M4/M5 can land in the same round. The existing nine controls and two mutants are proposal
  evidence on macOS polling mode only. They do not qualify the Linux subreaper path, real
  `nvidia-smi`, or native/GPU behaviour.

## Reviewer actions and limits

- Commands: `git checkout --detach e84ea024…` in the supplied worktree; static reads; `shasum -a 256`
  of receipts/proposals; Python consistency checks over the committed JSON; one run of
  `/Users/alex.konstantinov/.local/bin/python3 -B test_gpu_worker_v2.py --json …` through
  `run_controls.py` (own session, 420 s bound, identity-checked group signal only on timeout; not
  needed). Mac load average ~5 on 14 CPUs at launch.
- Not done: remote hash re-verification, Linux execution, any GPU/native/build action, mutant
  re-execution (sources not committed).
