# Next targets after the separated resource/synchronization experiments

Read-only assessment of frozen PR130 `1420c8c`; no additional implementation or
benchmark is claimed by this plan.

## Defer worker-lifetime reuse until its own cost is isolated

The corrected workspace profile measures session initialization24/0.421231s,
release48/0.100246s, cuFFT planning144/0.541206s, destruction144/0.052016s,
CUDA malloc936/0.178502s and free936/0.134492s. These intervals are inclusive
and overlap. They span several resource owners and do not isolate local cold
workspace construction/destruction. Do not add them to predict wall savings.

A already amortizes600 local alignment calls into24 movie-owned workspaces.
Inspect existing trace attribution first; a retained worker owner would require
new geometry/gain/lifetime/fatal-state contracts. A resource pool is not justified
merely because some allocations remain. No cross-movie cache is implemented.

## Separate dose-normalization experiment, if long movies justify it

`src/acc/cuda/cuda_realspace_dw.cu` recomputes each non-DC denominator for each
current frame. Frequency/Ne depends on geometry and float-converted pixel size;
the denominator sums `expf(-dose[j]/Ne)^2` in ascending frame order and takes
`sqrtf`. It depends on frame count and the complete ordered float dose vector,
not on Fourier values, polynomial motion or the current frame index. Preserve
the separate DC branch `1/sqrtf(n_frames)` exactly. Runner dose inputs include
selected original frame numbers, pre-exposure and voltage scaling.

Potential bounded change: one scoped float denominator plane of
`4*ny*(nx/2+1)` bytes within the existing reconstruction call. Compute once with
the identical expressions/order, then use unchanged numerator and division by
the stored square root. No reciprocal multiplication, fastmath, altered FMA,
reduction, FFT, interpolation or reconstruction accumulation. Keep allocation,
launch attribution and checked cleanup in current ownership.

The measured dose kernel occupies0.219702 GPU seconds over576 launches in the
workspace profile; this is not a predicted application saving. Allocation,
precompute launch and memory traffic are included in any future comparison.
First prove exactness for varied geometry, irregular dose vectors, selected
frames, pixel sizes, polynomial/null models and frame counts8/24/80/160, with
wrong/omitted-dose mutants and actual allocation/launch/cleanup controls.
Then run complete matched application pairs for normal and long movies. Drop
normal24-frame promotion if the gain is within variability; preserve any
long-frame result separately. No gain, additivity or new source is claimed yet.

Leave the multi-GPU owner, ingest scheduling, whole-movie prefetch and output
architecture unchanged. Preserve scientific truth failures as distinct from
same-backend exactness. No new merger or acceptance scope is implied.
