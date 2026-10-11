# Retained movie geometry (fix 2)

`CudaMovieSession::release()` used to free the movie frame buffers and destroy both
global cuFFT plans after every movie, and the next movie of the same size allocated
and planned them again (about 8 ms of setup and 3 ms of release per steady movie on
main 7d64043, see `MAP.md`).

**Design.** The worker's thread-local `CudaWorkerPlanPool` gains one
`GeometryEntry`, keyed on (device, nx, ny, n_frames). It holds `d_Iframes`,
`d_Fframes`, the R2C/C2R plans, the shared FFT work area and the inverse tile, which
are all owned by the session for the whole movie. `d_Isum` and the gain are not
retained: the session frees them mid-movie (`releasePreprocessingBuffers`).

- `initialize()` takes the entry when the key matches. The session then owns it
  outright, so a peer session on the same thread never shares it. On a mismatch it
  drops the entry before allocating, so two geometries never coexist.
- `release()` returns the entry only after a clean movie: initialized, no recorded
  failure, pool not retired, entry slot empty, every component present. Any failure
  frees the buffers as before. A fatal error retires the pool, which drops it.
- Products do not depend on prior buffer contents. Every retained buffer is fully
  written before it is read, as it already had to be with fresh `cudaMalloc` memory.

**Switches.** `MOTIONCORR_RETAIN_GEOMETRY=0` restores per-movie allocation.
`MOTIONCORR_FRAME_POOL_POISON=1` (shared with the host frame pool) fills taken
buffers with 0xFF before use, so a missing write shows up as a product difference.

**Memory.** Peak VRAM per movie is unchanged, since the retained set is what the
session already holds during a movie. The change is residency: those bytes stay
allocated between movies until the worker thread exits, the geometry changes, or the
pool retires. `cudaMemGetInfo` is read only after `initialize()`, so the free-memory
figure each movie plans against is the same as before for a single worker per GPU.
With several workers on one GPU, a worker that is between movies no longer frees
its movie buffers for its peers.

**Tests.** `CudaGeometryRetention` covers reuse, poisoned reuse, geometry change
(old entry freed before the first new allocation), failed sessions (including the
case where the release guard's own drop is refused by a peer's gain lease) and
interleaved sessions, all with byte-identical products. It has three compiled
mutants: no take, return after failure, and keeping an alias to taken buffers.
`CudaFaultMatrix` now also faults every call of a warm second movie, and it takes its
successive-movie ordinals from clean multi-movie runs.
