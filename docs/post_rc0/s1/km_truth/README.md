# Motion-truth census (#238 / #262)

Status: **RUNNING**, 2026-10-21. No production repair or merge. The generator
extension is based on #267 `88b34ae0` and targets its branch
`test/known-motion-diagnostics-v2`. The prospective protocol is [DESIGN.md](DESIGN.md).

Measured main `36913740` native results: all eight v2 cases completed on CPU
and A100 CUDA, Release `-O3`, eight pinned CPUs/process. Zero passes. Integer,
fractional, affine and pedestal fail the existing field gate on both backends.
Noisy fails accuracy; original checker aborts on CPU noisy and both repeated
estimates because their finite sampling coordinates leave the fixed ROI.
Flat/repeated are unidentifiable characterization cases. No process exit is
used as an accuracy verdict. Per-case px/Å RMS/P95/max and global iteration
outcomes are in the [table](native_v2_table.md) and [JSON](native_v2_metrics.json). Raw checker
outputs remain separate from independent field-only metrics for checker errors.

The original checker/adapter problem was reported on
[#267](https://github.com/KingAlejandro/MotionCorr-standalone/pull/267#issuecomment-6314920945).
Its fixed ROI and gates were not relaxed. Historical `km_local_noisy` accuracy
FAIL remains characterization in `docs/known_motion_validation.md`; it is not
superseded by an OVERALL PASS or by these new fixtures.

Native 512×384×5 noiseless controls recover zero exactly. Direct MRC and a TIFF
written with reversed rows produce identical translation trajectories: RMS
0.0573613 px, P95/max 0.0960452 px. A TIFF row-order mutant gives RMS 9.85013 px,
max 16.0885 px. This validates the sign/orientation adapter before large movies.

Large-frame source is diagnostic `97fd81070566af0358ccc839b6804a99b6bf52c1`,
combining #254+#260. The retained `capture_runtime_model.patch` only observes
pre-write global trajectories and polynomial coefficients at 17 digits, after
model admission/rejection. It changes no numerical arm or production file in
this PR. Source overlay and binary hashes are retained separately.

The realistic census is still running. No condition-level accuracy or #262
recommendation is established yet. Planned: 100 seeded movies, nine arms each,
plus double/both numerical offset controls. Frequency transfer and held-out
scientific outcomes are unrun. These weak-texture Poisson fixtures are a
counting-statistics proxy without CTF/damage/MTF, not experimental micrographs.

## Reproduction

Requirements: NumPy, SciPy for oversampled synthesis; native Release MotionCorr
with the separately published diagnostic branch/observation patch for the census.
No external movie download or simulator source is needed. SciPy uses its
BSD license; no simulator code is vendored into the GPL-2.0-or-later project.

```sh
OPENBLAS_NUM_THREADS=1 python3 tools/test_realistic_motion.py -v
python3 test-data/generate_realistic_motion.py --condition dose1 \
  --expectation /scratch/inmodel.npy --make-expectation
python3 test-data/generate_realistic_motion.py --condition dose1 --seed 0 \
  --expectation /scratch/inmodel.npy --outdir /scratch/fixtures/dose1-s00
python3 tools/run_realistic_motion_census.py --root /scratch \
  --binary /absolute/diagnostic-build/motioncorr --backend cpu --cpus 0-7
```

The runner expects `/scratch/fixtures/<condition>-sNN/RECEIPT.json`; a receipt
is written last. Generate/transfer fixtures there, retaining manifest/hash checks.
The host-specific campaign/transfer scripts show the actual orchestration.
Movies remain on 4GPUs under `/mnt/clathrin/alex-motioncorr-km-truth/fixtures/`.
Only hash-verified cpu64 duplicates become eligible for cleanup after all CPU
arms finish; receipts remain. No movies are committed.

For one output, run `tools/check_realistic_motion.py` with `--receipt`,
`--runtime`, `--star`, `--log`, `--json`. This evaluates a fixed spatial lattice
and keeps total, global, local, border, time, convergence and STAR-roundtrip
statistics distinct. `tools/summarize_realistic_motion.py` refuses an incomplete
100×9 census and computes paired seed statistics and CPU/CUDA/reference distances.

Completed infrastructure checks at `59ccaa43`: Linux CI
[run 39595686283](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/39595686283)
passed. The observation hook's on/off native control preserves MRC core header,
payload and serialized STAR exactly; timestamp labels are excluded explicitly.
The diagnostic branch later added its own model hook at `afba50a4`; source diff
from the pinned numerical snapshot is observation-only. This census keeps its
original `97fd8107` plus retained JSON observation overlay throughout.
