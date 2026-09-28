# WORKER_STATUS — issue #94

| field | value |
|---|---|
| Issue | #94 bounded next-movie CUDA prefetch |
| Model | `claude-opus-5` (Opus 5, 1M context), high effort — no routing errors, no model substitution |
| Task class | implementation |
| Phase | 5/5 — implemented, reviewed, fixed, re-validated; draft PR open and current |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main) |
| Head | `c377404` (validated source `eb022aff151c11d939e2c39a5fc0b56da31ad431`) |
| Branch | `round96/94-claude-opus-5` |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-967d9ef6` |
| PR | https://github.com/KingAlejandro/MotionCorr-standalone/pull/108 (draft) |

## Changed files (matches the ADR whitelist)

| file | state |
|---|---|
| `src/movie_prefetch.h` | new — ByteBudget, BoundedQueue, shared loader, MoviePrefetcher |
| `src/movie_prefetch.cpp` | new |
| `src/motioncorr_runner.h` | 3 options, 1 method, widened `executeOwnMotionCorrection` signature |
| `src/motioncorr_runner.cpp` | producer wiring in `run()`, shared loader in the read path, stats |
| `CMakeLists.txt` | two test registrations |
| `tests/test_prefetch_lifecycle.cpp` | new |
| `tests/test_prefetch_equivalence.py` | new |
| `scripts/prefetch_gpu_screen.sh` | new — **prepared, unrun** |
| `tools/compare_prefetch_arms.py` | new — **prepared, unrun** |
| `agents/designs/issue_94_bounded_prefetch.md` | new — ADR |
| `docs/issue94_prefetch/` | evidence only |
| `WORKER_STATUS.md` | this file |

Nothing outside the whitelist. `WORKER_RESOURCE_UPDATE.md` (Alex's drop-in) was briefly staged
by a `git add -A` and has been removed from the commit; it stays untracked.

## Commits

| sha | kind | subject |
|---|---|---|
| `446194f` | docs | ADR, ownership model, worker status |
| `87eb53c` | feat | opt-in bounded next-movie decode, off by default |
| `572976d` | test | lifecycle, admission and serial-equivalence checks |
| `3ded007` | test | STAR path normalisation; budget cases made actually tight |
| `412f2f9` | chore | GPU screening script and paired arm comparison, not run |
| `1955238` | docs | CPU validation evidence with placement recorded |
| `d48dc91` | docs | draft PR and reviewers recorded |
| `c699a52` | docs | CUDA-branch syntax check against stub headers, with control |
| `189ed1f` | test | fix assertions that could not observe what they asserted |
| `23f5023` | docs | validation evidence incl. ThreadSanitizer |
| `eb022af` | fix | return budget bytes only after the buffers are actually freed |
| `c377404` | docs | validation evidence for the fixed head, superseded runs retained |

## Latest test commands and results

Host `small-refmac-machine` (ssh alias `cpu64`), 2026-09-28T00:33Z, source `eb022aff`.
Lane **`taskset -c 32-47`** (top-level, descendants inherit) under
**`flock /tmp/motioncorr-issue96-cpu-validation.lock`**, build `-j16`, runtime `<= 16`.
The old independent `/tmp/motioncorr-issue96-cpu.lock` is not used anywhere in this task.

```
cmake -S <src> -B build-release -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON   # rc=0
cmake --build build-release -j 16                                              # rc=0
ctest --output-on-failure -j 1                                                 # rc=0, 15/15
```

`CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp` (GCC 13.3.0, CMake 4.4.3).
`motioncorr` sha256 `9fda7ac231cc780ff1d2df68dd0ac6f60fae2d86d52c8a717cd3222be180873a`.

ThreadSanitizer, same lane, `OMP_NUM_THREADS=1` (libgomp is not TSan-annotated, so OpenMP
workers would bury a real finding; with one OpenMP thread the only concurrency left is the
producer alongside the consumer):

- `PrefetchLifecycle`: exit 0, **0 warnings**.
- Real serial and prefetched runs over 4 synthetic MRCs and 2 TIFF fixtures, so the actual
  readers run on the producer thread: both exit 0, **0 warnings each**, all **6 corrected
  images byte-identical**, none empty.

NUMA/placement observed, not inferred: inherited `Cpus_allowed_list=32-47`; `lscpu` shows 16
distinct physical cores on socket 1, no SMT siblings in the lane; `numactl --show` →
`cpubind 1, nodebind 1, membind 0 1`, so CPUs are node-local and **memory is not pinned** —
no NUMA memory-locality claim. Interference recorded and not altered: two unrestricted
`ctffind` at ~100% each (`Cpus_allowed_list=0-63`) plus other round workers.

Evidence: `docs/issue94_prefetch/` (run log, per-test stdout, CLI contract, CUDA syntax check,
and `superseded/` holding earlier heads' runs including two that record corrections).

## Active PID / job / allocation

None. The last cpu64 job finished at 2026-09-28T00:34:24Z and released the validation lock.
Staged trees and builds remain at `cpu64:~/mc-issue94/src-eb022aff151c/` (Release and TSan)
for re-checks.

## Blockers

None for the CPU deliverable. The GPU screen is gated on a slot, not blocked on a defect.

## NEEDS_GPU — prepared, **unrun**, awaiting explicit transfer

#26 remains the slot owner. `scripts/prefetch_gpu_screen.sh` **refuses to start** unless
`MC94_SLOT_GRANTED` names the assigning reference, and that check runs *before* it would queue
on the benchmark lock, so it cannot sit on the mutex by accident.

- **Purpose**: paired serial-vs-prefetch end-to-end screen on the 24 tutorial movies, plus
  exact same-backend comparison of every corrected payload, normalized header and STAR.
- **Resources**: shared `4GPUs`; top-level `taskset -c 96-111` (16 logical CPUs aggregate
  across all MotionCorr work); **one** GPU first, at most 2 idle devices later; build `<= 8`
  inside the lock; aggregate runtime/reader/helper threads `<= 16`; whole series under one
  `flock /tmp/motioncorr-bench.lock`; no competing benchmark.
- **Command** (the script re-execs itself under the lock; do not wrap it again):

  ```
  MC94_SLOT_GRANTED=<reference> scripts/prefetch_gpu_screen.sh \
      --binary <build-cuda>/motioncorr --star <tutorial>/movies.star \
      --outdir <scratch>/issue94_screen --gpu <idle-device> --pairs 3 \
      --threads 8 --cpus 96-111
  python3 tools/compare_prefetch_arms.py --root <scratch>/issue94_screen
  ```

- **Protocol built in**: settle gate *after* acquiring (`pgrep -x` by exact name, load1 < 2.0,
  wait logged); arm order alternating within each pair with the order label retained; 1 Hz
  continuous foreign-load sampling; 5 ms NVML VRAM sampling; per-run `Cpus_allowed_list`,
  `lscpu` topology, NUMA policy and GPU UUID recorded; complete per-arm outputs retained.
- **Separate arms, not merged**: a fixed-8 and a fixed-16 CPU-budget series are distinct runs.
  Extra CPUs will not be attributed to the code change.
- **Stop rule**: if 1-GPU screening shows no meaningful full-run improvement, the negative
  result is the deliverable and the complexity is not promoted. 2/3/4-worker schedules are
  attempted only if the 1-GPU screen is not negative.

## Subagents / reviewers — both complete, both acted on

Two bounded read-only reviewers (the round cap), neither able to write.

1. **Code/concurrency**: found one real defect — the record returned its byte reservation
   before freeing the decoded frames, because a defaulted destructor destroys members in
   reverse declaration order. That wakes a blocked producer mid-free, so real resident memory
   transiently reaches `limit + one movie` on a host sized to `limit`, and no counter can show
   it. Also: no top-level `catch` in the producer thread, `forced_grants` counting in-line
   loads rather than overrides, a degenerate geometry decoding off-budget, a lock inversion in
   `pop`, stats sampled before the join, and the libtiff warning-handler write. All fixed in
   `eb022af`. Reported clean: no deadlock or lost wakeup, no runner member reachable from the
   producer, serial-path behaviour identical line by line, `Iframes` aliasing sound.
2. **Spec-scope and license**: `SPEC_CONFORMANCE_PASSED`, `LICENSE_PASSED`. Found seven test
   assertions that could not observe what they asserted, and four evidence overstatements. All
   fixed in `189ed1f` and the docs commits.

Findings and fixes posted on #94 (issuecomment-5861326352) and PR #108
(issuecomment-5861326140).

## Progress comments

- #94 plan/ADR: issuecomment-5860965445
- #95 interface coordination: issuecomment-5860967217
- #94 PR/validation: issuecomment-5861175290
- #94 review findings and fixes: issuecomment-5861326352
- PR #108 review findings and fixes: issuecomment-5861326140

## Next step

Hold. The CPU deliverable is complete and the draft PR is current at `c377404`. The only
remaining work is the GPU screen, which waits on an explicit slot transfer from #26. No
merges, no default promotion, no GPU submission before then.

If the screen is eventually run and shows no meaningful full-run improvement, the negative
result is the deliverable: record it and do not promote the complexity.
