# WORKER_STATUS — round96 correctness-foundation integration

| field | value |
|---|---|
| Issue / role | #96 integration and correctness owner (lane A of the #96 next-round plan) |
| Model | claude-opus-5, high effort, 1M context |
| Task class | integration of reviewed round96 correctness PRs; CPU validation; CUDA compile |
| Phase | branch assembled; CPU validation pending; PR101 held for its reviewed head |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main, refetched and pinned) |
| Branch | `integrate/round96-correctness-foundation` |
| Head | see `git rev-parse HEAD` — recorded per evidence run below |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-75781550` (T3-created, isolated) |
| Merge authority | **none**. Draft PR only. No merges, no closures, no default promotion. |

## Active locks and jobs

| resource | state |
|---|---|
| `/tmp/motioncorr-issue96-cpu-validation.lock` (cpu64) | see the evidence run records; acquired per validation batch, released after |
| `/tmp/motioncorr-bench.lock` (4-gpu-vm) | not held by this job for timing; CUDA **compile** coordination recorded below |
| GPU execution slot | **not requested for execution.** `NEEDS_GPU` published, unrun |

## Integrated groups

| group | PR | issue | head cherry-picked | commits | state |
|---|---|---|---|---|---|
| 1 | #102 | #72 fail-closed CI / canonical fixtures | `cf049ef4dab6278d18fc8c02754151ac717f85cb` | 6 | applied, tree identical to `pr/102` at that point |
| 2 | #105 | #99 fail-closed MRC/STAR writes | `910fcf431c038b3930cfd6919cebaeb02fc2295d` | 11 | applied; one CMake test-registration conflict resolved as a union |
| 3 | #103 | #92 TIFF integrity / expected frame count | `78621d318a89765d636827df7b9147d5cfd6f096` | 7 | applied; one genuine `src/image.h` semantic merge with group 2 |

## Deliberately NOT on this branch

| PR | issue | why |
|---|---|---|
| #101 | #98 malformed defect parser | owner is fixing the reviewed read-error P1. Head `482c75a` appeared 2026-09-28T02:10Z with no evidence or review comment yet. Held for its **final reviewed head**; this job will not duplicate the patch. |
| #100 | #97 recenter origin | changes option-on behaviour against inherited upstream code. Conditional pending explicit acceptance of the deliberate upstream divergence plus the option-on / non-one-selected-frame controls. Recorded as conditional / no-go rows, not integrated. |
| #108, #107, #93, #104, #109 | #94, #69, #77, #95, #26 | out of scope for this foundation branch by instruction. Future integration edges documented in the PR body. |

## Reviewed source heads consumed

| PR | reviewed source head | reviewer verdict of record |
|---|---|---|
| #102 | `cf049ef` (audit recorded at `8fc088c`, two docs commits after) | READY_TO_MERGE (code/spec) + COMPLIANT (license), two bounded auditors |
| #105 | `910fcf4` (source pin `f83a466`, docs after) | SPEC_CONFORMANCE_PASSED + LICENSE_PASSED, no severe code defect, two bounded reviewers |
| #103 | `78621d3` (source pin `433f04e`/`3037c4b`) | independent read-only code/spec/license audit passed |

## Next step

1. CPU build + full suite + negative controls on cpu64, cores 32-63 capped at 16, under the validation lock, with NUMA/cpuset/source/binary/input provenance.
2. Fresh CUDA configure/compile: default configure and explicit `sm80`, separately.
3. Draft PR with the requirement-to-evidence matrix, exact unrun rows and merge order.
4. Two bounded independent read-only reviewers on the final source head.
