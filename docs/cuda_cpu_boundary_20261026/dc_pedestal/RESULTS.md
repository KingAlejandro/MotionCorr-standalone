# DC-pedestal control on stored valid spectra

**H_DC is supported on these eight stored maps.** Maximum CPU–CUDA recomputed raw-subpixel vector difference falls from **0.00965926905869 px to 4.57047233476e-06 px** (ratio 0.000473169585295, 2113.40718228× reduction), below the frozen limit 0.000965926905869 px. No integer peak changes on any of the sixteen backend/input pairs. This is a bounded arithmetic/operator result, not a production, motion-truth, image-preservation or parity acceptance.

Producer-reported final controls: **80/80 PASS**, **8/8 inverse processes exit 0**. Collection verifies an exact 8 RUN ↔ 8 ADMISSION ↔ 8 START correspondence, input immutability and output hashes. The independent sealed-boundary result audit belongs to the parent; this follow-up does not duplicate it or present itself as an independent audit.

## Frozen scope and reproducibility

- Preregistered before new outcomes: `d10045e5cd4324eba62e189e5ffd256b42399557`, [plan](PLAN.md), [pins](FROZEN-PINS.json). Exactly 00021/00046 × CPU/CUDA-source valid spectra, each frames 0/4. Four source sets are not eight independent movies or a new validation cohort.
- Original spectra and original v2 maps are retained. Unmodified copies and separate zero-DC copies exist. Exactly the first 8 bytes (complex ky=0,kx=0) change to (+0,+0); every other byte and geometry is identical. All eight original/zero inputs are finite and exactly Hermitian-valid. [Input witnesses](evidence/INPUTS.json).
- No build or production-code change: existing source `031f333a2863218c74951117989c84423ad9c92e`, replay binary SHA256 `4970be307aad38034c0ae1e36537d00d6fb9cca9c28ae81663e4b79edf0018f1`. Explicit complex-zero initialization of all 24 CUDA batch slots remains; only frames 0/4 receive spectra. Four CPU `inverse` and four CUDA `inverse-valid` jobs. All CUDA full-batch memcmp checks report projection byte-no-op; projected spectrum hashes equal the supplied zero-DC input hashes.
- Same binary, layout and normalization as sealed v2: little-endian complex64 half-spectrum `[972,487]`, float32 unshifted real map `[972,972]`, native inverse unscaled. Same search square -12…12, strict greater-than row-major peak selection, separable double parabola/EPS 1e-15 and original multiply-then-divide pixel scaling. Estimates are recomputed from maps before anchoring; no new native trajectory observations were produced.
- Venue: 4GPUs, GPU2 `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`, CPU80–87, maximum eight threads. All eight jobs have fresh occupancy/compatible-lock/input/binary/scratch checks, actual child/thread affinity and GPU witnesses. Native resource window is released. No timing claim. [Exact native ledger](evidence/NATIVE-LEDGER.json).
- No movie, capture, forward, window or trajectory run; no added native matrix beyond the eight inverses. No peak/weight/reference/tie/search-domain change, no prior H7 package or CUDA port, no DC adoption or M3 decision. The unchanged 0.001 CPU-agreement and 0.20/0.40/0.80 Å truth gates were not evaluated on new products or relaxed.

## Per-input CPU–CUDA raw-subpixel vectors

Each cell is (CUDA−CPU X, Y) in original pixels; Euclidean norm. Before uses sealed v2 maps on the same valid spectra; after uses only the DC-zero copies. All selected maxima remain unique, all integer peaks unchanged, and no denominator is zero/nonfinite/degenerate.

| Movie/source/frame | Before: (X,Y); norm px | After: (X,Y); norm px |
|---|---|---|
| 00021/cpu/0 | (-0.00930037141322, 0.00260855713459); 0.00965926905869 | (4.60185979989e-07, -4.54724600463e-06); 4.57047233476e-06 |
| 00021/cpu/4 | (0.000130840272452, 0.000202552563394); 0.000241136305505 | (2.82964369802e-06, 0); 2.82964369802e-06 |
| 00021/cuda/0 | (-0.00930037141322, 0.00260855713459); 0.00965926905869 | (2.28539186686e-06, -3.087440275e-06); 3.84126326054e-06 |
| 00021/cuda/4 | (0.000130840272452, 0.000202552563394); 0.000241136305505 | (2.82963950182e-06, -1.78208065504e-06); 3.34405011496e-06 |
| 00046/cpu/0 | (-0.00580071797566, 0.00234260496352); 0.00625588739095 | (3.38874753059e-06, -1.73608095055e-06); 3.80756968327e-06 |
| 00046/cpu/4 | (0.00201795576362, 0); 0.00201795576362 | (0, 1.24133594426e-06); 1.24133594426e-06 |
| 00046/cuda/0 | (-0.00580071797566, 0.00234260496352); 0.00625588739095 | (3.38874753059e-06, -5.92775390107e-07); 3.44020239073e-06 |
| 00046/cuda/4 | (0.00201795576362, 0); 0.00201795576362 | (-1.40439515306e-06, 1.24133793866e-06); 1.87436539231e-06 |

## Frame-zero-adjusted f4−f0 vectors

These are two-map differences under the common recomputed peak rule, not 24-frame native trajectory RMS or a DC trajectory rerun. Each cell gives (X,Y); norm px.

| Movie/source/state | CPU f4−f0 | CUDA f4−f0 | CUDA−CPU anchored vector |
|---|---|---|---|
| 00021/cpu/before | (3.3769185687, -2.93742969855); 4.47572030555 | (3.38634978038, -2.93983570312); 4.48441733076 | (0.00943121168567, -0.0024060045712); 0.00973327343993 |
| 00021/cpu/after | (3.37873970314, -2.93089872473); 4.47281223798 | (3.37874207259, -2.93089417749); 4.47281104818 | (2.36945771803e-06, 4.54724600463e-06); 5.1275506925e-06 |
| 00021/cuda/before | (3.3769185687, -2.93742969855); 4.47572030555 | (3.38634978038, -2.93983570312); 4.48441733076 | (0.00943121168567, -0.0024060045712); 0.00973327343993 |
| 00021/cuda/after | (3.37873992975, -2.93089773636); 4.47281176151 | (3.378740474, -2.930896431); 4.47281131727 | (5.44247634959e-07, 1.30535961995e-06); 1.41427339138e-06 |
| 00046/cpu/before | (0.876562900278, -0.640935170638); 1.08589152824 | (0.884381574018, -0.643277775602); 1.09358907504 | (0.00781867373928, -0.00234260496352); 0.00816207431089 |
| 00046/cpu/after | (0.881403240956, -0.650426335264); 1.0954113797 | (0.881399852209, -0.650423357847); 1.09540688509 | (-3.38874753059e-06, 2.97741689481e-06); 4.51094460081e-06 |
| 00046/cuda/before | (0.876562900278, -0.640935170638); 1.08589152824 | (0.884381574018, -0.643277775602); 1.09358907504 | (0.00781867373928, -0.00234260496352); 0.00816207431089 |
| 00046/cuda/after | (0.881402747651, -0.650427869473); 1.09541189374 | (0.881397954509, -0.65042603536); 1.09540694798 | (-4.79314268365e-06, 1.83411332877e-06); 5.13207448198e-06 |

## Independent arithmetic CCF reference

Python 3.12.3 / NumPy 2.5.3, existing `.mc-venv`; exact float32 complex inputs cast to complex128, then `numpy.fft.irfft2(S, s=(972,972), axes=(-2,-1), norm="forward")`. Output float64. Installed `_raw_fft` code swaps inverse normalization, making its factor 1 on each axis: this is unnormalized C2R matching NativeFwdOnly inverse, not NumPy’s default 1/N inverse. Source, compiled pocketfft extension and versions are hash-bound in [environment](evidence/ENVIRONMENT.json).
An analytic unit-DC control gives constant 1 exactly; a rectangular non-DC cosine validates sign, axes and amplitude. For every actual original/zero spectrum, explicit half-spectrum weighted C2R sums independently check the double peak and four neighbors. All pass the frozen envelope. This reference evaluates arithmetic for the supplied spectra; it is neither native CPU/CUDA output nor physical motion truth.

| Movie/source/frame/state | CPU minus double reference: (X,Y); norm px | CUDA minus double reference: (X,Y); norm px |
|---|---|---|
| 00021/cpu/0/before | (-0.00108053087643, 0.00888080504509); 0.00894629785017 | (-0.0103809022896, 0.0114893621797); 0.0154844623944 |
| 00021/cpu/0/after | (-2.06157288929e-06, 1.33418920267e-06); 2.45563507191e-06 | (-1.6013869093e-06, -3.21305680195e-06); 3.59001031278e-06 |
| 00021/cpu/4/before | (-0.00289970684121, 0.00234812794017); 0.00373122025461 | (-0.00276886656876, 0.00255068050356); 0.00376465046277 |
| 00021/cpu/4/after | (-1.03085536107e-07, -3.69090079833e-07); 3.83215493926e-07 | (2.72655816191e-06, -3.69090079833e-07); 2.75142633871e-06 |
| 00021/cuda/0/before | (-0.00108044178716, 0.00888075020215); 0.00894623264891 | (-0.0103808132004, 0.0114893073367); 0.0154843619752 |
| 00021/cuda/0/after | (-3.18927323928e-06, 1.44717656259e-06); 3.50225410244e-06 | (-9.03881372416e-07, -1.64026371241e-06); 1.87282315814e-06 |
| 00021/cuda/4/before | (-0.00289976669777, 0.00234822344484); 0.00373132687504 | (-0.00276892642532, 0.00255077600823); 0.00376475919456 |
| 00021/cuda/4/after | (-1.15313982896e-06, 8.82600442953e-07); 1.45214152445e-06 | (1.67649967286e-06, -8.99480212091e-07); 1.90255507281e-06 |
| 00046/cpu/0/before | (0.002813258105, -0.00302633592462); 0.00413196445943 | (-0.00298745987066, -0.000683730961093); 0.00306470300453 |
| 00046/cpu/0/after | (-8.1608803093e-07, 5.59635041419e-07); 9.89540829785e-07 | (2.57265949966e-06, -1.17644590913e-06); 2.8288870388e-06 |
| 00046/cpu/4/before | (-0.0020222869432, 0.00646419652359); 0.00677314411306 | (-4.33117958121e-06, 0.00646419652359); 0.00646419797459 |
| 00046/cpu/4/after | (3.97953866349e-06, -7.25182744965e-08); 3.98019935108e-06 | (3.97953866349e-06, 1.16881766976e-06); 4.14763338777e-06 |
| 00046/cuda/0/before | (0.00281328579144, -0.00302668397446); 0.00413223823437 | (-0.00298743218422, -0.000684079010939); 0.00306475368481 |
| 00046/cuda/0/after | (-7.88403706764e-07, 2.11587509735e-07); 8.16302443409e-07 | (2.60034382382e-06, -3.81187880372e-07); 2.62813473822e-06 |
| 00046/cuda/4/before | (-0.00202241202956, 0.00646461563628); 0.00677358145608 | (-4.4562659407e-06, 0.00646461563628); 0.00646461717221 |
| 00046/cuda/4/after | (3.36115369848e-06, -1.18764918389e-06); 3.56480921913e-06 | (1.95675854542e-06, 5.36887547753e-08); 1.95749495209e-06 |

Double-map DC-only change: maximum residual from an exact constant is **2.48689957516e-14**, versus preregistered epsilon/L1-derived bounds **6.30729977294e-12…9.08140144408e-12**. Maximum double-reference peak change is 2.14526003427e-11 px, with unchanged integer peaks. The complete formula, gamma factor, inflated full-spectrum L1 values and direct-sum residuals are retained per input in [analysis v3](evidence/ANALYSIS-v3.json). The envelope is conservative under ordinary stable-FFT error scaling; it is not a formal pocketfft implementation certificate or a threshold fitted to these outcomes.

## Curvature, conditioning and post-map negative control

For D=vp+vn−2c, C1 #260 already promotes stencil values before double arithmetic. The experiment changes precision of the represented inverse map before that peak fit; it does not diagnose an FP64 parabola defect. D/ULP uses the float32 spacing at each map center; denominator condition is (|vp|+|vn|+2|c|)/|D|. The quantization envelope and every stencil value/N/D are retained in JSON and [curvature ledger](curvature.csv).

| Input/backend/axis | abs(D)/ULP32(c), before → after | Denominator condition, before → after |
|---|---:|---:|
| 00021/cpu/0/cpu/x | 646 → 1318988 | 67623.5944272 → 39.3986055976 |
| 00021/cpu/0/cpu/y | 1076 → 2199182 | 40598.8959108 → 23.2295890017 |
| 00021/cpu/0/cuda/x | 648 → 1318984 | 67414.882716 → 39.398719014 |
| 00021/cpu/0/cuda/y | 1079 → 2199177 | 40486.0176089 → 23.229638633 |
| 00021/cpu/4/cpu/x | 663 → 1348888 | 66362.3001508 → 39.0481819098 |
| 00021/cpu/4/cpu/y | 1083 → 2215701 | 40625.8402585 → 23.3807770092 |
| 00021/cpu/4/cuda/x | 660 → 1348888 | 66663.9454545 → 39.0481789444 |
| 00021/cpu/4/cuda/y | 1080 → 2215701 | 40738.6888889 → 23.3807752039 |
| 00021/cuda/0/cpu/x | 646 → 1318986 | 67623.6006192 → 39.3986668547 |
| 00021/cuda/0/cpu/y | 1076 → 2199181 | 40598.8996283 → 23.2296000193 |
| 00021/cuda/0/cuda/x | 648 → 1318985 | 67414.8888889 → 39.398691418 |
| 00021/cuda/0/cuda/y | 1079 → 2199178 | 40486.021316 → 23.2296294343 |
| 00021/cuda/4/cpu/x | 663 → 1348890 | 66362.3122172 → 39.0481225304 |
| 00021/cuda/4/cpu/y | 1083 → 2215702 | 40625.8476454 → 23.3807660055 |
| 00021/cuda/4/cuda/x | 660 → 1348890 | 66663.9575758 → 39.048119565 |
| 00021/cuda/4/cuda/y | 1080 → 2215702 | 40738.6962963 → 23.3807642002 |
| 00046/cpu/0/cpu/x | 658 → 1347207 | 94882.6838906 → 43.7548802819 |
| 00046/cpu/0/cpu/y | 1138 → 2331139 | 54861.4463972 → 24.8646472819 |
| 00046/cpu/0/cuda/x | 658 → 1347205 | 94882.6899696 → 43.7549407848 |
| 00046/cpu/0/cuda/y | 1139 → 2331136 | 54813.2827041 → 24.864677136 |
| 00046/cpu/4/cpu/x | 647 → 1323322 | 97268.0880989 → 45.7614926677 |
| 00046/cpu/4/cpu/y | 1056 → 2161132 | 59594.7386364 → 27.6333791735 |
| 00046/cpu/4/cuda/x | 649 → 1323322 | 96968.3374422 → 45.7614926677 |
| 00046/cpu/4/cuda/y | 1056 → 2161134 | 59594.7386364 → 27.633352675 |
| 00046/cuda/0/cpu/x | 658 → 1347207 | 94882.6838906 → 43.7548743437 |
| 00046/cuda/0/cpu/y | 1138 → 2331139 | 54861.4463972 → 24.8646438501 |
| 00046/cuda/0/cuda/x | 658 → 1347205 | 94882.6899696 → 43.7549348466 |
| 00046/cuda/0/cuda/y | 1139 → 2331137 | 54813.2827041 → 24.8646626088 |
| 00046/cuda/4/cpu/x | 647 → 1323321 | 97268.1004637 → 45.7615249815 |
| 00046/cuda/4/cpu/y | 1056 → 2161131 | 59594.7462121 → 27.6333905719 |
| 00046/cuda/4/cuda/x | 649 → 1323324 | 96968.3497689 → 45.7614189722 |
| 00046/cuda/4/cuda/y | 1056 → 2161133 | 59594.7462121 → 27.6333640734 |

The separate negative control casts each already-produced original float32 map to float64 and subtracts its real DC constant, with no FFT. **All sixteen peaks change by exactly 0 px, and every selected D and N is exactly preserved.** Their original peak errors relative to the arithmetic reference remain. The reduced displayed pedestal does not restore information already lost in the float32 inverse; the ledger retains the original map’s ULP scale rather than assigning new precision to the subtracted map. This is separate from pre-IFFT DC zeroing.

## Retained failures, evidence and interpretation

- First local analysis produced all 16 double maps and 16 post-map arrays, then failed JSON serialization on NumPy booleans. The amended v2 reused those arrays but reported 71/80 exact controls: pre-dividing the pixel scale differed from the sealed multiply-then-divide rule by about 1e-15 px. Final v3 restores the original evaluation order and frozen norm calculation; it passes 80/80 without tolerances or threshold changes. [Additive amendment](ANALYSIS-AMENDMENT.md), retained source v1/v2, logs and original v2 grade are included.
- Packaging/analysis repairs repeated no native inverse and no actual-spectrum NumPy FFT. Final analysis reuses the first 16 double arrays and verifies the retained 32 reference/postmap arrays; only local peak/direct-sum/analytic controls are evaluated again. The native count remains exactly eight.
- [Collection](evidence/COLLECTION.json) strictly binds the eight RUN/ADMISSION/START triplets and verifies all frozen inputs and 60 output files. Aggregate scratch is 5,198,826,370 bytes, below 20 GiB. Raw spectra, float maps and double/postmap arrays remain under `4GPUs:/mnt/clathrin/alex-motioncorr-cuda-cpu-boundary-20261026/dc-pedestal-v1-20261026`. [Output hashes](evidence/OUTPUT-INDEX.json), [verified local/remote metadata archive](evidence/ARCHIVE-BINDING.json). Sealed boundary paths are unchanged.
- This supports a DC-pedestal conditioning mechanism for the selected stored spectra: double maps differ only by a constant, both float backends move much closer to the double arithmetic reference, and subtracting the pedestal after float IFFT does not recover the lost curvature. It does not establish full trajectory recovery, image preservation, final Gate2 improvement or physical accuracy.
- Smallest proposal for parent consideration, only after historical/scientific harm review: one default-off DC-only manipulation of a COPY of the global CCF consumption spectrum before inverse. No other bins, weights, reference, peak/tie rule or local route change. This packet implements only copied-spectrum replay controls; it neither implements/ports that native concept nor authorizes a trajectory campaign. Historical DC/H7 harm results and no-port falsification remain in force.
- No production/science/parity acceptance, DC adoption, M3 decision, merge or watcher. Independent result review remains with the parent.
