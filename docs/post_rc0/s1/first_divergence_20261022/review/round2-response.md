# Parent response to independent Sonnet round 2

The review at 25e8261a found no blocking defect and closed F1–F8. Its F7 check
supports the author's source/output interpretation; keep the original Opus F7
and the correction visible. This response implements only R2-1 through R2-4.

- R2-1: rename the generated key to
  `iteration1_native_vs_double_map_parabola_px_max`; retain the historical
  offline script/output names and explain their meaning. The generator's
  self-hash changes, as required. No numerical metric changes.
- R2-4: state that 1.221 px measures native-map versus double-map use of the
  same parabola rule. The 0.576 px continuous comparison is frame 1 only;
  integer CPU frame 0 reaches 1.041 px. Neither is a truth error.
- R2-2: N=9 errors are 0.044/0.067 px after 50 iterations and N=13/20 approach
  zero; every production 50-iteration probe remains unconverged at 1e-9.
  README and generated ledger now distinguish small error from convergence.
- R2-3: identify the 11.8 px probe as fractional at N=20; the integer result
  is 0.041 px and only one of eight isotropic rows shows the large divergence.

Parent verification checks the exact serialized diff after normalizing only
those field/text changes and the separately validated generator self-hash.
All numbers, statuses, input bindings and raw native/manifest/offline/estimator
bytes are unchanged. No native process, GPU, source overlay, algorithm, gate,
threshold or original outcome was rerun/changed. The preserved independent
review is at `round2/REVIEW.md`; this mechanical check is not a new independent
native qualification or a recommendation to merge/adopt.
