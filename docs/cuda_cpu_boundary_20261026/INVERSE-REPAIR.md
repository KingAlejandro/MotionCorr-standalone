# Additive inverse replay v2 repair

Parent source review found the initial diagnostic inverse-CUDA helper allocated
`vector<fComplex>(n*count)`, whose empty default constructor leaves unfilled
slots indeterminate. It filled only frames0/4, then projected/transformed all24.
This is a diagnostic-helper defect, not production CUDA behavior. Retain the
original28attempts and original54-control summary unchanged; its four CUDA
inverse runs and four projected-CPU derivatives are PROVISIONAL for inverse
attribution. The first forward-FFT mismatch, native captures, and forward/window
operator evidence are unaffected. Original raw-CPU inverse runs remain retained.

v2 explicitly initializes all24slots with fComplex(0,0). Rerun only four raw
CUDA inverse compatibility jobs (2cases x2stored spectra) and four dependent
projected-CPU jobs. Add four separately labelled valid CUDA inverse controls,
which require byte-identical complete input stacks before/after projection.
Total12new inverse-only processes; no movie/capture/forward/window repeat.

Raw inverse CPU input is the saved actual raw weighted spectrum, which is not
Hermitian-valid. CUDA raw inverse is explicitly native projection PLUS C2R;
it is compatibility behavior, not an unchanged-input pure inverse-FFT cross.
For the separate valid controls, CPU and CUDA read exactly the same hashed
projected bytes. CUDA must assert projection is a byte no-op on all24slots.
Only that conditional residual can be attributed to inverse execution, without
an independent correctness or truth oracle. Input/output arrays and old failed
provenance are never silently replaced or relabelled as new passes.
