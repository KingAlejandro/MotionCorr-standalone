# CPU and CUDA compatibility

All end-to-end compatibility comparisons use released standalone CPU source `6d68e2d6` as the reference unless a control names a different CPU arm. The applied STAR field diagnostic is 0.020 Å vector RMS on the fixed lattice. The image limit is 0.001 relative RMSE, the RMS pixel difference divided by the reference image's standard deviation.

## SCARF and the inverse crossover

The initial native pair used two frozen 4096×4096×40 low-contrast synthetic movies. The trace CPU reproduced the released CPU fields and image pixels exactly. Native CUDA exceeded both limits on both movies. The same 25 patch sites were accepted by both backends on each movie. The first sampled numerical difference was at the forward FFT. Exchanging all 40 captured Fourier windows at a fixed correlation operator had zero measured effect on the first-iteration estimates.

At zero-based frame 35, a common Hermitian-valid correlation spectrum produced a subpixel gap of **0.148035 px** on seed 04 and **0.038095 px** on seed 09 between FFTW and cuFFT with the CPU peak reader. Zeroing DC before the inverse reduced both gaps to about **4.5×10⁻⁶ px** and changed the integer winner on seed 09. The follow-up crossed both native pre-inverse spectra and the two inverses while retaining DC. FFTW reproduced the native CPU estimate from either spectrum. Exchanging the weights and complex products gave the same CPU peak after FFTW in the targeted replay. Over the first global iteration, FFTW recovered all **80/80** CPU integer and subpixel estimates from CUDA spectra. Three sampled native spectra per movie matched the replayer byte for byte. [SCARF numerical evidence](data/scarf_compatibility.json)

## Live hybrid alignment on SCARF

The live hybrid retained CUDA forward transforms, correlation-spectrum formation, phase updates and reconstruction. It used the FFTW float inverse and CPU peak reader on either the global correlations alone or both global and local correlations. It retained DC. The table uses the applied STAR field and corrected image against the released CPU. Bold marks a value within its respective limit.

| Movie | Alignment | Applied field RMS (Å) | Global RMS (Å) | Image relative RMSE |
| --- | --- | ---: | ---: | ---: |
| contrast025-s04 | Native CUDA | 0.0363723 | 0.0343355 | 0.0669435 |
| contrast025-s04 | Global hybrid | 0.0225442 | 0.000002023 | 0.0399350 |
| contrast025-s04 | Global and local hybrid | **0.000002025** | 0.000002023 | **0.000116854** |
| contrast025-s09 | Native CUDA | 0.0669187 | 0.0710834 | 0.166947 |
| contrast025-s09 | Global hybrid | 0.0363077 | 0.000001434 | 0.0662957 |
| contrast025-s09 | Global and local hybrid | **0.000690063** | 0.000001434 | **0.000880210** |

Each live arm retained 25 accepted patch sites and 1,000 observations per movie. The global and local hybrid met the numerical limits on both fixtures, with residual pixel differences in both cases.

SCARF used an A100-SXM4-40GB, driver 580.196.07, and eight allocated CPU threads. The trace and live hybrid builds used `4b524b7d` with scratch instrumentation. The first native and trace job was 3859518. Its scheduler status remains **FAILED** because the seed-04 reducer expected CUDA maps beyond the two saved frames. The producers completed, and the seed-04 summary was recovered from the original arrays. An earlier build and launch sequence also had partition, AppleDouble, instrumentation and import failures before any movie ran. The inverse replays (3859638 and 3859641) and the live hybrid job (3859750) exited zero. The live hybrid binary SHA-256 is `0a52e5fe1e08a2c7b8030dacbc258c2aba82b10092f47ac5fba9ec2fd0010d47`.

## Three real movies and a common motion field

The selected inputs are two tutorial movies, 00021 and 00046, and EMPIAR-10216 movie 1739. They had recorded CPU/CUDA mismatches. Each run used a 5×5 local grid, float ingestion, dose weighting and a separate unweighted sum. Image metrics and byte-level input pins are recorded with the binary hashes. The tutorial dose and gain are pinned, and the EMPIAR-10216 dose is the same corpus placeholder across arms. [Real-movie results and inputs](data/real_movies.json)

| Movie | Native CUDA weighted | Hybrid weighted | Native CUDA unweighted | Hybrid unweighted | Common field weighted | Common field unweighted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tutorial 00021 | 0.005713 | **0.000481** | 0.011522 | 0.001024 | **0.00008349** | **0.00011620** |
| Tutorial 00046 | 0.010737 | **0.000316** | 0.016083 | **0.000764** | **0.00008463** | **0.00011738** |
| EMPIAR-10216 1739 | 0.015973 | 0.005257 | 0.032107 | 0.012173 | **0.00007075** | **0.00008569** |

Native CUDA and hybrid use released CPU as reference. The common-field comparison uses the CPU and CUDA sums reconstructed with the exact same full-precision CPU global trajectory and local polynomial. That intervention bypassed local estimation and applied the cumulative global shift once. CPU fixed-field versus CPU live image relative RMSE stayed below 8.0×10⁻⁷, and preprocessing frames 0 and 4 matched bitwise. The residual in the common-field pair includes separate preprocessing and initial transforms, phase arithmetic, inverse transforms, interpolation and summation.

The ordinary CPU arm reproduced the released CPU field and both image payloads exactly in each case. The hybrid global shift difference stayed below 2.1×10⁻⁶ Å RMS. All three native and hybrid STAR fields passed the 0.020 Å diagnostic, including images above the image limit. The runtime local field gaps after the hybrid substitution were 0.000129, 0.000081 and 0.004817 Å RMS. STAR rounding altered the size of the reported gaps, so subsequent diagnosis used full-precision runtime coefficients. The accepted patch and frame rows agreed across CPU, native CUDA and hybrid. On EMPIAR-10216, exchanging the most helpful single patch track in a same-design offline refit reduced the gap from 0.004817 to 0.004010 Å.

The 18 producers all exited zero on cores 80–87 at 4GPUs. All nine CUDA producers were observed on a single A100 PCIe 80GB, driver 570.86.10 and CUDA 12.8. The fixed-field diagnostic overlaid the live hybrid source at `4b524b7d`. The diagnostic build SHA-256 is `0059576a04250bf51e8b572d6f165f342a46f80e5c395309573291d3681aa92b`. The rebuilt `6d68e2d6` CPU binary SHA-256 is `9f04aac4638eb535924b47360c96208c049806341a4cf84464ec52d3f9d78ba2`.

## Identical local inputs on EMPIAR-10216

The two native controls captured each of the 25 grouped float patch stacks immediately before the local forward FFT. The two crossover producers used the other backend's captured pixels, recaptured their actual FFT inputs and matched every stack digest against its source. The CUDA route retained resident batched alignment. All four producers retained the same 1,239 observations at the same 21 accepted patch sites. The own-input controls reproduced the preceding runtime fields and both image payloads exactly. [Crossover results and receipts](data/patch_crossover.json)

| CPU versus hybrid CUDA | Runtime local field RMS (Å) | Weighted relative RMSE | Unweighted relative RMSE |
| --- | ---: | ---: | ---: |
| Each uses its own pixels | 0.00481702 | 0.00525691 | 0.01217342 |
| Both use CPU pixels | 0.00261184 | 0.00326171 | 0.00774338 |
| Both use CUDA pixels | 0.00462492 | 0.00516126 | 0.01178214 |

With byte-identical pixel stacks, the first numerical disagreement in the traced patch (408, 2865) appeared in the normalised forward spectra. That boundary combines the FFT implementation and normalisation. The weight and product already differed before the first correlation inverse. All raw subpixel peaks were identical in iteration one. CUDA's float shift update produced up to 9.30×10⁻⁷ px of cumulative difference. The first different raw subpixel peak appeared in iteration two. All 59 integer peaks agreed through four iterations in both pairs. With shared CPU pixels, the maximum raw subpixel differences by iteration were 0, 0.003602, 0.010824 and 0.053609 px.

The map replay recovered **32/32** captured float maps and their peak records exactly. Exchanging existing DC values and bypassing the CUDA Hermitian projection each left the sampled peak coordinates unchanged. Zeroing DC before the inverse reduced the frame-39 iteration-four subpixel gap from 0.05361 to 0.01056 px with shared CPU inputs, and from 0.04322 to 0.01058 px with shared CUDA inputs. The map's DC level is near 36,461, where float values are 0.00390625 apart. On the shared CPU input, the difference between the right and left interpolation samples was two representable steps in the CPU map and seven in the hybrid map. The parabolic fit uses that small difference. Thus quantisation on top of a large offset amplified the already different non-DC spectra. Removing DC in these saved maps left the sampled integer peaks unchanged. The earlier synthetic seed-09 replay changed an integer winner under the same manipulation. [Saved CCF replay](data/ccf_replay.json)

All four crossover producers exited zero on the same 4GPUs A100 and CPU mask. Both CUDA PIDs were observed on the assigned device. The crossover build added scratch instrumentation to the preceding source, binary SHA-256 `3ae199afdc63b240354437ae8f8ca5073f5eb313f8d28d26be0af709b1be7547`. An initial build error and an initial stdout-redirection error were repaired before a native producer started.

The identical-pixel result locates part of the residual inside local alignment. The saved-map replay identifies a float precision effect on one patch and two sampled frames. Separation of forward FFT and normalisation, product arithmetic and phase feedback remains open, as do live behaviour under DC removal and broad compatibility qualification.
