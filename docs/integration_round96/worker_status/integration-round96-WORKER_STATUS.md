# WORKER_STATUS — round96 correctness-foundation integration

| field | value |
|---|---|
| Issue / role | #96 integration and correctness owner (lane A of the #96 next-round plan) |
| Model | claude-opus-5, high effort, 1M context |
| Task class | integration of reviewed round96 correctness PRs; CPU validation; CUDA compile |
| Phase | all four groups integrated; CPU validation and CUDA compile executed; draft PR and independent review in progress |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main, refetched and pinned) |
| Branch | `integrate/round96-correctness-foundation` |
| Candidate source head | `d3c04f7f2a40637e8666ccfb4fb43a6e9540d316` (later commits are docs/evidence only) |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-75781550` (T3-created, isolated) |
| Merge authority | **none**. Draft PR only. No merges, no closures, no default promotion. |

## Active locks and jobs

| resource | state |
|---|---|
| `/tmp/motioncorr-issue96-cpu-validation.lock` (cpu64) | acquired per validation batch (phases 1, 2, 3, final), released after each. Lane `taskset -c 32-63`, `numactl --membind=1`, build/runtime <= 16 |
| `/tmp/motioncorr-bench.lock` (4-gpu-vm) | acquired for CUDA **compile only**, after waiting for the #69 thread to release it. Lane `taskset -c 96-111`, `-j8`. Released |
| GPU execution slot | **not requested for execution.** `NEEDS_GPU` published in the PR body, unrun. No CPU run was substituted for it |

## Integrated groups

| group | PR | issue | head cherry-picked | commits | state |
|---|---|---|---|---|---|
| 1 | #102 | #72 fail-closed CI / canonical fixtures | `cf049ef4dab6278d18fc8c02754151ac717f85cb` | 6 | applied, tree identical to `pr/102` at that point |
| 2 | #105 | #99 fail-closed MRC/STAR writes | `910fcf431c038b3930cfd6919cebaeb02fc2295d` | 11 | applied; one CMake test-registration conflict resolved as a union |
| 3 | #103 | #92 TIFF integrity / expected frame count | `78621d318a89765d636827df7b9147d5cfd6f096` | 7 | applied; one genuine `src/image.h` semantic merge with group 2 |
| 4 | #101 | #98 malformed defect rectangles | `482c75ac32d659329d18098c5f0b58ddf2c552bc` | 19 | applied after its owner published the final reviewed head; `src/motioncorr_runner.cpp` auto-merged with group 3 and verified as an exact union |

## Deliberately NOT on this branch

| PR | issue | why |
|---|---|---|
| #100 | #97 recenter origin | changes option-on behaviour against inherited upstream code. Conditional pending explicit acceptance of the deliberate upstream divergence plus the option-on / non-one-selected-frame controls. Recorded as conditional / no-go rows, not integrated. |
| #108, #107, #93, #104, #109 | #94, #69, #77, #95, #26 | out of scope for this foundation branch by instruction. Future integration edges documented in the PR body. |

## Reviewed source heads consumed

| PR | reviewed source head | reviewer verdict of record |
|---|---|---|
| #102 | `cf049ef` (audit recorded at `8fc088c`, two docs commits after) | READY_TO_MERGE (code/spec) + COMPLIANT (license), two bounded auditors |
| #105 | `910fcf4` (source pin `f83a466`, docs after) | SPEC_CONFORMANCE_PASSED + LICENSE_PASSED, no severe code defect, two bounded reviewers |
| #103 | `78621d3` (source pin `433f04e`/`3037c4b`) | independent read-only code/spec/license audit passed |

## Latest results

| layer | result |
|---|---|
| cpu64 Release build | configure 0 / build 0, `-O3 -DNDEBUG` read back from the cache |
| full CTest suite, combined tree | **17/17 pass** |
| fail-closed chain (preflight, inventory, canonical generate, verify, 7 controls) | all exit 0 |
| candidate tests vs BASE main source | control builds and runs; 4/17 fail, exactly the four integrated groups' tests |
| healthy all-24 A/B vs exact main | 24/24 images identical, 341,735,520 pixels, 25 STARs identical; 4 PDFs differ (known ghostscript nondeterminism, retained, overall left FAIL) |
| CUDA `sm80` compile | 0 errors, real `sm_80` cubins, cudart/cufft linked |
| CUDA **default** configure | **FAILS** -- `CUDA_ARCHITECTURES is empty`; pre-existing on main, scoped fix requested under #72/#18 |
| GPU execution | **unrun** |

## Note on this file

PR101's own history contains `a3cc983 chore: keep WORKER_STATUS.md out of the
production PR`, which deletes the root file. Cherry-picking group 4 therefore
removed this integration job's status file as a side effect. It was restored
from `6f29659` and PR101's own handoff (added by `d26617a`, deleted by
`a3cc983` within its own branch) is archived alongside the other three, so no
worker record is lost either way.

## Next step

1. Two bounded independent read-only reviewers on the integration surface (running).
2. Publish the draft PR and comment on #96 / #66.
3. Await a coordinator GPU slot for the published `NEEDS_GPU` plan.
