# ADR: who owns a CUDA resource that outlives a movie

## Context

`CudaMovieSession` is constructed and destroyed once per movie, so every
resource it owns is paid for again on every movie. On the 24-movie tutorial set
that is 24 gain uploads of 54.3 MiB, 24 whole-frame plan pairs with their work
area and inverse tile, 24 batched patch plans and 24 reconstruction plans — for
objects whose content or shape did not change.

Making them live longer is easy. Making them live longer *safely* is the
decision, because the obvious implementations all fail the same way: a handle
reachable from two owners, a cache key that outlives the thing it describes, or
a cleanup failure that gets overwritten by a successful-looking replacement.

## Decision

A single `mc_cuda::CudaWorkerPool`, owned by `MotioncorrRunner`.

**Owned by the runner, not by a `thread_local` or a process static.**
`run()`'s movie loop is serial and belongs to the runner, so the runner's
lifetime *is* the worker lifetime and "which pool" is never ambiguous. It also
makes the runner-local gain generation counter a sufficient identity: two
runners cannot collide on generation 1 because neither can see the other's
pool. A process-wide pool would have needed a process-wide counter, and a
`thread_local` would have needed one too as soon as two runners shared a thread.

**Sessions borrow.** A session receives a handle or pointer it may use and may
not destroy. `release()` nulls borrowed aliases and destroys only what the
session itself owns. No handle is ever reachable from two owners.

**An explicit lease, not an assumption about threads.** `acquireLease()` admits
one holder. A second holder is refused, and the refusal changes nothing — no
drop, no invalidation, no cleared borrow. A refused session falls back to owning
everything itself and the holder keeps running. `thread_local` storage would not
give this: two live sessions can interleave on one thread.

**Publish last, invalidate first.** Every created handle is adopted by a scoped
owner on the line after it exists, and ownership moves to the pool only after
the last fallible step of its construction has succeeded. Replacement
invalidates the entry *before* destroying what it described, so a failure
part-way through leaves "no resource, no key" rather than a key pointing at
something freed or half-built.

**A failed drop fails the acquire.** The pool does not construct and publish a
replacement as though the cleanup had succeeded. The original error, any late
fatal code and the caller's retry verdict all have to survive.

**Cleanup is device-correct.** Each entry records the device it was built on; a
drop selects that device, and the acquire therefore re-selects the requested one
before constructing. A device id in a cache key does not by itself make cleanup
context-correct.

**A fatal context retires the pool, but still attempts the release.** Retiring
discards the entries for that device and refuses every later acquire for it,
stickily and independently of any session's failure state — the next movie
starts with a clean `CudaFailureState` and that must not make handles from a
dead context reusable. It still attempts the same checked release every other
owner in this codebase performs on a poisoned context, recording each status
rather than trusting it. Skipping the release would leak the pool's bytes for
the life of the process; `CudaPreprocessingFailurePaths` observes exactly that.

**Bounded, with eviction.** One entry per resource class, each with a complete
key, so a geometry change replaces rather than accumulates. Before a movie is
refused for an allocation failure, the pool releases what the live lease is not
using and the admission is retried once; a genuine shortage still fails with its
real error, and nothing is retried after a fatal error. The eviction destroys on
each entry's own device, so the retry re-selects the requested one first — the
same rule as every acquire, and the one place it was initially missed.

## Consequences

269.5 MiB of device memory stays resident between movies at the tutorial
geometry. That is new residency and counts against any VRAM budget, although
the same buffers existed during each movie before — what changed is that they
are no longer freed in between.

Four `MC_POOL_*` compile-time switches exist so each mechanism can be measured
on its own. Production defines none of them.

## Alternatives rejected

*A `thread_local` pool keyed on device* (PR133's shape). Simpler to wire, but it
cannot express exclusivity, and the review of PR133 found the consequences:
a borrowed handle destroyed as if owned, and a created handle with no owner
until planning succeeded.

*Retaining the movie buffers* (`d_Iframes`, `d_Fframes`, `d_Isum`). Deferred,
not rejected: it is a 3.2 GiB residency change and has to earn that separately.
