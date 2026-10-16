# #194: native staging for raw integer MRC movies

Candidate `a414ec25` (#194 merged with main `4b849165`) against main `4b849165`. 4GPUs A100 (GPU-eddb42fe, lane 96-103, `--j 8`), Release, CUDA 12.8, nvCOMP 5.3, inputs in tmpfs (`.mrcs` links). Config L: `--patch_x 5 --patch_y 5`.

Options: `--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --expected_frames <8|59> --patch_x 5 --patch_y 5 --gpu 0 --j 8 --ingest_witness <file>`. EER: dose 1.282051282051282, 39 frames, `--gainref gain.gain --eer_grouping 49 --eer_upsampling 1`. `mcprof compare main cand`, 1 warmup, 8 pairs (EER: 2 pairs, identity only).

| input | SHA-256 |
|---|---|
| EMPIAR-10164 `data/frames/TS_01_000_0.0.mrc` (mode 0) | 117c303163480aa6bd3a1c1298c5635486dd077babce770dfcaf4ca944245039 |
| EMPIAR-10164 `data/frames/TS_01_020_30.0.mrc` | e6780acb0df21aae077fb9a5fdaf80a1553cd0fb4a339482aa59799b2642029d |
| EMPIAR-10216 `..._1739_Fractions.mrc` (mode 1) | f399bd30bfe1a9807bd494c348bfcf7d4aee312ccc18140b05abb1453ac23a56 |
| EMPIAR-10216 `..._1742_Fractions.mrc` | c3b841e9ebcfb1e734a93c7bd7511033ded98c82b5c1cdb123f17e669e165ca1 |
| EMPIAR-12963 `..._014501_EER.eer` | 3fc5feb61f487f0f4f6ec1317ae033138fe50e7da80e3b5b16bab3aaff2403f5 |
| EMPIAR-12963 `20230326_221855_EER_GainReference.gain` | 6d4f3e5f9a6b837c637dc7098420e1c0cdfbbd61c9305a7780568f67c7134050 |

| family | identity | wall main → cand (median) | paired B-A | peak RSS main → cand |
|---|---|---|---|---|
| 10164, mode 0, 8 fr, 2 movies | PASS (12 files, 2 MRC) | 3.132 → 2.471 s | -0.637 s (-20.3%), resolved | 2263 → 1182 MiB |
| 10216, mode 1, 59 fr, 2 movies | PASS (12 files, 2 MRC) | 6.378 → 5.106 s | -1.281 s (-20.1%), resolved | 4180 → 2325 MiB |
| 12963, EER, 39 fr, 1 movie | PASS (9 files, 1 MRC) | no verdict (2 pairs) | - | - |

Witness: 10164 and 10216 write `compact` for cand and `float` for main. 12963 writes `compact` for both arms (main has #196's EER route), so the compare shows the merge left EER products unchanged.

`ctest-full-summary.txt`: 84 of 85 pass, including `SignedMrcStaging` and `CudaU16StagingEquivalence`. `CiFailClosedControls` test_6 fails because this tree is a `git archive` without `.git`, with the same message on main.

The first version of this evidence (candidate `ae25a714` against `116eb04a`) ran without patches, so it was global-only, not config L. This revision replaces it. The 4GPUs host was shared (foreign CPU on the lane <= 0.01 cores). Identity is checked on round 1 only.
