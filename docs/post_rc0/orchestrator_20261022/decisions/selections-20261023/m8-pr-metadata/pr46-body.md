**Parked — maintainer M8 selection, 23 October 2026 (Europe/London).**

This PR remains open at retained head [`2ef82b0279d0db7403daf9ba6c2943888f3a0321`](https://github.com/KingAlejandro/MotionCorr-standalone/commit/2ef82b0279d0db7403daf9ba6c2943888f3a0321). The Metal feasibility projection is historical, not measured qualification or implementation approval. Parking does not close #35; #52 retains the real tutorial limitations. No branch deletion or history rewrite is authorized.

The original PR description is retained below.

---

### Summary
Addresses [Issue #35](https://github.com/KingAlejandro/MotionCorr-standalone/issues/35) and references [Epic #29](https://github.com/KingAlejandro/MotionCorr-standalone/issues/29).

### Deliverables
1. **Architectural Decision Record**: `agents/designs/issue_35_metal_patch_alignment_feasibility.md`
   - **Post-Mortem of CUDA PR #37**: Explains the Amdahl's law bottleneck where accelerating patch CCF on GPU produced a net slowdown (0.96x) because 66% of process wall time (10.5 s) remained on CPU for bilinear resampling and dose weighting.
   - **Feasibility Verdict**: **CONDITIONAL GO**. A holistic Metal pipeline accelerating batched patch CCF, CPU SVD fitting, and native Metal GPU bilinear resampling (`realSpaceInterpolationKernel`) is projected to achieve $\approx 13.6\times$ end-to-end speedup on Apple Silicon (M4 Pro).
   - **Resource Footprint**: Staging budget requires 2.68 GiB peak memory on unified memory ( \times 3710 \times 24$ Falcon-3 micrograph), well within hardware limits.
2. **Dataset Comparison Tool**: `tools/compare_metal_dataset.py`
   - Evaluates multi-movie benchmarks against CPU j1 reference runs with Metal profile extraction and Gate 2 validation.

Closes #35 when merged.