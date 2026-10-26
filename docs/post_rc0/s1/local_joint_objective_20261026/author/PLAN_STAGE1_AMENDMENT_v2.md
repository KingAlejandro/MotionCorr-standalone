# PLAN_STAGE1_AMENDMENT_v2 (additive to PLAN_STAGE1.md; that file and stage1_v1.py are unchanged)

Prepared before any captured outcome. Still PROVISIONAL until the parent freezes; nothing executed on captured data; no controls rerun.
Control status unchanged: v1 C9 original FAIL stands; the v2 control relaxation is not accepted.
This amendment tightens the native linkage; it relaxes nothing. Runner: `stage1_v2.py` (v1 retained). The core `jointobj_core_v1.py` is unchanged.

## Changes relative to PLAN_STAGE1.md
1. **Closure A and B both gate.** For every captured entering iteration of each patch: A = |0.5*sum_f real-map[f][0,0] - J_direct(entering F)| <= 5e-6 and
   B = |J_ideal(initial spectra, s_enter) - J_direct(entering F)| <= 5e-6. A failure of either, on either patch or iteration, writes `closure_result.json`
   (with `closure_gate_detail` per patch) and exits with code 3 before any optimization. (v1 had B report-only.)
2. **New closure C (gates, same 5e-6 bound)**, per patch, using the LAST captured iteration L (the largest iteration present): 
   C = |J_ideal(initial spectra, final-local-shifts) - J_direct(actual iter-L exit spectra, s=0)| <= 5e-6, complex128, DC zero.
   Label: **phase-drift consistency only**. No native map exists at the final exit, so C does not tie J to a native CCF value; it ties the ideal-phase
   evaluation of the native final trajectory to the actually stored exit spectra. Frame 0 of final-local-shifts must be exactly 0. Also reported: whether
   final-local-shifts equals iter-L exit-shifts bitwise. `CLOSURE_C_GATES = True` is recorded in the result; the parent's instruction was read as "C gates"
   (admission), and reversing that needs a new version.
3. **Whitelist** gains `iter[12]-frame[0-4]-exit-fft.{bin,json}` only (the `truth` guard, INDEX sha256 verification and everything else are unchanged).
4. The clearance JSON must bind `stage1_v2.py` (key `stage1_sha256`), `jointobj_core_v1.py`, the chosen `plan_file`, `c9_disposition`, and
   `authorizes_captured_payload: true`. The runner can bind only one `plan_file`; the parent may bind this amendment or a merged frozen plan.

## Unchanged
Closure bound 5e-6 (objective units), remainders and sub-step diagnostics, vacuity guard (1 px perturbation must move J by >10x bound), the 11 starts, optimizer
settings, the 300 s total cap, highest-J selection, sealed output, and all failure/cap retention.

## Not done / for the parent
- C is applied only at the final state. The `native_iter1_exit` start is not covered by an iteration-1 exit analogue; adding it would be a further (non-requested) closure.
- If the frozen bound fails on captured data, no optimization is run and no bound is changed; the raw deltas are kept.
