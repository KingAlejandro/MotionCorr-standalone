# ALL = UP + B2 + FW: frozen predictions (2026-10-27, before any ALL run)

Frozen by the orchestrator (Opus 5.5) after K267 Mac B2FW (#290 head 6132f664), before any ALL run. The B2FW census
round on #287 is still running.

## Arm and binary
ALL = env MC_EXPERIMENT_CCF_DC_ARM=both + `--experimental_coupled_peak all` + the B2 flag as the #287 census used it +
`--experimental_local_full_width_weight`, on Mac binary d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546.

## Reasoning
- On the plain base, B2FW fixes noisy against OFF (3.00 -> 0.68 A RMS) and passes affine. Pedestal, integer and
  fractional still fail, because they need the global fixes in UP (DC zeroing plus the coupled peak).
- UP+FW passed zero, integer, fractional, affine and pedestal earlier.

## K267 eight cases (unchanged scorer, runtime and STAR; OFF = the plain-base OFF from 6132f664, reused)
- A1: zero, integer, fractional, affine and pedestal all PASS (0.20/0.40/0.80 A) in both runtime and STAR.
- A2: noisy under ALL is better than plain OFF on RMS, p95 and max. It is also reported against UP, UPFW and B2FW,
  with no threshold on those comparisons.
- A3: flat and repeated stay UNIDENTIFIABLE. Integer and fractional under ALL equal UP+FW, because local flags do not
  touch global-only cases.

## Census (100 Mac replicate movies)
- A4: ALL in-model passes >= B2FW in-model passes. If B2FW is not yet available, compare against B2's 68.
- A5: zero OFF-pass to ALL-fail movies. Every ALL-fail movie that passes under B2 or B2FW is listed.
- A6: pedestal32 under ALL is reported against B2/B2FW. UP's effect at scale is expected only on pedestal32.

## Falsification
If A1 or A5 fails, ALL is not a contract candidate.
