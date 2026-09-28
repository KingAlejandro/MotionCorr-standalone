# WORKER_STATUS — issue #53, round 96

| Field | Value |
|---|---|
| Issue | #53 — current-main multi-GPU scheduler |
| Model | `claude-opus-5` (high effort), Claude Code / T3 Code |
| Task class | implementation |
| Phase | 5 — native two-GPU correctness complete; GPU slot RELEASED |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (current main) |
| Head | `69638bf` |
| Branch | `round96/53-claude-opus-5` |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-20acbcac` |
| PR | https://github.com/KingAlejandro/MotionCorr-standalone/pull/106 (draft) |

## Scope (PR A only)

Static whole-movie process workers, deterministic metadata merge, native
device-list honesty, cheap CPU fixtures. **Not** in this PR: dynamic coordinator
or work queue, coordinator gain/merge C++ flags, intra-movie GPU split, any
numerical change, any throughput claim.

ADR and changed-file whitelist: `agents/designs/issue_53_multi_gpu_scheduling.md`.
PR55's branch, history and evidence are untouched.

## Changed files

Diff against base is exactly the ADR whitelist, 19 files:

- production: `src/motioncorr_runner.cpp` (+36/-11, device-list validation and help text only)
- tooling: `tools/multi_gpu/{star_io,partition_star,merge_workers,gpu_witness,run_multi_gpu,compare24}.py`
- tests: `tests/{fake_worker,test_multi_gpu_scheduling}.py`, one `add_test` in `CMakeLists.txt`
- docs/evidence: `agents/designs/issue_53_multi_gpu_scheduling.md`, `docs/multi_gpu/`, `WORKER_STATUS.md`

No pre-existing test, tolerance, gate or numerical constant is touched.
`WORKER_RESOURCE_UPDATE.md` is Alex's file and is deliberately left untracked.

Commits, separated by kind as the round requires:
`6b17a2e` docs/ADR · `1b8ada5` fix · `8008b60` tools · `3eece28` test · `e0699da` evidence.

## Latest test commands and results

One run, host `small-refmac-machine` (cpu64), `taskset -c 32-63` (NUMA node 1),
under `flock /tmp/motioncorr-issue96-cpu-validation.lock`. Source staged by
`git archive` of the committed tree; head `2353876`, base `4c952b3f`,
`applefile_count=0`, `BUILD_RC=0`, zero compiler errors. Release,
`-O3 -DNDEBUG -std=gnu++17 -fopenmp`, g++ 13.3.0, cmake 4.4.3, Python 3.12.3.
Patched binary `f4748106a1a296efd961b655fce675c9336cda42ca63f7b4bf4488d12ef9e8f2`;
unpatched-main control `de35fddc37d8237576adea7d34bec618ce1bf4867286b87ec568815c71645f8a`.
Raw artifacts: `docs/multi_gpu/pr_a_evidence/`.

| Layer | Result |
|---|---|
| `tests/test_multi_gpu_scheduling.py --binary <built>` | **27/27 passed** |
| `docs/multi_gpu/negative_controls.py` | **25/25 mutations detected**, no survivors |
| `ctest --output-on-failure -j 4` | **14/14 passed** (13 pre-existing + `MultiGpuScheduling`) |
| end-to-end, real binary: serial vs 3-way sharded, 6 movies | **6/6 exact**, merge `PASS`, aggregate STAR identical, `DISTINCT_PAYLOADS=6/6` |
| `--gpu` list rejection, patched vs unpatched main | recorded in the validation log |

Interference recorded from the artifact: load average `40.52 22.97 13.09` at
start and `51.49 29.74 16.02` at end; a concurrent `python` at 5656% CPU,
another round's `motioncorr` at 373%, two `ctffind` trees. Nothing in PR A is
timed, so no claim is affected; recorded so this is never reused as a timing
baseline.

### Independent reviews

Both required read-only reviews were run and their findings are fixed in
`f3ee2b5` and `2353876`:

- **Code/correctness.** Found the C++ change, `gpu_witness.py` selection and
  `compare24.py` clean. Found that the merge could not have handled any real
  run (`_shifts.eps`), that a genuine misroute could pass when a movie name
  ends in an output decoration, that a failed device witness was laundered into
  a merge PASS, three `star_io` divergences from the C++ reader that all failed
  open, an unsafe `--link` + `--aggregate-with` combination, and several test
  gaps. All fixed, each with a case and a mutation.
- **Spec conformance and license.** Forward completeness and reverse scope
  isolation both clean; all line citations resolve; GPL-2.0 clean with no new
  third-party dependency (every import is stdlib). Found the invalid evidence
  run and two overclaims, all corrected in `e5431fa` and `2353876`.

## Active jobs / allocations

**None. The GPU slot is RELEASED as of 2026-09-28 07:07 UTC.** Verified at
release: zero processes whose executable is under the run tree (checked via
`/proc/*/exe`, not a self-matching `pgrep`), zero compute apps on any device,
all four GPUs at 1 MiB / 0%, `flock /tmp/motioncorr-bench.lock` unheld, host
load 0.74. #69/#110/#94 are unblocked by this release.

Allocation used while held: GPU0 `GPU-eddb42fe…` and GPU1 `GPU-cd5b9f86…` only;
all MotionCorr descendants inside CPUs 96-111 on NUMA node 1; build
`taskset -c 96-103 -j 8`; worker masks `96-103` and `104-111`, disjoint;
`--j 4 --max_io_threads 4`; every arm under the one benchmark mutex. GPU3 never
touched. GPU2 idle during the main arms, later running #69's authorized work —
recorded as concurrent occupancy, not gated on. Scratch retained at
`~/mc-i53-gpu` on `4-gpu-vm`.

## Blockers

None for PR A.

## NEEDS_GPU

**Satisfied and closed.** Full record: `docs/multi_gpu/GPU_ACCEPTANCE.md`,
artifacts in `docs/multi_gpu/gpu_evidence/`.

Source `f433662`, binary `d4e3afb8…`, Release + `-DCUDA=ON` sm80, nvcc 12.8.61,
driver 570.86.10. Inputs 25/25 verified against `Movies/SHA256SUMS.txt`.

| Arm | Result |
|---|---|
| Serial CUDA vs two-worker two-GPU sharded, 24 pairs | **24/24 exact PASS** |
| Aggregate `corrected_micrographs.star` | identical, canonical order |
| Device witness | **2 distinct physical UUIDs**, 0 unwitnessed / shared / wrong |
| Launcher inertness, plain serial vs 1 worker | 24/24 exact PASS |
| Owned-child failure (SIGKILL) | merge refused, 0 strays, 0 owned compute apps |
| Non-prefix resume (indices 5-11 missing) | merge PASS, 24/24 exact PASS |
| Unpatched main, `--gpu 0:1:2:3`, CUDA build | ran all 24 on **one** device, exit 0 |

**No timing, throughput or scaling figure was measured or is claimed.** #26 owns
that; other work shared the host.

Unrun and explicitly not claimed: >2 devices, `--grouping_for_ps`,
`--even_odd_split`, EER inputs, gain rotation/flip, other geometries and frame
counts. `logfile.pdf` equivalence excluded by construction. CPU/RELION Gate 2
untouched and still separately failing.

## Next step

Awaiting maintainer and @codex review of PR #106. PR B (coordinator gain/merge
flags) and PR C (bounded dynamic assignment) remain separate and not started.
