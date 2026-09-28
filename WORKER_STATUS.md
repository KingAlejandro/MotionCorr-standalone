# WORKER_STATUS — issue #94

| field | value |
|---|---|
| Issue | #94 bounded next-movie CUDA prefetch |
| Model | `claude-opus-5` (Opus 5, 1M context), high effort — no routing errors, no model substitution |
| Task class | implementation |
| Phase | 6/6 — review fixes landed and re-validated; dedicated SCARF GPU allocation running |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main) |
| Head | `ab9cd6b` (validated source `08c87bb653a3970639dd0699eaa479eb2fc795a9`) |
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

## GPU allocation — DEDICATED SCARF, acquired 2026-09-28T06:58Z

Per Alex's 28 Sep authorisation (#96 issuecomment-5864906904, #66
issuecomment-5864920453): threads no longer queue behind #53. This task took a **separate
dedicated SCARF Slurm allocation** and touched **no** shared-VM resource — #53 keeps GPU0/1
with CPUs 96-111, #69 has GPU2 with 112-119, GPU3 stays free for colleagues. No
`/tmp/motioncorr-bench.lock` was taken or queued on.

| field | value |
|---|---|
| Cluster | SCARF (`ui1.scarf.rl.ac.uk`), account `scd`, QOS `normal` |
| Job | `3511123`, partition `gpu`, node `gn3000`, `--exclusive`, `--gres=gpu:a100:1` |
| Earlier job | `3511120` FAILED in 10 s at preflight/configure (no `nvcc`: `module load` had been piped into a subshell). Allocation released immediately; recorded, not hidden. |
| Scratch | `/work4/scd/scarf1415/motioncorr/mc-issue94/` — quota `pan_quota` reports **unlimited** soft/hard, 3.08 TB currently used |
| Inputs | 24 tutorial movies + `gain.mrc` + `movies.star`, **copied into this task's own tree**, never read from or written to #53's `i53-scarf` tree during the run |
| Input identity | `input_sha256.txt`, 26 files; verified byte-identical to the i53 tutorial inputs before use |
| Source | `ab9cd6b9a3ee5c2f0de11a623d849dc921a71448` staged by `git archive` |
| Toolchain | GCC 13.2.0, CMake 3.27.6, CUDA 12.8.0, FFTW 3.3.10, LibTIFF 4.6.0, libpng 1.6.40, libjpeg-turbo 3.0.1, zlib 1.2.13 (all EasyBuild modules) |

Design of the run, and why:

- **Correctness before timing.** Prefetch off vs on over all 24 movies, compared on every MRC
  payload, every normalized header (bytes 0-224; 224-1024 is the label area and carries a
  wall-clock timestamp) and every STAR artifact. If the arms disagree the job **exits without
  producing any timing**, because a speed number from arms that differ is meaningless.
- **Fixed CPU budget for both arms.** The allocation is exclusive, so the job's cpuset is the
  whole node — that keeps other users off the host but is *not* a budget. Both arms are
  `taskset`-pinned to the same 16 logical CPUs, chosen on one NUMA node and preferring distinct
  physical cores before SMT siblings, with `--j 8` and `OMP_NUM_THREADS=8`. The prefetch arm's
  reader threads therefore come out of the same budget and are counted, not treated as free.
- **Paired, alternating, labelled.** Three pairs with the arm order flipped each time and the
  order retained, so the positional bias comes out of the same data.
- **RSS over the owned process tree**, sampled at 200 ms — not one pid, not the node.
- 100 ms NVML sampling for device high-water, recorded as a lower bound.
- Full provenance per run: inherited `Cpus_allowed_list`, `lscpu` topology, NUMA policy, GPU
  **UUID** (ordinals never identify silicon), co-tenant compute apps, node occupancy.

Not attempted, and still **UNRUN**: the composed PR103/PR110 integrity work — the standing
instruction is that reader/error integration with PR110/103/105 is a *later* bounded
composition, and composing another task's branch here would be a merge this task is not
authorised to make.

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

Wait on SCARF job `3511123`, then publish exact source/input/binary/harness/commands/results
and the allocation release on #94, #108 and #66. No merges, no default promotion.

If the paired screen shows no meaningful full-run improvement, **the negative result is the
deliverable**: record it, keep prefetch opt-in, and do not promote the complexity.
