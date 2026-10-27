# Fixed-global noisy/noiseless comparison — auxiliary bridge result

Under two declared single-total-G NumPy bridges, removing additive pixel noise makes every noiseless pairwise term favor the fixed physical scoring point over the captured remote point. This is a conditional bridge result, not native noise causation, global optimality or estimator acceptance.

The original noisy/affine movies have identical target and truth hashes, and their pixel difference reproduces the declared noise stream within float32 rounding. The noisy bridge matches the captured samples to ≤4.8e-5 and its measured objective-gap error falls inside the worker's reported control-only bound. A different input is not covered by that native-control bound: the native per-global-iteration shifts were not captured, whereas these bridges apply one total G. No native noiseless run was performed.

At bad patch (62,79), frame4 iteration1, the B64 aggregate fixed-point gap changes from +0.0388807 (noisy) to −0.3673998 (noiseless). The frame0 term changes +0.0382569→−0.0930491. The frame3 term was already negative and becomes more negative; it does not reverse sign. [Parent qualifications](REPORT.md) correct this wording and the original overly broad “all gates FAIL” sentence. No existing gate status changes.

## Independent check

[verify.py](verify.py) independently evaluates the B64 global shift/crop/FFT and 16 pairwise gaps. [Verified result](VERIFIED.json) matches the original within 1.95e-16 raw objective units. It also checks all 61,440 noise differences against float32 rounding. The parent does not independently audit B32, the worker's spectral error bounds or local candidate searches.

## Provenance, original records and reproduction

- Capture source: 927a6890c8864f81ad58e44eac7281b080714af4; unchanged sealed primary package 63d73581. Capture index SHA256 5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3; [primary evidence index](../local_ccf_capture_20261026/EVIDENCE_INDEX.json).
- Worker: claudeAgent / claude-sonnet-5-5 / effort high. Original PLAN and pre-twin qualifications are unchanged; the original stopped precondition-check attempt and both script versions remain under [original/](original/ATTEMPTS.md).
- Full original archive: `/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Noise-twin-parent-review-r1/original/`, 28 files/1,011,449 bytes, copied and hash-verified. [COPY_INDEX.json](COPY_INDEX.json) binds every original file. Raw MRCs and duplicate source blobs stay outside Git. The original SHA256SUMS is retained verbatim; it verifies against that full external archive, not this intentionally compact subset. This package's own manifest covers all included files.
- Independent parent verification inputs: the pinned original movies at `/tmp/mc-local-ccf-noise-twin-bridge-20261026/inputs/`, source capture bundle, and parent Fourier-series functions. Those same bytes also exist in the full original archive above. To reproduce after scratch expiry, supply/copy the indexed input tree at the documented path; do not overwrite the original result files. Run the copied parent verifier from a separate output scratch with absolute existing Python, `-B`, OPENBLAS_NUM_THREADS=1 and OMP_NUM_THREADS=1.
- Parent Python/NumPy2.4.2; no native/GPU/FFTW run, alignment, fitting, source/default/ROI/gauge/tolerance change or reserved-data exposure. Historical failures and NO-GO decisions remain.
