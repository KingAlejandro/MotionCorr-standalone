# cpu1c: CPU-only qualification plan, version c (supersedes the unlaunched cpu1 and cpu1b)

Same rows, source (`e77a51a2`), binaries, tools packet `4facd76d`, lane (CPUs 8-9, no GPU) and decision rules as cpu1b, with these changes only (details in `review/CPU1B_R1_RESPONSE.md`):

* K267 `v2check` requires complete, finite field-metric dictionaries and the checker's own status/exit contract; equal checker ABORT rows (the parent's false-PASS control) are invalid. FAIL and UNIDENTIFIABLE truth outcomes remain valid evidence.
* Non-object or non-strict RUN files, non-finite or empty sums, bool/float/string exits and self-selected counts are invalid (exit 2 / 5), never a crash or a difference; JSON written with `allow_nan=False`.
* The documented INCONCLUSIVE K269 decision (exit 3) no longer stops the independent metrics and image rows (parent decision; the status is preserved, not a PASS); FAIL and INCOMPLETE still stop.
* Whole-chain `taskset -c 8-9` with recorded `Cpus_allowed_list`; deployed tools verified against a frozen git-derived manifest; the original F-cpu baseline runs pinned (binary, argv, cwd, mask, rc).

Files: `chain-cpu1c.sh`, `cpu1c_sums.py`, `cpu1c_prereq.py`, `test_cpu1c_sums.py` (19 tests), `review/` (R1 report verbatim and response), `parent-control/` (the parent's negative control).
