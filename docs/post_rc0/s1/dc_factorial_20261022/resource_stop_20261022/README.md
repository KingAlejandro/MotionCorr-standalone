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
- Command once approved:
  `python3 -B tools/gpu_worker_v2.py --root $R --queue <frozen queue> --runs-dir $R/runs-gpu-r2-<date> --binaries $R/binaries.json --cpu 13 --uuid <UUID> --gpu-index <n> --lock /tmp/motioncorr-gpu<n>-correctness.lock`
