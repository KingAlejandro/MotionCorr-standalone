# W6 round 2: harmful-case mechanism and P5 check (frozen before any round-2 computation)

Written 2026-10-26 after W6 (34681942) was accepted, before any round-2 code or result exists.
Same replay (round-2 W5 `lib.py`, W6 `W6Estimator` class taken verbatim from `scripts/w6.py`),
same lane and rules. Diagnostic only: no estimator, weight, tolerance, guard or scoring change.

## Calculations

Case vel1-N20 (vel1 = (-0.8125, 0.53125) px/frame), arms S-P/S-D/H-P/H-D, double and map32, gain 1.
Per iteration and frame, log the raw (unanchored) peak, its integer argmax, the top local maxima of
the CCF in the search window, and the ideal leave-one-out displacement
a_f = (t_f - s_f) - mean_{j!=f}(t_j - s_j) for the state s before that iteration.

- (i) Capture: integer argmax vs round(a_f) at every iteration; runs started at truth and at 50% of
  truth (5 / 0.5 px and 50 / 1e-9); endpoint frame errors compared with the local maxima of the
  W-weighted target autocorrelation (alias candidates) for iso and prod.
- (ii) Transient: raw update RMS and max per-frame update norm per iteration.
- (iii) Weight: the same logs for vel1-N20-prod beside vel1-N20-iso.
- map32 escape: the first (iteration, frame) where map32 S-P and map32 H-D (and S-D) differ in
  integer argmax, and the first where the subpixel peak differs by > 1e-6 px; at that point, the top
  CCF maxima, 3x3 values and float32 ulp in both runs, and whether any map32 S-P frame had an exactly
  zero update (dead-zone freeze) before that point.
- P5: double S-P vs S-D (and H-P vs H-D) per-iteration, per-frame peak and state differences for the
  W6 rows with the largest P5 gaps: vel0-N13-prod-5it, vel0-N9-prod-5it, pedestal fixture 50 it
  (S-D vs S-P) and vel0-N13-iso-5it (H-D vs H-P), flagging any iteration where the integer argmax differs.

## Predictions

- **M1 (i, capture).** In double, iso, every arm: at iteration 1 at least one frame's integer argmax
  is >= 2 px from round(a_f), and the endpoint frame errors lie within 1 px of iso autocorrelation
  local maxima (alias lock). A start at truth stays at truth (< 1e-6 px) in every arm and domain.
  A start at 50% of truth converges to truth (PASS) in every arm in double.
- **M2 (ii, transient).** At gain 1 no later raw update exceeds the iteration-1 raw update RMS; the
  wrong basin is entered at iteration 1, not through a later overshoot.
- **M3 (iii, weight).** Under prod the iteration-1 integer argmax is within 1 px of round(a_f) for
  every frame, and the largest secondary autocorrelation maximum (relative to the central peak) is
  lower for prod than for iso.
- **M4 (map32 escape).** map32 S-P and map32 H-D first differ in integer argmax at iteration 1 or 2,
  which is a changed early argmax and not a late dead-zone freeze. No map32 S-P frame has an exactly
  zero update before that point.
- **M5 (P5a).** Double S-P and S-D iteration-1 peaks agree within 1e-9 px for every frame in each
  checked row. A larger iteration-1 difference indicates a replay defect.
- **M6 (P5b).** The 0.70 px final P5 gaps are not smooth geometric growth: in each checked row the
  difference jumps at one iteration where the two arms' integer argmax differs.

The mechanism verdict is the hypothesis whose test passes. If none or several pass, that is reported
as found. This file is not edited after commit.
