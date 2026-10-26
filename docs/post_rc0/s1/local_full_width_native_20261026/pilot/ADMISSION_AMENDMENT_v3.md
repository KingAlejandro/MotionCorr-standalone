# Admission amendment v3 (additive; PLAN.md, ADMISSION_DRAFT.json and COMMANDS_DRAFT.json are unchanged)

Status: HELD. No producer exists or has run. `ADMISSION_DRAFT_v3.json` (version v3) supersedes `ADMISSION_DRAFT.json` by
hash only for admission-consumer purposes; the scientific design in PLAN.md is untouched. The final Linux binary, source
archive, compiler/config, shared libraries, venue identity and lease fields stay null.

## What v3 adds (Opus review M1, L1-L4)
- `score_fields_v3.admit_producer`/`score_admitted` bind one run directory to its case and arm, the exact argv (the flag
  exactly once for ON, never for OFF), the exact declared MC/OMP/BLAS environment plus the observed controlled child
  environment, the cwd, a staged cwd of exactly `<case>.star` and `<case>.mrcs` at the pinned bytes, a complete
  `output/` inventory equal to the receipt and to the case's baseline names, receipt-bound `runtime.json` and
  `stdout.log` bytes, and the log witness in `output/<case>.log` (strict `x_norm = 42, pnx = 42, nfx = 22`; exactly 9 on 3x3
  ON, 0 otherwise). A draft row whose argv[0] is `<PINNED_LINUX_BINARY>` is not admissible; only a row resolved with an
  explicit binary path and 64-hex sha256 is.
- Scoring is bound to manifest `9697c203...02dc`, the fixed ROI `[12,84,12,116]`, the case's own truth file name and STAR
  (`_rlnMicrographMovieName` stem equals the case). `field_metrics_lowlevel` (= v2 `field_metrics`) stays metadata-only.
- Admission pins now include the comparator `compare_products.py` (`53449d2d...5f0f47`), the six transitive consumer and
  generator files, `score_fields_v2.py`, `score_fields_v3.py`, the v3 tests and builders, lane.py and factorial_common.py,
  each with an explicit root (`consumer_source`, `repo`, `pilot`). `verify_tool_pins` rechecks them at supplied roots.

## Deviations from the retained producers, now named
1. Staged two-file cwd: the retained producers ran with cwd = the full 33-file fixture directory; the pilot stages only
   `<case>.star` and `<case>.mrcs`. Gated products should not depend on the extra files (compare_products normalises
   the output root), but this is unproven locally; the OFF compatibility gate decides it.
2. New output root (`/tmp/motioncorr-local-full-width-native-20261026/evidence` in the draft, re-rooted at admission).
3. Source baseline: the retained UP_only binary was built from production `326f03a0` (sha256 `531a1b09...c2eb`); the
   candidate is `634e4b48` (src unchanged at branch head `215c37b0`). The difference is default-off by design, but OFF
   byte-compatibility with the retained baseline is an empirical gate, not an assumption.

## Stop rule
If source identity or OFF compatibility fails for a case, stop before that case's ON producer
(`score_fields_v3.on_launch_permitted(off_compat, source_identity)` is True only for PASS/PASS). No retry.

## Limits that remain
`runtime.json` content is not self-identifying: it is bound to the case by the receipt hash, the declared
`MC_DIAG_MODEL_OUT` path under the canonical run directory and the producer, not by its bytes. The v3 tests use fake
files plus the retained noisy runtime/STAR/truth; they establish consumer logic only. No native run, estimator
accuracy, byte neutrality or scientific acceptance follows.
