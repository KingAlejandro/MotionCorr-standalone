# cpu1b: CPU-only qualification plan, version b (supersedes the unlaunched cpu1)

The independent review of the frozen `cpu1` plan found fail-closed gaps in its helper before any launch: `decide` accepted any non-empty F control set and ignored the control's own native exits; `v2check` could treat two missing keys as equal.
`cpu1b` keeps the same rows, source (`e77a51a2`), binaries, tools packet `4facd76d` and decision rules, and changes only the evidence helper and the chain that calls it:

* expected identities are frozen in `cpu1b-identities.json` (100 sorted unique fixture names; the 10 control movies `dose1-s00..09`); every result set must equal its identity set exactly, with no missing, extra or duplicate identity;
* every native `RUN.json` must have exit 0, the expected binary sha256 (C1 CPU or frozen-F CPU) and be bound to its fixture (movie hash equals the fixture receipt);
* `decide` recomputes every comparison instead of trusting a stale comparison file, and validates the F control's own runs;
* `v2check` requires exactly the 8 expected cases in order, all required keys, `dc == unset`, native exit 0, and compares missing keys as a sentinel (never `None == None`);
* the prerequisite checker no longer counts the first stage's own receipts as a stale stage name (a latent defect in the old prerequisite that would have stopped the chain at its first stage).

Tests: `test_cpu1b_sums.py` (18): ordinary valid controls and negatives for partial / wrong-name / extra sets, nonzero or foreign-binary or unbound runs, malformed identity files, a partial one-row F control, a wrong-name F control, a nonzero F run with an existing sum, missing/one-sided v2 keys, wrong case names/count/order.
No GPU, build, or source change. The old `cpu1` freeze and preflight are retained, unlaunched.
