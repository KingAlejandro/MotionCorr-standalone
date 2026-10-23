# v6.1 data-only addendum for R5

Tested source `2f32e7be4d75c4451d46fbef66a87540716f48c6`; amendment frozen first at `6c648839`.
[R5 response](../review-r5/RESPONSES-v6.1.md) covers scope and remaining objections.
The frozen v6 source, contracts, controls, prior results and README files are unchanged.

One new data-only iteration, `iteration-01-2f32e7be/`, retains:

- 17/17 static tests PASS, exit 0, including **exact K22** and synthetic K36.
- 11/11 frozen admission cases PASS against the v6.1 runner, exit 0.
- Focused K22/K36 and K28/K30 PASS with details in focused-controls.json.
- Two single-site mutants FAIL on exactly their intended test, exit 1 and no errors:
  `k22_own_group_exclusion_removed`, `late_observer_root_signal_removed`.
- All 15 replacement sets compile uniquely; the other 13 executions remain UNRUN on this source.

Commands/argv, in-process runpy invocation mode, exits, source/input/interpreter hashes, resources and
limits are in ATTEMPT.json and PREFLIGHT.json. `verify-data-only.py` is the exact driver. It uses one
interpreter with forbidden real Popen/signals and in-memory test overrides, never the process runner.
Focused controls are function calls, not the harness CLI. No worker/mock/query child is launched.
The driver's final JSON is the verdict; a diagnostic driver's exit 0 alone is insufficient.

K36 contrasts a healthy live-root view with errors arriving on refresh or during either result of
group verification. Healthy has two mocked signals, no fallback/errors; each late case has one
checked fallback, two mocked original-group signals and retained uncertainty. The checked fallback
AST remains unchanged, as recorded in REFERENCE-CHECKS.json. This is branch/identity evidence only.
The private scratch lease is resource discipline, not evidence of live-job lease lifetime.

Host macOS, 14 CPUs, numeric threads 1, no pinning; preflight load 8.59/9.05/7.79, free space 6.00 GB,
private nonblocking lifetime lease, 256 MiB cap, iteration data about 141 KiB. No new unexpected test
failure. R5's reviewer syntax FAIL and original v6 K22 failure remain in the byte-exact selected
review packet; that export is not duplicated. R5's report whitelist and the selected-copy whitelist
are kept separately.

SOURCE-HASHES.json and DIFF-v6-to-v6_1.patch bind the new counterparts to reviewed v6. HASHES.txt hashes
this packet, excluding itself. Raw unittest stdout retains its original trailing spaces; those bytes
are preserved. Authored source/docs pass scoped whitespace checking; whole-packet whitespace checks
are not claimed to pass.

Process suite remains UNRUN/unspent, provider binding unchanged and unavailable via Codex. Independent
R6 is required before any possible prospective process run. No process/native/SMI/Linux/GPU evidence;
GPU PAUSED, consumer unimplemented/BLOCKED, science/history unchanged.
