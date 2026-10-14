# CPU local patch phase window experiment

Base: main `116eb04ad359cd5bf789b28809fc2047ea155b9b`. Issue #10.

## Scope and earlier work

The merged CUDA windowed patch spectra work in PR #168 already established the
same liveness observation. See `docs/perf_vram_tier1/report.md` and
`docs/vram_live_ranges.md`: local alignment consumes only the CCF support, with
full-patch frequency coordinates. This experiment applies that observation to
CPU phase updates. It does not change spectrum allocation, FFTs or CCFs.

For every iteration, CPU `alignPatch` builds `Fref` and each `Fccs` from precisely
`ccf_nfx` columns and `ccf_nfy` rows. Window row `wy` maps to full-spectrum row
`wy > ccf_nfy/2 ? wy-ccf_nfy+nfy : wy`. No other spectral bins are read during
alignment. Local `Fpatches` are cleared after shifts are interpolated and copied
into the polynomial model inputs. Grouped-frame patch spectra have the same
lifetime and support. Global `Fframes` are subsequently inverse transformed and
used for reconstruction, so their phase updates must remain full-sized.

## Change

The existing phase helper accepts optional window extents. Its default remains
the full geometry. Only `alignPatch(..., is_global=false)` passes the CCF window.
Table phases use the original signed full-spectrum row and the same normalized
shifts `-cur_xshifts/pnx`, `-cur_yshifts/pny`. The complex arithmetic and float
store retain their original expression order. The positive CCF Nyquist row stays
in the positive half, including odd half-sizes. Unconsumed bins remain at their
original values rather than receiving shifts; no caller may use them afterwards.

For a representative 768x742 patch and a 192x192 CCF, the complex pixel updates
drop from 385x742 = 285,670 to 97x192 = 18,624 per shifted group per iteration,
about 6.5% of the original. Trig table calls drop from 1,127 to 289. These are
operation counts, not measured stage or whole-movie speedups. Patch preparation,
CCF preparation, inverse FFTs, peak finding, and model fitting still run.

## Verification and timing protocol

`CpuPatchPhaseWindow` calls the production private helper through the existing
test friend and compares it with a frozen, licensed copy of the original full
helper. It checks 300 window geometries across odd and even full spectra, both
halves, crop edges, zero/partial/full extents and five successive phase updates.
Every retained complex float must match bit for bit, every discarded bin must
remain untouched. Default full geometry must match every original pixel.
GNU/ELF builds additionally wrap `sincos`/`sincosf` and check actual production
table call counts against window extents and full default geometry.

The same test compares actual production local and global `alignPatch` arms on
108 combinations of rectangular/even geometries, odd CCF half-sizes, 2/4/7 frame
groups with unequal amplitudes, j1/j4 and iteration limits 1/5, explicit CCF scales 0.7/1.0 and automatic
CCF sizing at scaled B=150. Convergence,
accumulated shift vector bits and iteration/RMSD logs must match exactly.

The separate unwrapped `cpu_patch_phase_bench --bench 1` (or `4`) times the
frozen original full-spectrum helper against the production window helper on
24 groups of a 768x742 patch,
20 updates per arm. Resetting and allocations of the frame stack are outside
the timer; per-call phase table allocations remain inside, as in production.
One warmup per arm is excluded. Six measured pairs alternate order. All retained
complex output bits are compared after every pair outside the timing interval. This is a
phase-helper experiment, not full patch alignment or whole-movie latency.

Release CPU build passed at `146dc07` with GCC 13.3.0, FFTW 3.3.10,
`-O3 -DNDEBUG -std=gnu++17 -fopenmp`. Both focused CTests passed: the new
`CpuPatchPhaseWindow` matrix and the existing `PatchRetryState` control. The new
test took 4.41 seconds; this is test duration, not performance evidence.
Configure/build/test logs and binary hashes are in
`docs/cpu_local_phase_window_evidence/`.

Measured performance and whole-movie product identity remain pending. No
whole-movie speed or correctness claim is established by the focused controls.
