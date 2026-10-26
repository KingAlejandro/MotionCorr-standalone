# Diagnosis of the r1 STOP (saved files only; the frozen STOP stands)

Confirmed halt: no ON, no retry, no new source or criteria; 1 of the global 16 launches is used. Owned state after the run: no lane/driver/MotionCorr/comparator process, no flock entry on any of the 8 lock inodes,
namespace `/tmp/motioncorr-lfw-v5-20261026` (423 MB) intact, nothing running locally.

- Raw checks the gate had already passed: OFF `runtime.json` and `noisy.star` are byte-identical to the retained baseline and to their pins (`diagnosis/DIAGNOSIS_BYTES.txt` section 1).
- All 10 products, baseline vs OFF: `noisy.mrc` header bytes 0-223 equal, float32 payload `array_equal` (12288 values, max|diff| 0.0, no NaN), only the timestamp label block differs (not gated); `noisy.star` and the three accumulated-motion EPS byte-equal.
  `corrected_micrographs.star` and `noisy_shifts.eps` differ in exactly 2 lines each, and those lines differ only in the embedded output root. `logfile.pdf` (dates), `logfile.pdf.lst` (root path), `noisy.log` (timings, root) are inventory-only.
- Cause: the baseline files embed the ORIGINAL scratch root `/tmp/motioncorr-b2-factorial-20261026/evidence/runs/noisy/UP_only/output` (0 files embed the durable path). The gate passed the durable copy path as comparator root A, so the comparator's root normalisation did
  not touch the baseline side. All 8 baseline cases embed their original root in `corrected_micrographs.star`, `<case>_shifts.eps`, `.lst` and `.log` and none embed the durable path (`diagnosis/diag_remote_state.txt`), so every case's gate would have failed the same way.
- Proof with the unchanged pinned comparator on the same saved trees (read-only, under the lane, trees hashed before and after): root A = durable copy gives DIFFERENT (2 files, rc 1, reproducing the STOP); root A = the baseline copy at the original scratch root gives
  **IDENTICAL, 7 gated products, 0 differing, rc 0** (`diagnosis/diag-comparator-r1/`). The task copy and the durable copy are byte-identical (all 152 pinned bytes).
- Not a science, field or image difference. The original STOP is not promoted or waived.
