# Future analysis plan (plan only; nothing is run now)

Applies only after the two parent-released capture jobs exist and their records are sealed. Uses the unchanged cleared v3 oracle with the actual saved float32 real CCF maps as primary input, truth read-only and only after the capture record is sealed, global optimum UNPROVEN_GLOBAL, no causal noise claim, no new estimator or arm.

Per selected patch ((104,15) and (62,79)), each actually executed iteration k, all 5 frames:
1. Integrity: file coverage, API-consumed versus actual C2R input versus API-after, scalar raw/weighted expression, weight map built with x_norm 42, map-to-search/verdict/selected-shift identities at native precision (as in the reviewed analysis protocol).
2. Frame-0 raw reference r0^k versus the frame-4 raw selected shift r4^k, with the anchor-adjusted deltas d_f^k = r_f^k - r0^k (as applied) and the frame-0 raw value reported separately, never absorbed.
3. Sum closure: sum_k d_f^k against the final local shifts, then the native interpolate/recentre step, then the reported observation; the Tr closure `y[g] = L_g + 0.5*L_1` (with L_0 = 0 after the pin) checked against the stored STAR observation to its 5-decimal rounding.
4. Per-iteration contribution of each term to the endpoint (g=4) observation, and entering/exit trajectory, for both patches; same-state objective values at the native peak and at the unclipped refined point.
5. Truth enters only afterwards as a read-only scoring coordinate (physical-centre increment, as in the existing protocol); it is never used to choose or move a peak. Reporting keeps the physical and Tr gauges separate. No percent causal shares; convergence alone is not a cause.
Open comparisons to return: old-weight (62,79) state versus full-width (62,79) state; (104,15) versus (62,79) under full-width. The previously captured old-weight states are not mixed with the new ones (schema `/1` versus `/2`).
