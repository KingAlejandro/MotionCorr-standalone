# #262 live-job handoff (2026-10-22T20:45Z)

Operational ownership of the detached campaign passes to the parent until the
author resumes in the same context. This is a scope split, not completion: the
four workers, their GPU2 lease and the frozen matrix keep running untouched.

## Live processes on 4GPUs

Root `R=/mnt/clathrin/alex-motioncorr-dc-fourarm-20261022-3eee0a4b`,
source `3eee0a4b4e367f9b57f950c440c89679a5ec9c93` (`$R/SOURCE_SHA`).

| Worker | Wrapper PID (`$R/worker-*.pid`) | Python child | CPU | Lock |
|---|---|---|---|---|
| cuda-13 | 3119381 | 3119383 | 13 | holds `/tmp/motioncorr-gpu2-correctness.lock` (GPU2 `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`) |
| cpu-10 | 3119417 | 3119420 | 10 | none |
| cpu-11 | 3119491 | 3119494 | 11 | none |
| cpu-12 | 3119582 | 3119584 | 12 | none |

Each wrapper writes `$R/worker-<kind>-<cpu>.exit` when its queue is exhausted
(0), on the 115 GiB cap (3) or on lock/GPU admission refusal (75); progress is
in `$R/worker-<kind>-<cpu>.log`. Each native process writes
`$R/runs/<id>/RUN.json` (argv, env, binary/input hashes, UUID witness, exit,
output hashes); a directory without RUN.json is in progress or orphaned and
must be reconciled, not rerun in place. The CUDA worker writes
`$R/gpu-final-<epoch>.json` when it releases the GPU2 lock.

Snapshot at 20:44Z: Tier A 80/80 exit 0; Tier B CUDA 264 + CPU 122 exit 0, 4 in
progress, 414 unrun; Tier C 816 unrun; runs 25 GiB; /mnt/clathrin 458 GiB free;
GPU2 one compute process (the worker's child), ECC 0. Expected remaining time
(unqualified): CUDA queue ~4 h, CPU queue ~8–10 h.

## One-shot status commands (read-only)

```sh
ssh -J ccp4-gateway -oBatchMode=yes 4GPUs "R=$R; cd \$R; date -u; cat worker-*.exit 2>/dev/null; tail -n1 worker-*.log | cut -c1-160"
ssh -J ccp4-gateway -oBatchMode=yes 4GPUs "R=$R; /home/alex/.mc-venv/bin/python3 -B \$R/tools/evaluate.py status \$R"
ssh -J ccp4-gateway -oBatchMode=yes 4GPUs "R=$R; grep -l '\"exit\": [1-9]' \$R/runs/*/RUN.json; ls \$R/runs/*/ADMISSION_FAILED 2>/dev/null; du -sh \$R/runs; df -h /mnt/clathrin | tail -1"
ssh -J ccp4-gateway -oBatchMode=yes 4GPUs "nvidia-smi --query-gpu=index,uuid,memory.used,ecc.errors.uncorrected.volatile.total --format=csv,noheader; lslocks -o PID,COMMAND,PATH | grep motioncorr"
```

## Pending evaluation (author follow-up; not started by this handoff)

Run on 4GPUs with `/home/alex/.mc-venv/bin/python3 -B`, `OPENBLAS_NUM_THREADS=1`,
`nice -n 10 taskset -c 13`, from `$R`:

1. `tools/evaluate.py B $R` — evaluates only new Tier B records; 345 done
   (passes 1 and 2, logs `eval-B-1.log`, `eval-B-2.log`, both clean).
2. `tools/evaluate.py C $R` — after all Tier C records exist.
3. `tools/evaluate.py controls $R final` — writes `eval/controls-r2-final.json`
   (includes the two Tier B plain controls); never overwrites.
4. `tools/matrix.py $R eval/matrix-final.csv` — all 1700 rows with status.
5. Locally: `tools/summarize.py EVAL_DIR results/` regenerates `tables.md`.

Safe completion criterion: all four `worker-*.exit` files exist with 0, no
directory under `runs/` lacks RUN.json, `gpu-final-*.json` shows GPU2 idle with
ECC 0, and the GPU2 lock is no longer listed. Any nonzero exit, admission
failure or cap stop is retained and reported, not retried in place.

## Evaluator identities

| Script | SHA-256 | Use |
|---|---|---|
| `tools/evaluate-original-b20bff53.py` | `b20bff53...72a` | produced `eval/A-*.json`; original controls rule (replayed) |
| `tools/evaluate-interim-abd1aec1.py` | `abd1aec1...b5d6` | produced the current `eval/controls.json` (`5da1f914`, path-only labelled IDENTICAL; kept unchanged) |
| `tools/evaluate.py` (r2) | `dcc5ddb3...e14d` | Tier B passes, `controls-r2-tierA.json`, all pending steps |
| `tools/campaign.py` | `8701cf24...eae` | workers, queue (`queue.json` `7745d453...a4da`) |
| `tools/matrix.py` | `6598d105...07a8` | evidence matrix |

## Local observers stopped by this handoff

Four read-only local waiters were stopped after checking their commands; none
launched, signalled or locked remote work: `biocg6rko` (local PID 82266,
`ssh ls RUN.json | wc` until-loop plus one `evaluate.py status`), `bbn08h0ws`
(83753), `boimt3wpi` (24394) and `bsej7er57` (25999) (each waited on a local
output file and `cat` it). The evaluator pass 2 (remote PID 3200867, carried
by local task `b0bxc31pt`) was allowed to exit normally first.

## Worktree

Branch `experiment/262-four-arm-20261022` in
`/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-6c79c479`; not pushed.
Iteration-1 scratch `/mnt/clathrin/alex-motioncorr-dc-fourarm-20261022-59ff5811`
(builds and Phase 0, 458 MiB) is retained.

## Update 2026-10-22T21:59Z

The CUDA worker (wrapper 3119381, coordinator 3119383) was stopped by the parent
at 21:40Z for foreign GPU occupancy; `worker-cuda-13.exit` is 137 and no CUDA
worker is running. Its GPU2 lock is no longer held. CPU workers 3119420,
3119494, 3119584 continue. The completion criterion above now applies to the
CPU queue only; the CUDA queue remains incomplete until an approved resume (see
`resource_stop_20261022/README.md`).
