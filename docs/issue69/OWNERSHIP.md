# CUDA reliability ownership baseline

PR115 extends the partial PR107 port against main a75a3f8. Reliability is independent
of PR93's optional alignment cache. No PR93 kernel, cache or performance change is
imported. The per-call alignment owners derive from PR107 9303a5c, with checked
release, immediate invalidation and no allocating host registry.

* Alignment owns eight temporary device buffers, eight events and one cuFFT plan.
  The input Fourier stack is borrowed and never freed by alignment.
* Host alignment wrappers own their upload staging allocation across upload,
  alignment and copyback, including exceptions.
* The runner owns movie-local patch Fourier scratch; alignment only borrows it.
  Its movie-scope guard also releases the legacy retained real-frame cache after
  early-binning/nonresident patch exceptions, including the last failed movie.
* CudaMovieSession exclusively owns resident frames, shared FFT workspace/tile,
  its movie plans and resident patch cache. Cache replacement clears pointers and
  capacity/geometry before release, checks release, and publishes new claims only
  after success. Plans are owned immediately after cufftCreate, before planning.
* FFT preparation and reconstruction use the same fixed scoped owners rather than
  vector registries that can allocate while registering an already acquired resource.

Release is one-shot and idempotent. All resources are attempted even when one release
reports failure. Session/helper release errors preserve monotonic fatal state; original
recoverable diagnostics cannot mask a later fatal release. Destructors do not throw.
No device reset or cache optimization is introduced. No performance claim is made.

A real driver failure to free/destroy does not guarantee physical reclamation. The
application invalidates the stale handle, reports the failure and refuses unsafe retry;
it cannot repair a genuinely poisoned context. After-release error injection tests this
ambiguous-error contract without deliberately damaging shared hardware. Test results
and remaining unrun classes will be recorded separately for the final source.
