# Exact dose-normalization reuse experiment

Baseline current main c499b1d3bf1cceec5c3b194f356844d6f493e7f2. Separate branch
experiment/post128-dose-normalization. No workspace/synchronization/ingest/output/
multi-GPU import. #77 previously proposed reuse; old algebraic dose optimizations
produced nonzero differences and are excluded.

One reconstruction-scoped float plane stores the original sqrtf of the original
ascending expf-square sum at each frequency. Geometry/apix/dose float conversions,
Ne formula, numerator, final division and DC branch remain unchanged. Recompute
per call; no cache/stale-dose key. Allocation/launch/precompute completion and
cleanup use existing failure owners. Extra storage4*ny*(nx/2+1)bytes is reported;
precompute and allocation cost included in reconstruction/application timings.

First: native byte-exact old-kernel controls for1/8/24/80/160frames, changed/zero/
irregular doses, odd/non-square geometry/apix and null/polynomial reconstruction;
actual new allocation/launch/completion/cleanup error controls and powered wrong/
omitted-dose mutants. Keep genuine context poison separate from injected status.
Then whole-application exact products/headers/STAR/native witnesses and matched
alternating process pairs on the tutorial workload and clearly labelled synthetic
long-movie fixtures (repeated actual tutorial frames, not new acquisition data).
Only confirm a promising screen; no claimed long-movie gain from kernel complexity.

Dedicated SCARF resource, one UUID, payload affinity verified, build≤8, no competing
compute or overlapping build/timing. CPU and CUDA-without-nvCOMP remain supported.
Keep all failures and unrun rows; no tolerance or arithmetic relaxation. No merge.
