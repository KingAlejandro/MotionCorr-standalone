# WORKER_STATUS — issue #94

| field | value |
|---|---|
| Issue | #94 bounded next-movie CUDA prefetch |
| Model | `claude-opus-5` (Opus 5, 1M context), high effort — no routing errors, no model substitution |
| Task class | implementation |
| Phase | COMPLETE — implemented, reviewed twice, fixed, CPU- and GPU-validated. Verdict: **no-go on promotion**, prefetch stays opt-in. |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main) |
| Head | `2644a30` (source under GPU test `ab9cd6b9a3ee5c2f0de11a623d849dc921a71448`) |
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

## GPU — three dedicated SCARF allocations, all released

Per Alex's 28 Sep parallel-GPU authorisation (#96 issuecomment-5864906904). **No shared-VM
resource and no `/tmp/motioncorr-bench.lock` taken or queued on**: #53 keeps GPU0/1 with CPUs
96-111, #69 has GPU2 with 112-119, GPU3 left free.

| job | CPU budget applied | elapsed | state |
|---|---|---|---|
| 3511120 | — | 00:00:10 | FAILED: `module load` piped into a subshell, so cmake found no `nvcc` |
| 3511123 | — | 00:00:12 | FAILED: login profile exports a nonexistent `TMPDIR` |
| 3511125 (A) | 8 logical / 4 physical, NUMA node 0 | 00:15:42 | COMPLETED |
| 3511134 (B) | **1 logical** — submitted as "cpu16"; `sbatch --export` splits on commas. Relabelled. | 00:24:15 | COMPLETED |
| 3511138 (C) | 16 logical / 8 physical, NUMA nodes 0+1 | 00:14:13 | COMPLETED |

All released. Each `--exclusive`, so each held the whole 64-CPU 4×A100 node for one GPU and
≤16 CPUs — ~54 min of whole-node occupancy, taken because timing on a shared host is not
defensible. Node `gn3000`, GPU `GPU-c6c43d6a-aa2e-af46-022c-aa4a4735638d`.

**Correctness, all three series:** 72/72 MRC payloads, 72/72 normalized headers, 25/25 STAR
artifacts, 2 759 049 984 bytes of pixels, 0 failed movies, `decoded=24 inline=0 failed=0
over_budget_grants=0`. Correctness ran before timing and the job exits without timings if the
arms disagree.

**Timing:** prefetch faster in **0 of 9 paired blocks**; mean −3.44 s (A), −10.15 s (B),
−2.39 s (C) on runs of 103/171/100 s. Series not combined into one curve.

**Host RSS:** 2.97 → 5.51 GiB, **+2.55 GiB / +86%** in every series, spread 5-13 MiB across
nine runs. Device memory unchanged at 3497 MiB.

**Mechanism:** `consumer_wait_s` 0.3-5 s against `producer_queue_blocked_s` 81-95 s. The decode
is fully hidden; it was never what the wall clock waited for.

**ADR estimate validated:** `budget_bytes = 3 × 1822785536`, and the §5 formula for
3710×3838×24 with 8 IO threads gives exactly 1822785536. `peak_reserved == budget` in every
prefetched run.

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
- #94 Codex fixes + negative controls: issuecomment-5864955036 (PR: 5864954787)
- #94 GPU result / no-go: issuecomment-5865942956 (PR: 5865942642)
- #66 roadmap report: issuecomment-5865947621

## Verdict

**No-go on promotion.** The feature is correct and its bound behaves exactly as specified, but
it buys no measurable full-run time at any of three CPU budgets and costs +86% host RSS every
time. Per the issue's own stop rule, the negative result is the deliverable: `--prefetch` stays
opt-in and off by default on every backend.

## Next step

Nothing outstanding. Awaiting `@codex` re-review of PR #108 (requested at the review-fix push).
No merges, no closures, no default promotion.

Still UNRUN and stated as such: the composed PR103/PR110 integrity work (a merge this task is
not authorised to make; a later bounded composition), multi-worker schedules, EER and
compressed-MRC through the prefetch path, budgets wider than 16 CPUs, NUMA memory pinning,
`nsys` transfer counts, and ThreadSanitizer at the current head.
