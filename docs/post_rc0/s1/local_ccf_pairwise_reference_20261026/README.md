# Fixed-state pairwise reference decomposition (qualified result)

This additive follow-up uses the sealed two-patch capture at production source `927a6890`, package `63d73581`. It performs no native job, estimator change or source modification. Runtime/STAR truth limits and all historical failures remain unchanged.

The eight fixed-point objective gaps independently reproduce. On bad patch `(62,79)`, frame4 iteration1, reference frames0–3 contribute `+0.0382561`, `+0.0153357`, `+0.0001590`, `-0.0148743` to the native-selected-point minus physical-scoring-point objective gap. The aggregate is `+0.0388766`; the native-map remainder is about `-5.60e-8`. Thus frame0 contributes the largest positive term while frame3 opposes the remote point. These are conditional raw objective differences, not causal or variance shares.

**Read [parent review](REPORT.md) before the original report.** The original report section3 contains incorrect G values and an unsupported causal explanation of boundary/window mismatch. The script uses the correct captured G, and the numerical table reproduces. The original files/manifests are preserved unchanged under [original/](original/REPORT.md); the additive parent review supersedes that discussion. No global optimality or physical peak certification follows.

A proposed noiseless comparison is UNRUN. It must verify identical scene/truth and hold the exact captured global trajectory, preprocessing and crop fixed, first reproducing the noisy captured state. Independently aligned noisy/noiseless outputs would not isolate noise. No temporal-reference pruning or estimator adoption is authorized by this result.

## Provenance and reproduction

- Capture bundle index SHA256: `5b3dde3aefa3ff647927cbf702b3489fc1a470083fbcc23644bb8eb2f191c8d3`. Local immutable source: `/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Local-CCF-native-capture-r1/native-map-bundle-r1/`. Durable primary capture: `cpu64:/home/ubuntu/motioncorr-evidence/local-ccf-native-20261026/`; [primary evidence index](../local_ccf_capture_20261026/EVIDENCE_INDEX.json).
- Original saved-only plan, code, JSON and report: [original manifest](original/SHA256SUMS), verified all four entries. Worker model: `pi_gpt_vertex / claude-unified/gemini-4-argon / thinking high`, verified from T3 task identity.
- Independent parent: [verify.py](verify.py), [VERIFIED.json](VERIFIED.json), [execution stdout](stdout.log), NumPy2.4.2, existing absolute Python, BLAS/OpenMP caps1. This independently checks eight fixed-point gaps and map closure, not the original component/leave-one-out peak searches.
- Run from this directory with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /Users/alex.konstantinov/.local/bin/python3 -B verify.py`; input paths are intentionally pinned to the durable local capture bundle. Original worker script has its own immutable input/output paths; do not rerun it to overwrite the preserved result.
- No source/tests/CMake, native output, primary package or old manifest was edited. No native/GPU/FFTW run, fitting, image-pixel analysis, timing, held-out exposure, M1 or adoption claim.
