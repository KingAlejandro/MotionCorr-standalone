**Parked — maintainer M8 selection, 23 October 2026 (Europe/London).**

This PR remains open at retained head [`edb57b5d91ec0719d7285a16a4771b886d979e65`](https://github.com/KingAlejandro/MotionCorr-standalone/commit/edb57b5d91ec0719d7285a16a4771b886d979e65). The historical tutorial relative-RMSE FAIL (0.01322–0.01323) and exploratory two-run 1.04× ratio remain unchanged; no backend or performance acceptance is implied. No branch deletion or history rewrite is authorized.

The original PR description is retained below.

---

## Summary

Adds the resampling component probe source and captured log, plus a reproducible real RELION tutorial movie report and JSON metrics for commit `637b8117c83c670b6556ee6ef31a594ed6f78494`.

The real 24-frame M4 Pro run completed in 5x5 dose-weighted mode. Relaxed Gate 2 **fails** on relative corrected-image RMSE (0.01322-0.01323 vs 0.001); two runs per backend show only an exploratory 1.04x median CPU/Metal ratio. This does not establish a reliable speedup or satisfy the three-run requirement.

The synthetic resampling probe passes its component checks, but it is explicitly labeled component-only and does not certify full MotionCorr Gate 2. This follow-up corrects the scope of the earlier certification wording on PR #46.

## Scope

- Does not close Issue #35 or Issue #32; both still have unmet acceptance criteria.
- Does not include the tutorial movie, gain file, or generated binary.
- Stacks on `feat/issue-35-metal-patch-feasibility` (PR #46).
