# Current-source CPU/native-CUDA first-boundary result

The first **sampled bit mismatch** is the initial forward FFT, after byte-equal preprocessed frames 0/4 in both predetermined tutorial movies. On the same stored valid CCF spectra, inverse execution still changes the sampled subpixel estimates materially. Replacing the initial FFT inputs at a fixed downstream operator changes none of those four sampled estimates. This is a located CPU/CUDA compatibility boundary, not proof that FFT roundoff solely causes final image differences, a native inverse-correctness verdict, or scientific acceptance.

No estimator intervention is justified by this bounded packet. Only default-off capture code is proposed; no candidate, merge/default/gate/policy change, C1 campaign restart, W4 repeat, full24/100 run, throughput claim or M1 disposition.

## Revisions and protocol

- Isolated worktree t3-5b6913e1; branch cuda-cpu-first-divergence. Clean stale c8844894 fast-forwarded to b305b23bc7572aaafb0a7fa9fdfdd0c350fb4ce3. Production/tests identity to e77a51a220cb0d91f4ac3c7fac211876d0c6833f was checked before edits; the original entire delta outside C1 qualification docs/tooling was empty.
- Plan frozen at 1e23051c before new measurements. Read AGENTS.md, gate contract, issue36 latest discussion, issue238 latest relevant discussion, latest C1 acceptance packet and W4 closure. Older issue36/W4 source captures were inventoried and not promoted to C1 evidence. C1 provided no justified replacement for accepted cases00021/00046.
- Capture hook 0e055c15 was corrected after independent source review; exact cleared hook 7a1bde5db99c94bc4332bae3f3aff6e0bfccaabd. [Review](REVIEW.md). The final diagnostic binary 930ed6b6e600b002d7ff38725e627caca134f409718421014398307c331776a3 binds 268 source files: [pins](evidence/diagnostic-pins.json), [manifest](diagnostic-source-manifest.json).
- The plain production CUDA binary34e768128b83f7c94eb4a41ee6bb9a795c52c531a5d646ce4116df83d8d3535a runs BOTH CPU and native CUDA. Capture-disabled outputs at0e055c15 and7a1bde5d each match all 8 production baseline MRC payloads and movie-STAR text exactly; amended capture-on matches all 4corresponding flags-off outputs exactly.
- Same host4GPUs, CPUs 80–87 at most8threads; GPU 2 GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598, A10080 GB PCIe; CUDA12.8/driver570.86.10. No cpu64 work. [Protocol](PROTOCOL.md) binds selectors, layouts, normalization, FFTW ESTIMATE/single plan threading with outer OMP 8, cuFFT geometry, Hermitian validity and route/device witnesses.
- Flags: --j 8 --use_own --dose_weighting --dose_per_frame1.277 --bfactor150 --seed1 --expected_frames24 --gainref Movies/gain.mrc --ingest float; native adds --gpu0. G uses1x1, L5x5. Defaults group1/bin1/max_iter5/ccf_downsample0; optional origin interpolation OFF. [Producer ledger](evidence/producer-ledger.json) binds all 8exact baseline argv/env/binary hashes and all later commands.
- Baseline/off/off-v2 resource checks were phase-level only. Capture/replay producers use fresh per-job input/binary rehash, overlapping-lock/CPU occupancy assessment,20 GiB scratch admission and parent/child/thread affinity witnesses. Do not retroactively upgrade the first 24 producers. [Provenance amendment](PROVENANCE-AMENDMENT.md). No timing ratio is claimed.

Input SHA256:

| Input | SHA256 |
|---|---|
| gain.mrc | `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1` |
| 20170629_00021_frameImage.tiff | `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0` |
| 20170629_00046_frameImage.tiff | `61094383ce6750976275b13227033dcdb154c8214ef3db402aa6440a505ad377` |

## Endpoints: unchanged relaxed gate

Existing unmodified comparator `--gate relaxed --require-complete-coverage` independently grades the endpoint metrics relative to the new producer analysis; comparator source/argv/exit are bound in [endpoint-grades](evidence/endpoint-grades/RUN.json). This is not an independent result audit of the new replay tools. Every pair has complete image/STAR coverage and FAILS only relative image RMSE 0.001. Other enforced relaxed predicates pass.

| Case | G/L | relative image RMSE | Global vector RMS px | STAR total field vector RMS px | Gate |
|---|---|---:|---:|---:|---|
| 00021 | G | 0.00589254030912 | 0.00412504633812 | 0.00412504633812 | FAIL |
| 00021 | L | 0.00571264666096 | 0.00412504633812 | 0.0107935112475 | FAIL |
| 00046 | G | 0.0119137921445 | 0.0067684927575 | 0.0067684927575 | FAIL |
| 00046 | L | 0.0107374983664 | 0.0067684927575 | 0.0052308165422 | FAIL |

Field numbers use printed STAR on17x17 points over10–90% of each axis, all 24 frames. They are descriptive CPU distances, not fullprecision runtime truth. Both L arms accept 25 patches / 600 matched frame-centre rows. Global trajectories are identical between G/L within each backend. Observation/local-field/total-field differences are distinct:

| Case | Observation vector RMS px | Local-field vector RMS px | Total-field vector RMS px |
|---|---:|---:|---:|
| 00021 | 0.00929812104087 | 0.0111878980442 | 0.0107935112475 |
| 00046 | 0.0138190981813 | 0.00876424962765 | 0.0052308165422 |

[Field ledger](evidence/endpoint-decomposition.json) retains squared global/local/cross terms; scalar RMS values must not be added. These observations already have different global states and are not same-state fit attribution. Fullprecision local CUDA observations/fit and same-field applied-reconstruction counterfactual remain UNRUN. DW image endpoints are measured; their residual is not assigned to reconstruction or estimator alone. W4 CPU fit closure was not repeated.

## Matched operator evidence

Four captured preprocessed frames are bit-identical. Forward replay of each identical stored frame through actual NewFFT and actual resident CudaMovieSession reproduces the corresponding native captured spectra exactly. Initial CPU/CUDA Fourier-component RMSE is9.55e-11 to1.21e-10; this is the earliest observed bit boundary for the sampled frames, not an all 24-frame preprocessing proof.

All24saved Fourier windows can be equalized before reference/CCF construction. Under that control, CPU/CUDA references are bit-identical. Weights differ by at most1.1920928955078125e-7; weighted-spectrum component RMSE is7.83e-15 to1.94e-14. Same-backend window replays reproduce native reference/weight/spectrum/map bytes. Replacing only initial FFT-window inputs at either fixed downstream operator changes maps but produces exactly zero change in all four recomputed sampled subpixel estimates. The common-state weighting/arithmetic crosses likewise retain the sampled estimates under fixed inverse backend. These conditional samples do not bound later iterations.

Both actual raw weighted spectra fail exact Hermitian conjugacy on self-conjugate columns. Actual CPU preserving-wrapper input is raw; CUDA actual input is postprojection, saved separately as ifft-input-F.c64. Raw CPU-vs-CUDA inverse arms are explicitly raw FFTW versus native projection-plus-cuFFT compatibility behavior. They are not unchanged-input pure-FFT correctness controls.

### Repaired inverse-only controls

Parent source review found undefined 22 batch slots in the initial inverse-CUDA helper. The original 28 attempts and original 54-check JSON are retained: [original](evidence/replay-v1-analysis-original.json). Four CUDA inverse attempts plus four projected-CPU derivatives have INVALID complete-batch provenance; selected maps matching v2 does not repair that provenance. Captures, forward/window and original raw-CPU inverse execution are unaffected. [Finding and source-only clearance](evidence/parent-source-review/REVIEW.md), [fix amendment](evidence/parent-source-review/AMENDMENT-031f333a.md), [repair protocol](INVERSE-REPAIR.md).

Fix `031f333a2863218c74951117989c84423ad9c92e` explicitly zero-fills all 24 complex slots. Only the 8 affected inverse jobs were repeated, plus 4 separately labelled valid CUDA controls: 12 new inverse-only processes, no movie/capture/forward/window repeats. Producer-reported 39/39 v2 checks pass, 12 exits 0; independent source clearance is complete, independent result audit remains PENDING. Each valid control compares the complete batch before/after projection with memcmp and fails on any changed byte; the supplied projected spectra are also SHA-bound identically for CPU/CUDA. All projected spectra are exactly Hermitian-valid. Native CUDA inverse of its actual raw capture reproduces its captured maps exactly. [v2results](evidence/inverse-v2-analysis.json).

On those byte-identical valid spectra, map RMSE remains about2.18e-6 to2.45e-6 and subpixel estimates differ as follows (same double formula recomputed on each float map):

| Case/frame | Integer peak both | CPU X/Y px | CUDA-map X/Y px |
|---|---|---|---|
| 00021/0 | [-2, 2] | -6.52886073208, 6.30081501369 | -6.53816110349, 6.30342357083 |
| 00021/4 | [-1, 1] | -3.15194216338, 3.36338531514 | -3.15181132311, 3.3635878677 |
| 00046/0 | [-1, 1] | -3.43982575957, 3.25461245272 | -3.44562647754, 3.25695505768 |
| 00046/4 | [-1, 1] | -2.56326285929, 2.61367728208 | -2.56124490352, 2.61367728208 |

All four sampled maxima are unique on both native maps and all crosses, and integer peaks match. Recomputed-map estimates are NOT the recorded native raw observations: the latter are in peak-x/y files (CPU f64, CUDA f32) before frame 0subtraction. Their maximum selected difference from map recomputation is3.11e-7px for CUDA and8.88e-16px for CPU. Interpolation output rounding is a separate small term here. No tied-peak or optional-origin causal claim is made.

## Native raw observations and anchoring

All24 pre-anchor native observations were captured, not just frames 0/4 maps. Below are vector RMS CPU/CUDA differences, with a separate mathematical float64 subtraction and actual float CUDA anchoring. These are iteration1 differences, separate from final STAR trajectories.

| Case | Raw observations px | Mathematical raw_i−raw_0 px | Native float anchoring px | Final global STAR px |
|---|---:|---:|---:|---:|
| 00021 | 0.00337606333435 | 0.00915003466387 | 0.00915000259298 | 0.00412504633812 |
| 00046 | 0.00344366118828 | 0.00717613081683 | 0.0071760904592 | 0.0067684927575 |

The native frame 0CUDA-minus-CPU vectors are(-0.00930006885673,+0.00260886783884)px for00021 and(-0.00580073770296,+0.00234269407126)px for00046. The common offset does not simply cancel; anchoring increases the all 24-frame difference here. Full raw and anchor-adjusted vectors and raw-map/native separation remain in the original analysis JSON; those capture-derived fields are unaffected by the inverse-helper defect. A progress-message00046anchored-RMS transcription0.006200 was explicitly corrected to0.007176; retained data always held the latter.

## Evidence, failures and limits

- All 28movie processes (8 production baseline,8 initial flags-off,8 amended flags-off,4 capture) exited0. Original28replay processes exited0; their8 affectedinverseattempts retain invalid provenance. Repaired12 inverse processes exited0. These counts are execution coverage, not science or acceptance passes.
- Retained preparation failures: nonexistent cmake/archive path and incomplete first staging/configuration; nvcc rejected a GCC-style linker option; system Python lacked NumPy. Corrected preparation records are additive. No producer was silently retried, no tolerance was relaxed, no foreign process/lock was removed, and the eight-case K267 PLUS separate retained N5/9/13/20/global-only/harmfulvel1N20iso candidate controls remain mandatory and UNRUN for any new intervention.
- Raw arrays/products/binaries remain under4GPUs:/mnt/clathrin/alex-motioncorr-cuda-cpu-boundary-20261026. All882 recorded product-file hashes were verified unchanged; final scratch4,799,899,831 bytes, below20 GiB. GPU 2 post-readback idle; no native process retained. Kernel-Xid inspection UNRUN; no fault campaign was performed.
- [Receipt archive binding](evidence/archive-binding.json):473 metadata/receipt files,1,754,657 bytes, SHA256 e28fffa6f02366eb8899f47cdb8aa1b4539f3bccf22a64909c5eb07a9687c9ab; downloaded copy SHA-verified. [Verified product index](evidence/verified-file-index.json). Parent source notes are copied with all 3 hashes verified; final supplemental metadata bundle includes them.
- Independent source review clears the capture hook and repaired helper only. Producer-reported analysis/control grades await independent result audit. Current-head CI remains separate; no monitoring/watcher is started by this child.
- Numerical operator compatibility, motion truth and image/signal preservation are separate claims. No independent highprecision/truth inverse oracle, downstream science, same-field reconstruction attribution, later-iteration causal fraction, native estimator candidate or performance qualification is established. M1 remains HELD; parent owns direction and interpretations.

[Final configuration witness](evidence/final-config-witness.json) rehashes both producer binaries, both replay binaries, CMake cache/flags/link command and dynamically linked libraries; it records the final lock/GPU readback.
