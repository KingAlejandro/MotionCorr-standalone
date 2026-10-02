# Reliable reusable single-GPU worker

Question: what should one long-lived single-GPU worker safely reuse so repeated
movies stop paying unnecessary setup cost?

Starting point: PR130 head `1420c8cc4d65ec6fc4b4a868e0135d8042b98bed`
(movie-owned patch alignment workspace), not merged at dispatch, so this branch
is based on it rather than on main `c499b1d3`. PR133's pool is a design
reference; its ancestry also contains the separately reported no-gain alignment
telemetry experiment, which is NOT imported here.

## What is in scope

Lifetime and reuse of CUDA resources across movies in one process, with the
result, failure behaviour and memory bounds preserved. Four mechanisms, each
measured on its own:

| arm | mechanism added |
|---|---|
| A0 | PR130 head, no pool |
| A1 | pool and lease present, every mechanism disabled (null control) |
| B  | + device gain retention |
| C  | + whole-frame R2C/C2R plans, shared work area, inverse tile |
| D  | + batched patch R2C plan |
| E  | + reconstruction C2R plan |

Out of scope, owned elsewhere: CUDA Graphs, input/backend expansion,
overlap/concurrency, multi-GPU scheduling. Also deliberately excluded: PR133's
defect premask/sparse-traversal change, which is a host-side runner
optimisation rather than worker resource reuse.

## Ownership rules the implementation has to satisfy

1. One owner per CUDA resource; sessions hold borrowed aliases with no destroy
   authority.
2. An explicit exclusive lease. A refused second holder changes nothing.
3. A key is published only after the complete construction succeeded.
4. Invalidation before destructive replacement.
5. Checked release: a failed drop fails the acquire, and preserves the original
   error, any late fatal code and the retry verdict.
6. Cleanup selects the owning device; construction re-selects the requested one.
7. A fatal context retires the pool's resources for that device, stickily.
8. Retained bytes are visible and bounded, with eviction before a new movie is
   refused for resource pressure.

## Evidence required

Native controls on real hardware through the production entry points, each
powered against a compiled mutant that reintroduces the specific defect it
claims to cover. Interleaved multi-arm timing with complete product comparison
on every run. A no-pool null control arm, so the scaffolding's own cost is
measured rather than assumed. Retained and peak device memory reported.
