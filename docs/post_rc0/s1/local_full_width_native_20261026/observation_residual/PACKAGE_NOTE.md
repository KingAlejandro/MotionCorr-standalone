# Package note

Additive archive of the saved-metadata observation-residual diagnostic (`README.md` is the report) and the parent's independent check (`parent_check/`: own STAR parser, direct Tr/frame-0 formulas, independent 18-term basis, no author-code imports; 32 input pins verified, six observation-array sets bit-exact, fitted point fields within 4.45e-15 px).

Retained as recorded: the original freeze (`FREEZE.txt`), the failed first hand-array test attempt (`out/*.attempt1.*`, `ATTEMPTS.md`), and the post-freeze `supplementary.py` (labelled; concentration shares are descriptive, not causal). Paths in `PINS.json` and `FREEZE.txt` refer to the original working directory `/tmp/mc-lfw-observation-residual-20261027-r1` and the durable bundle. `MANIFEST.json` here is the original 22-file manifest of that directory; this package adds `parent_check/` and this note, so verify with `PACKAGE_SHA256SUMS`: `cd observation_residual && shasum -a 256 -c PACKAGE_SHA256SUMS`.

Durable originals under `~/Documents/MotionCorr-evidence/20261026/`: `Observation-residual-r1/` and `Observation-residual-parent-check-r1/`.
