# Response to independent review round 2 (head 0a1f64ab)

`REVIEW.md` is the verbatim reviewer report, copied from
`/tmp/motioncorr-guard264-review-r2-20261022/REVIEW.md`, sha256
`cd7d0026fcd7a30cc1fedfd4cf298dfcc0b585050eb15aa9bfc5783b9223895d` (matches the reviewer's
`REVIEW.sha256`). The reviewer's scratch, clone, mutant scripts and logs stay in that directory.

- **F1, F2:** closed by the reviewer. No change.
- **F5:** accepted. Iteration-1 files and the live iteration-1 chain are untouched; if its candidate
  A rows fail on the printed value, that FAIL is retained. A separate N3-only iteration 2 is
  proposed and frozen in `../native/n3-iter2/FROZEN-ITER2.md`: A totals 3.5 (frame-10 stop at
  3.181818, 4.5% margin), unchanged decisions everywhere, and exact margin/perturbation controls
  that also detect the iteration-1 tie. Not launched.
- **F6:** `../README.md` gains a dated clarification and `../host_controls/INDEX.md` marks
  attempt01 INVALID. Attempt01's raw `model_controls.json` (including `all_expected: true`) is not
  edited. The stale `predict.py` comment is noted, not edited, because that file is frozen.
- **F3, F4:** carried unchanged. Non-finite models are accepted by both guards, which is out of scope.
  Maintainer sign-off for the intended RELION-parity difference is still missing.

No source, test, tool, gate, tolerance or default changed in this response.
