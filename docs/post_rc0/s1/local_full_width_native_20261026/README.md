# Default-off local full-width CCF weight (CPU prototype)

`--experimental_local_full_width_weight`: with the flag on, patch alignments divide the CCF weight's x frequency by the
full patch width `pnx` instead of `pnx/2+1`; global alignment, defaults and publication are unchanged. CPU `--use_own`
only. See `DESIGN.md` for the design, test criteria and local results, and `EVIDENCE_INDEX.md` for pins, hashes and
limitations. Status: source reviewed (conditional, source-only clearance) and host-tested on a limited scope; no native
run, no scientific claim, no adoption.

## Pilot packet (added later, documentation only)
`pilot/` holds a snapshot of the HELD pilot design, scorer/pair-decision review tools (not a portable release), three independent
reviews and the access probes; see `pilot/README.md` and `pilot/FINAL_PACKET_INDEX.md`. Native execution, a producer driver and all
science/neutrality/harm results are UNRUN; the oracle value is an independent reproduction for two exposed affine fixtures only.

## B2 cross-feed offline screen (added later, documentation only)
`b2_crossfeed_screen/` holds the offline B2 + full-width counterfactual screen (status NOT_A_CANDIDATE: noisy case fails the unchanged limits), its independent audit and an additive audit disposition; see `b2_crossfeed_screen/README.md`. No native run or acceptance follows from it. `b2_crossfeed_screen/NEXT_OBSERVATION_PROPOSAL.md` is a draft only.
