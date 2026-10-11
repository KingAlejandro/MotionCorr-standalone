# Strict complete-report paths

Aggregate-only supplies literal EPS filenames in the original movie order.
Strict `joinMultipleEPSIntoSinglePDF` checks each requested literal path and
passes exactly that sequence to Ghostscript. It does not interpret movie-name
brackets or other glob metacharacters. Non-strict existing callers retain their
wildcard behavior.

The actual-binary `test_aggregate_only.py` controls cover a bracketed filename
with only its literal plot, a stale plot matching its glob interpretation, and
a missing literal even when that stale match exists. The first two fail on the
retained predecessor; missing-literal refusal was already protected by initial
preflight and remains a required control. Hashes and mtimes prove no movie
rewriting. Explicit fake Ghostscript tests the production input-list selection
and failure wiring only; full real-rendered content acceptance remains separate.
