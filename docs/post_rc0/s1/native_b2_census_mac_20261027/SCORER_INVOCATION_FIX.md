# Mac replicate census, not hash-identical to the frozen census

The first dose1-s00 OFF native producer exited 0 and published its outputs.
Its first scoring invocation exited 1 before analysis: Python `-I` removed the
script directory, so the unchanged evaluator could not import its sibling
`check_motion_diagnostics`. The original STOP, score invocation and traceback
are retained in `replicate_failures/` and in the raw run tree.

The wrapper is corrected to call the unchanged evaluator exactly as the pilot
did, without `-I`. No evaluator, tolerance, ROI, truth, source, binary or native
argv changes. The first OFF native result and generated movie are reused only
after checking their recorded receipt/product/binary hashes. The new score is
versioned `SCORE-v2.json` / `score-v2.stdout`; the first failed score is retained.
All subsequent native producers remain single-attempt. Predictions are unchanged.

The one-time `--resume-first-score` continuation is restricted to this exact
STOP, zero complete movie rows, and exactly one existing native OFF directory.
It does not permit an arbitrary native retry. The stopped runner is retained
in git commit `3f6e1bea`; the correction is committed before continuation.
