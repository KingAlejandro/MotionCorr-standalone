# GPU2 resource stop, 2026-10-22 21:40Z, and proposed GPU resume (UNRUN)

## What happened

A foreign `llama-server` (PID 3276184, another user) opened contexts on all
four GPUs. On GPU2 it first appears between 21:25:51Z (last clean recorded
snapshot) and 21:26:02Z (first snapshot showing it), and it is present in every
later snapshot. The campaign's CUDA worker checked occupancy only at worker
start, so it kept launching. The parent stopped only that worker (coordinator
PID 3119383, UID 1004, start ticks 815401887, exact argv checked): SIGSTOP, the
running child finished on its own, then SIGKILL of the stopped coordinator;
wrapper exit 137. The foreign process was not signalled. The CPU workers
(3119420, 3119494, 3119584) were not touched. Exact receipts, byte-copied and
hash-checked against the remote originals: [receipts/](receipts/) ([INDEX](receipts/INDEX.json)).

## Records affected

- [incomplete-runs.json](incomplete-runs.json): `C-e12963-03-p3-cuda-both` is
  **INTERRUPTED/INCOMPLETE**. Its child finished (`time -v` exit status 0) and
  products exist, but the stopped coordinator never wrote `RUN.json`. It is not
  EXIT0, not evaluated, never PASS and never rerun in place. The three
  `B-dose05-s04-cpu-*` directories in the same scan belonged to live CPU workers.
- [gpu2-foreign-overlap.json](gpu2-foreign-overlap.json): **54** completed CUDA
  records (`C-e10216-07-p5-cuda-global` to `C-e12963-03-p3-cuda-local`) have the
  foreign process on GPU2 before and/or after their own process
  (`FOREIGN_OBSERVED`). Snapshots exist only immediately before and after each
  process, so occupancy during a run is not observed. ECC stayed 0. All 54
  exited 0. This is resource metadata only: no RUN.json, exit status or
  scientific category is changed, and no new endpoint was evaluated.
- No `gpu-final` receipt exists: the coordinator was killed before its cleanup
  block. Its flock was released by the kernel at process exit.

## Review R2, owner collision and worker v4 (2026-10-23)

Review R2 ([review-r2/REVIEW.md](review-r2/REVIEW.md), verbatim) found a Linux-only material defect
in v3 (R2-M1: the worker's own new-session `nvidia-smi` queries would be adopted as owned on Linux) and
moderate gaps. v3 stays frozen and must not be deployed. The proposed successor is
`tools/gpu_worker_v4.py` (`071a1588…`); responses in [review-r2/RESPONSES.md](review-r2/RESPONSES.md).
During the v4 control runs orphan copies of the author session ran concurrently; see
[collision_20261022/](collision_20261022/README.md) for the inventory, recovery actions and attempt
trust. The one authorized fresh attempt in [gpu_worker_v4_controls-r2/](gpu_worker_v4_controls-r2/README.md)
was refused by its runner and is UNRUN. v4 is not deployed and has not run on Linux; a fresh
independent review comes before any Linux host mock. Namespace-aware evaluation stays unimplemented
and evaluation of any resumed namespace is blocked.

## Review R1 and worker v3 (2026-10-22)

Independent review R1 ([review-r1/REVIEW.md](review-r1/REVIEW.md), verbatim)
found five material defects (M1–M5) and moderate gaps (m6–m12) in v2. v2 and
its controls below are kept unchanged as the reviewed version but **must not be
deployed**. The proposed successor is `tools/gpu_worker_v3.py`
(`a0510eaa…c106c9`); finding-by-finding responses are in
[review-r1/RESPONSES.md](review-r1/RESPONSES.md) and its host mock controls in
[gpu_worker_v3_controls/](gpu_worker_v3_controls/README.md) (final harness
`73735e79…`: 22/22 PASS; 9/9 mutants rejected). v3 is not deployed and has not
run on Linux; a fresh review comes before any Linux host mock or deployment.
Namespace-aware evaluation/matrix support is not implemented, so evaluation of
any resumed namespace is blocked until a reviewed reader exists.

## Successor worker (proposed, not deployed)

[`tools/gpu_worker_v2.py`](../tools/gpu_worker_v2.py) (SHA-256 `610dca3b…98f`)
checks UUID/index, ECC and foreign compute processes before every launch,
samples the target GPU during each job, stops before the next launch after any
foreign process or post-job health problem, runs each job in its own session,
and signals only process groups re-verified as owned through
`tools/multi_gpu/process_ownership.py` (`8de59b8c…`, unchanged). It writes a
TIMEOUT/CANCELLED record, never a success, and releases the GPU lease only after
verified cleanup; otherwise it writes `CLEANUP_FAILED_LEASE_HELD` and keeps the
lease. Existing job directories are reported PRESERVED_EXISTING and never
touched. `campaign.py`, the native source `3eee0a4b`, the frozen queue and all
records are unchanged.

Host controls ([gpu_worker_v2_controls/](gpu_worker_v2_controls/),
`tools/test_gpu_worker_v2.py` `52b05104…`, macOS, Python 3.13.7, fake
`nvidia-smi`, mock jobs, no GPU or motioncorr):

| Control | Result |
|---|---|
| C1 foreign process before first launch: no launch, lease released | PASS |
| C2 nonzero ECC / C3 failed query / C3b wrong index: no launch | PASS / PASS / PASS |
| C4 clean two-job queue, the job's own GPU process not treated as foreign | PASS |
| C5 foreign appears mid-job: job recorded with it, stop before next launch | PASS |
| C6 existing incomplete directory untouched and skipped | PASS |
| C7 timeout / C8 SIGTERM: job tree including a `setsid` grandchild reaped, record kept, independent same-user sentinel not signalled, lease released | PASS / PASS |
| Mutant without occupancy checks | rejected: C1, C5 FAIL |
| Mutant without group signals | rejected: C7, C8 FAIL (worker holds the lease, as designed) |

Limits: macOS uses the helper's polling mode; Linux child-subreaper adoption
and real `nvidia-smi` behaviour are not exercised by these controls. The first
control run found and fixed one worker defect (an exited, unreaped own job was
classed as foreign), and the first no-signal mutant run crashed the harness on its wait timeout instead of recording FAIL rows; the harness now records that case and also checks the `setsid` grandchild. Those earlier runs are not retained as separate files.
While cleaning up after the first mutant run I ran a name-based
`pkill -f "sleep 300" -U <uid>` on the Mac; it may have matched unrelated
`sleep 300` processes of the same user there. It did not touch 4GPUs.

## Proposed GPU resume (UNRUN; needs an exclusive GPU lane and independent review)

- Preconditions: a coordinated exclusive GPU lane; independent review of
  `gpu_worker_v2.py` and this proposal; a Linux host-only mock run of
  `test_gpu_worker_v2.py` on 4GPUs (CPU only, no GPU) to cover the subreaper path.
- Queue [proposed-resume-gpu-r2.json](proposed-resume-gpu-r2.json)
  (`80120b7c…`): the 297 CUDA entries of the frozen `queue.json` (`7745d453…`)
  without a `RUN.json` at the stop, in frozen order: 296 unrun and the
  interrupted `C-e12963-03-p3-cuda-both`.
- Optional contention replicate
  [proposed-contention-replicate-gpu-r2.json](proposed-contention-replicate-gpu-r2.json)
  (`081b3b97…`): the 54 FOREIGN_OBSERVED jobs. Originals are kept; MRC core
  header, payload, movie STAR and runtime model are compared byte-for-byte, and
  any difference keeps both records and is reported.
- Output: fresh `$R/runs-gpu-r2-<UTC date>/`, same binaries
  (`binaries.json` `28d84f5d…`), same argv, GPU2 by UUID (or the lane Alex
  assigns, recorded), `--cpu 13`, `--job-timeout 3600`. Old `runs/` directories,
  including the interrupted one, stay as they are. Evaluation reads both
  namespaces and records which one each row came from.
- ~~Command once approved (v2)~~: superseded by review R1; do not use v2.
- Null replicate required before any contention attribution (m12):
  [proposed-null-replicate-gpu-r2.json](proposed-null-replicate-gpu-r2.json)
  (`39fd2c0f…`), the 57 CUDA Tier C jobs that ran before the foreign onset with
  clean GPU2 snapshots. If their replicate is not byte-stable, no difference in
  the 54-job replicate can be attributed to contention. The comparison tool does
  not exist yet. UNRUN.
- v3 command shape, only after review, an exclusive lane and a Linux host mock.
  Copy the proposal file to `$R/resume-gpu-r2/` and verify its hash; copy
  `tools/multi_gpu/process_ownership.py` (`8de59b8c…`) beside the worker as
  `$R/tools/multi_gpu/process_ownership.py`:
  `python3 -B $R/tools/gpu_worker_v3.py --root $R --queue $R/resume-gpu-r2/proposed-resume-gpu-r2.json --queue-sha256 80120b7c5136f855908e408d8ef9776b37775369ce0e42b02b0b4d5ae7e69cd1 --expected-jobs 297 --binaries $R/binaries.json --binaries-sha256 28d84f5d09ba58ffdf065db002737a8125a0ad7c8abd4db8eb832e09d1ecb7e9 --runs-dir $R/runs-gpu-r2-<UTC date> --uuid <assigned UUID> --gpu-index <its index> --cpu 13`
  (lease `/tmp/motioncorr-gpu<index>-correctness.lock` is derived from the index).
  The 54-job and 57-job replicates would each be a separate invocation with its
  own fresh namespace, hash and expected count.
