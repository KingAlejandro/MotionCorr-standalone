# Default-off local full-width CCF weight (CPU prototype)

`--experimental_local_full_width_weight`: with the flag on, patch alignments divide the CCF weight's x frequency by the
full patch width `pnx` instead of `pnx/2+1`; global alignment, defaults and publication are unchanged. CPU `--use_own`
only. See `DESIGN.md` for the design, test criteria and local results, and `EVIDENCE_INDEX.md` for pins, hashes and
limitations. Status: source reviewed (conditional, source-only clearance) and host-tested on a limited scope; no native
run, no scientific claim, no adoption.
