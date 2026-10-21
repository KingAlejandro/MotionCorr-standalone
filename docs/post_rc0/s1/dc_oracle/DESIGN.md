# Diagnostic CCF numerical reference (#262)

Diagnostic branch only. Parent `31309df0` combines #254 `af2a5900` and #260's
production fit plus tests (`531e9db4`, `6c23ba1d`), retaining both CMake test sets.
No inherited CPU bug is proposed for production repair.

`MC_DIAG_CCF_DC=none|global|local|both` defaults to none. The selected CCF
scratch spectrum's (0,0) bin is zeroed immediately before inverse transformation.
Global and per-patch calls use their existing is_global flag; batched calls are
local, and retry dispatches reuse these same entry points. CUDA still projects
Hermitian columns. Frame spectra, weights and reconstruction are untouched by
this operation; changed estimator feedback can change subsequent inputs.

`MC_DIAG_CCF_DOUBLE=1` enables CPU-only double reference accumulation, CCF
product, FFTW inverse, strict row-major peak search and quadratic fitting from
existing float frame spectra. The existing float B weights, frame transforms,
shift feedback, fitting policy, convergence and publication behavior remain.
Thus it isolates the CCF precision pipeline; it is not a double movie pipeline
or a motion-truth oracle. Combining both toggles checks offset neutrality.

Observation hooks are reused from #261's capture commit `bff7c991`. Double maps
and five-sample records retain double precision. Toggle-off byte controls compare
MRC core header (0:224), payload and movie STAR; timestamp labels are reported
separately. No production default or tolerance changes.
