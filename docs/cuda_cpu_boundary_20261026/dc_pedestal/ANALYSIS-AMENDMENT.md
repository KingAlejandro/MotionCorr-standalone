# Local serialization-only repair

The first local analysis generated all16double actual-spectrum maps and all16
post-map-negative arrays, then JSON serialization rejected NumPy bool scalars.
Retain its source as analyze_control_v1.py and its analysis.log/analysis.exit1.
No native process failed, and no H_DC aggregate was published from that attempt.

The amended analysis serializes NumPy scalar values explicitly. Run with
--reuse-retained-reference-arrays: read the already-produced16double maps,
recompute the small peak/direct-sum ledger, verify all32retained array bytes
against the recomputed/output buffers, and emit ANALYSIS-v2.json exclusively.
No actual-spectrum NumPy FFT is repeated; no native inverse is repeated.
Tiny analytic normalization controls and local peak/direct-sum arithmetic are
checked again. This is a packaging repair, not a new selection/threshold/run.


## Exact baseline arithmetic repair

The retained v2 grade serialized successfully but reported71/80checks; eight
exact baseline peak comparisons and the exact frozen maximum failed. Cause:
the analysis computed `(integer+offset)*(pnx/ccf_nx)` instead of the sealed
`(integer+offset)*pnx/ccf_nx` evaluation order, causing about1e-15px rounding
differences. Its Euclidean norm implementation was also aligned to the frozen
math.hypot calculation. Keep v2source/report/log unchanged.

v3 restores the sealed evaluation order and norm; it does not loosen a check or
alter the frozen prediction. It reuses the same already-generated16double maps
and verifies all32retained reference/postmap arrays without any actual-spectrum
FFT or native replay repeat. It emits ANALYSIS-v3.json. The analysis failures
are separate from H_DC's ratio/integer predicates and from native execution.
