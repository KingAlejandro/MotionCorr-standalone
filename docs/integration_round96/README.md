# round96 correctness-foundation integration — evidence index

Integration branch: `integrate/round96-correctness-foundation`
Base: `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main, refetched and pinned 2026-09-28)

This directory holds the integration job's own evidence. Each integrated
branch's original evidence directories (`docs/issue92_review_evidence/`,
`docs/issue99_write_faults/`, the ADRs under `agents/designs/`) are carried
across unchanged and are **not** superseded by anything here.

## Layout

| path | contents |
|---|---|
| `worker_status/` | each integrated branch's root `WORKER_STATUS.md`, archived verbatim under a distinct name instead of being resolved away |
| `scripts/` | the validation scripts exactly as executed on cpu64 and the 4-GPU VM |
| `evidence/` | captured stdout of those runs, with provenance headers |
| `REQUIREMENTS.md` | requirement → test / source / runtime evidence matrix, including explicit unrun rows |
| `OVERLAP.md` | semantic-overlap analysis and the merge order this job recommends |

## What this integration is, and is not

It **is** a draft candidate that composes four independently reviewed
correctness branches onto current main, with the union of their CMake test
registrations preserved, one genuine semantic merge in `src/image.h`, and a
combined-source CPU validation that did not exist before: ten separate green
branch CI runs are not a combined-source pass.

It is **not**:

- a merge, a merge approval, or an issue closure;
- a replacement for the independent reviews already performed on PR100/101/102/103/105 —
  those reviewed their own heads and remain the reviews of record for their content;
- any GPU **execution** result. The CUDA work here is compilation only. Nothing
  was run on a device; the compute-app witness is recorded empty at both the
  start and the end of every CUDA arm;
- a scientific-quality claim. Same-backend output equality, motion truth,
  and downstream scientific equivalence remain three different requirements.
