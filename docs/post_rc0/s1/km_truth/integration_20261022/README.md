# PR267 → PR269 local integration, 2026-10-22

This is local integration and retained-estimate replay evidence. It does not
rerun or requalify the historical 100-movie, 900-native-arm campaign.

The fresh T3 worktree began clean at
`c8844894c7c6366abf297699b5312e4b775eb5b0`, on
`integrate-pr267-into-pr269`. Live PR267/269 metadata, both PR discussions and
issues #238/#262 with their latest discussion were read. Both fetched heads
matched the requested identities; no head drift was found. The branch was
fast-forwarded to PR269 before the normal, conflict-free parent merge.

- PR269 starting head: `677abcfab0b55cf8c64ae511369a863383b21a59`.
- Parent PR267 head: `6695241523d7285d4f0480abf1c4a2c6423c3617`.
- Merge: `d38400c3588ca69cdcb1ac0a4c1e875c5c0152cf`, with those two parents
  in that order. No rebase or force operation.
- Consumer-control commit: `31a7fecc9a883766084d9b3b7009fa0f18784856`.
- PR269 target remains `test/known-motion-diagnostics-v2` (parent branch);
  remote source branch remains `test/realistic-motion-truth`. Nothing pushed.

## Consumer contract

The inherited v2 checker emits field metrics for finite estimates outside the
fixed ROI, `sampling_status=OUTSIDE_FIXED_ROI`, and JSON null for
`signal.estimated_motion_bilinear`. Its CLI writes the report then exits 1;
malformed/nonfinite inputs still exit 2. Truth, ROI, thresholds, sign and gauge
are unchanged. The parent's checker, tests and documentation were retained
byte for byte.

PR269 imports only `validate_star_rows` and `vector_metrics` from that checker.
Both function bodies and signatures remain identical to the old composition;
the `evaluate` and `check_case` signatures also remain identical. The realistic
checker and its historical analysis scripts do not consume v2's signal map or
CLI exit. They already retain field diagnostics and their own sampling status.
The field-only realistic CLI intentionally retains exit 0 for valid finite
characterization inputs, including outside-ROI estimates, and fails nonfinite
inputs without a new report. Its signal-transfer result stays UNRUN.

Three new controls exercise the actual PR269 evaluator with a STAR adapter,
the actual CLI and its JSON/exit/nonfinite behavior, and the actual summarizer.
The summary control supplies 90 explicitly synthetic records (one condition,
ten seeds, nine arms); invalid sampling, failed field limits and nonconvergence
remain independently counted. No estimator, image-metric or summary behavior
needed modification. The existing ten controls remain intact.

## Local validation

Checks ran sequentially on macOS 26.7.1 arm64, Python 3.13.7, NumPy 2.4.2
(SciPy 1.17.1 for the existing synthesis test), with the existing explicit
`/Users/alex.konstantinov/.local/bin/python3`. Occupancy and free space were
checked first: load averages 12.44/11.48/14.07, about 35 GiB available; visible
load was primarily desktop/security services. No other process was modified.
All five numerical thread controls below were 1; no parallel test workers ran.
The controls were executed on merge `d38400c3` plus the test contents now
committed as `31a7fecc`; the composition replay was also run at `31a7fecc`.

```sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
/Users/alex.konstantinov/.local/bin/python3 tools/test_realistic_motion.py -v
/Users/alex.konstantinov/.local/bin/python3 tools/test_motion_diagnostics.py -v
/Users/alex.konstantinov/.local/bin/python3 tools/test_known_motion_verdicts.py -v
/Users/alex.konstantinov/.local/bin/python3 tools/test_known_motion_runner.py -v
/Users/alex.konstantinov/.local/bin/python3 \
  docs/post_rc0/s1/km_truth/integration_20261022/verify_composition.py \
  --outdir /tmp/motioncorr-pr269-integration-20261022-a836b1e8-committed
/Users/alex.konstantinov/.local/bin/python3 -m py_compile \
  tools/test_realistic_motion.py \
  docs/post_rc0/s1/km_truth/integration_20261022/verify_composition.py \
  tools/check_motion_diagnostics.py tools/check_realistic_motion.py \
  tools/summarize_realistic_motion.py
git diff --check
```

All four suites PASS: **13/13 + 11/11 + 8/8 + 8/8**. Python compilation and
whitespace checks PASS. Focused unittest collection finds all 13 realistic
controls; CI already invokes this file, so no collection/workflow change was
needed. CMake/CTest, builds, native CPU/CUDA execution and integration-head CI
are **UNRUN** in this task.

[Composition and replay results](RESULT.json) record source identities, input
hashes, environment, individual STAR results and collection. The reproducible
script refuses an existing output directory and only writes fresh local scratch.

- All 32 valid v2 reports (eight cases × truth/zero/sign/offset) exactly match
  the old checker after removing the additive `sampling_status`.
- The old checker negative control still aborts on finite outside-ROI sampling.
- All 16 retained native STAR estimates emit reports. CPU noisy/repeated and
  CUDA repeated now give exit 1, outside-ROI status and null candidate image
  metrics. Field metrics agree with the separately retained historical metrics
  at 1e-12 relative/absolute comparison precision; acceptance limits are unchanged.
- Every file in the v2 archive is verified against its original index before
  retained STAR bytes are copied. Replay uses locally regenerated, versioned v2
  fixtures; their manifest hash is recorded. This is a replay of old estimates
  with regenerated inputs, not an original-byte movie replay or new motion run.
- All 50 other PR269-added/changed files match the old head byte for byte,
  including every historical recipe, command, receipt, metric, source identity,
  report, archive and index. Production `src` has no diff against the old head.

## Dependent PR272 handoff and limits

Integrate the resulting local PR269 branch head into PR272 normally when its
owner assigns that task. PR272 has not been modified here. The v2 null/status/
exit contract above is now present in the parent composition; PR272's actual
wrapper and fallback still need their own integration controls. The historical
900-arm native source identities remain those in the original provenance files.

The measured pedestal-32 benefit remains historical evidence: both/double
still fail 9/10 unchanged field gates, out-of-model cases fail 10/10, and shared
nonconvergence #268 stays FILE-ONLY. S1, downstream scientific outcomes,
frequency transfer and controlled performance remain open/unqualified. There
was no native estimator run, remote campaign, GPU use, push, merge to main,
GitHub comment or Notion action in this integration.
