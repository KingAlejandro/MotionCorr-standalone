# WORKER_STATUS — round96 correctness-foundation integration

| field | value |
|---|---|
| Issue / role | #96 integration and correctness owner (lane A of the #96 next-round plan) |
| Model | claude-opus-5, high effort, 1M context |
| Task class | integration of reviewed round96 correctness PRs; CPU validation; CUDA compile |
| Phase | review follow-up complete. Codex P2 fixed, three owners' fixes composed, **native CUDA executed on two platforms**, licence/scope delta review returned; code/spec delta review outstanding |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main, refetched and pinned) |
| Branch | `integrate/round96-correctness-foundation` |
| Candidate source head | `1c590ba0362fbf48b24b9509381d2e8d2eddebb0` (later commits are docs only) |
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

## Independent review

| reviewer | verdict |
|---|---|
| code / spec, bounded read-only | **READY_TO_MERGE** — no P1, no P2 on the integration surface; three P3, one fixed (docs attribution), two accepted and recorded |
| license / scope, bounded read-only | **LICENSE_COMPLIANCE_PASSED** + **SPEC_CONFORMANCE_PASSED** — 6 pre-existing warnings untouched, 43 cherry-picks with zero authorship rewrites, all handoffs archived byte-identically, zero deletions |

Neither reviewer compiled or ran anything; all execution evidence is this job's.

## CI

Run 36371119141 at head `6b4a950b`: Build & Smoke Check (Ubuntu Linux) **success**, CUDA compile only (no GPU execution) **success**.

## Published

- draft PR **#110**
- coordination comments on **#96** and **#66**
- integration notes on **#101**, **#102**, **#103**, **#105**; conditional/no-go note on **#100**

## Next step — not this job

1. Maintainer rulings on the five residual decisions in the PR body.
2. A coordinator GPU slot for the published `NEEDS_GPU` plan. **Unrun; no CPU run was substituted for it.**
3. Scoped `CMAKE_CUDA_ARCHITECTURES` build fix under #72/#18.


## Review-follow-up round (28 Sep)

| item | state |
|---|---|
| Codex P2 `r4119221898` canonical STAR immutability | **fixed** (`b0a70d6`, `13c6e32`, `fe8ca55`), reproduced before/after on cpu64 |
| #72 / PR102 review fixes | composed (`9524909`, `29e9635`); their restructure reinstated the STAR overwrite, re-applied in `615d67e` |
| #99 / PR105 `RLIMIT_FSIZE` fix | composed (`1084269`, `318a324`), test files byte-identical to their head |
| cpu64 combined suite, final source | **17/17**, 8/8 controls, negative control fails on exactly the four groups |
| **native CUDA, SCARF `3511135`** | **24/24 pixel-identical, 341,735,520 pixels, 25/25 STARs**; device witness pid 410748 on `GPU-c7b9c523…` |
| **native CUDA, VM GPU3** | identical result on different silicon; witness pid 1228552 on `GPU-b2cb2c39…` |
| native controls `3511136` | decoded-reader 24/24, failure exit 1 joint STAR withheld, resume exit 0 pixel-identical |
| CI at source head | both jobs success |
| licence / scope delta review | **LICENSE_COMPLIANCE_PASSED + SPEC_CONFORMANCE_PASSED** |
| code / spec delta review | running |
| `@codex` re-review | requested at `1c590ba0` |

All locks released: cpu64 validation lock free, SCARF jobs finished (only #94's
remains, untouched), VM GPU3 released and its device lock free.

## What remains before merge

1. Code/spec delta review verdict, and the `@codex` re-review.
2. Maintainer rulings: the `src/image.h` merge direction; the scoped
   `CMAKE_CUDA_ARCHITECTURES` fix under #72/#18; whether #72's numpy
   `FATAL_ERROR` stays unconditional; `generator_sha256`'s meaning; root
   `WORKER_STATUS.md` tracked or ignored; and whether the GPU3 use of the VM
   stands, since it extends the published 24-CPU / 3-device envelope.
3. The #97 upstream-parity divergence ruling before #100 can join.
