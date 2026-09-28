# WORKER_STATUS — issue #94

| field | value |
|---|---|
| Issue | #94 bounded next-movie CUDA prefetch |
| Model | `claude-opus-5` (Opus 5, 1M context), high effort — no routing errors, no model substitution |
| Task class | implementation |
| Phase | 4/5 — implemented, CPU-validated, evidence published; draft PR next |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main) |
| Head | `1955238` (validated source `412f2f98be401760aa2b336deaba3aa348cfafd7`) |
| Branch | `round96/94-claude-opus-5` |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-967d9ef6` |
| PR | (opening now — URL recorded here and on the issue) |

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

## Latest test commands and results

Host `cpu64` (`small-refmac-machine`), 2026-09-28T00:11:48Z, source `412f2f98`.
Lane **`taskset -c 32-47`** (top-level, descendants inherit) under
**`flock /tmp/motioncorr-issue96-cpu-validation.lock`**, build `-j16`, runtime `<= 16`.
The old independent `/tmp/motioncorr-issue96-cpu.lock` is no longer used.

```
cmake -S <src> -B build-release -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON   # rc=0
cmake --build build-release -j 16                                              # rc=0, 21.6 s
ctest --output-on-failure -j 1                                                 # rc=0
```

**15/15 tests passed**, 19.84 s. `CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp`
(GCC 13.3.0, CMake 4.4.3). `motioncorr` sha256 `b8f2907d92862f48c971ff63f226434f0efff2c841324fc6394ce40e17b3df52`.

- `PrefetchLifecycle` 5.43 s — 19 admission/lifecycle cases, every blocking one watchdogged.
- `PrefetchEquivalence` 7.31 s — 10 serial-vs-prefetch cases all byte-identical, plus a
  positive control proving the pixel comparison can fail.
- 13 pre-existing tests unchanged and still passing.

NUMA/placement actually observed (not inferred from the mask): inherited
`Cpus_allowed_list=32-47`; `lscpu` shows 16 distinct physical cores on socket 1, no SMT
siblings in the lane; `numactl --show` → `cpubind: 1, nodebind: 1, membind: 0 1`, so CPUs are
node-local and **memory is not pinned** — no NUMA memory-locality claim is made.
Interference recorded and not altered: two unrestricted `ctffind` at ~100% each
(`Cpus_allowed_list=0-63`) and another round worker's `motioncorr` at 100% on CPU 3 (node 0);
load1 5.42 → 6.57.

Full log: `docs/issue94_prefetch/cpu_validation_412f2f98be40.log`.
CLI contract: `docs/issue94_prefetch/cli_contract_412f2f98be40.txt`.

## Active PID / job / allocation

None. The cpu64 job finished at 2026-09-28T00:12:31Z and released the validation lock.
Staged tree and build remain at `cpu64:~/mc-issue94/src-412f2f98be40/` for re-checks.

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

## Subagents / reviewers

None launched yet. At most two bounded read-only reviewers will be used for the independent
code/spec/license review before the PR leaves draft.

## Next step

Open the focused draft PR, record its URL here and on #94, then request independent read-only
review. No GPU submission until a slot is explicitly transferred from #26.
