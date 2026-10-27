# Next observation (DRAFT proposal; nothing here has been run or authorized)

Status: draft for the parent. No execution, no code, no new arm, no fitter tuning, no optimization. The parent decides whether any of it happens.

## Question
After the B2 cross-feed screen (NOT_A_CANDIDATE), where does the remaining noisy-case error sit under current full-width, and is it in the accepted patch observations or in what the operator does with them?

## Smallest diagnostic: saved metadata only
Use only files already saved: the native OFF/ON `runtime.json` and STAR local observations (staged copies are in the durable archive, `out/stage1_staged_manifest.json` lists them), the sealed stage-1 and stage-2 outputs, and the exposed truth/global for the same cases. Tabulate, for each accepted patch (noisy: 8, affine/pedestal: 9; the excluded noisy patch (2,3) is listed as excluded, not imputed) and each frame:

- the observed patch shift (old weight and full-width);
- the unchanged truth at the patch centre and the unchanged global (the fixed runtime G);
- the difference observation − (truth − global), old versus full-width.

Report per-patch, per-frame and per-spatial-position concentrations (rms, max, signed mean) for both weights, next to the already sealed fitted-field errors. This is a table. It fits nothing and adds no gate.

## Two gauges, reported separately
1. Operator Tr: the observation frame as the existing W8/B2 operator consumes it (its own time convention and nuisance intercepts).
2. Physical/reporting gauge: frame-0-referenced h(f) with h(0)=0, as used for scoring.

Do not combine them into one column. If the two disagree on where the error concentrates, say so; do not choose between them.

## Pre-declare before any computation
Pins (file hashes), the case list, the column definitions and "descriptive only, no thresholds, no pass/fail" in a short frozen note, as the screen did. One noisy realization: no independence, p-value or generalization claim; offsets or correlations with truth origin are not causal evidence.

## Out of scope: any new full-width CCF capture
The current capture path (`MC_DIAG_LOCAL_CCF_DIR`, `src/motioncorr_runner.cpp` scope check) refuses `--experimental_local_full_width_weight`. Capturing full-width CCF states would need a separate, explicit guard amendment and its own source review. This proposal does not request it. Old-weight CCF states already saved must not be silently mixed with full-width observations; every table row carries its weight arm.

## What this can and cannot show
It can show whether the residual is already present in the accepted observations (before any fit) or appears in the fit. It cannot show a cause, cannot justify a new arm, and cannot change NOT_A_CANDIDATE or the old noisy harm.
