# #262: independent double-CCF reference and split DC conditioning

**Both global and local CCF conditioning are needed to approach the double reference across this development corpus.** Against R, CPU/CUDA float have **16/20** product-screen positives without conditioning, **10/13** with global only, **13/11** with local only, and **0/0** with both. All **600 primary processes exited 0**. Both-conditioned arms match R's accepted-patch sets in **60/60** configurations. These are numerical-reference results; the reference itself still fails global convergence on e10216-01.

R is CPU double CCF reference accumulation/product, FFTW double inverse, double search and fit, starting from the existing float frame spectra. R′ also zeros CCF DC globally and locally. The corpus, input identities, recipes, frame origin, grids and descriptive **relRMSE ≥0.1** screen are those of [#255](https://github.com/KingAlejandro/MotionCorr-standalone/pull/255) and [#261](https://github.com/KingAlejandro/MotionCorr-standalone/pull/261): EMPIAR-10216, EMPIAR-12963 and EMPIAR-10474 Falcon 3, ten movies each, 5×5 and 3×3, **60 configs / 30 movies**. Every row is retained, including both failed-movie grids. No results from the separate known-motion experiment are claimed here.

| DC arm | CPU float positives /60 (movies /30) | CUDA float positives /60 (movies /30) |
|---|---:|---:|
| none | 16 (13) | 20 (16) |
| global only | 10 (8) | 13 (12) |
| local only | 13 (9) | 11 (7) |
| both | **0 (0)** | **0 (0)** |

| Both-conditioned arm vs R | Median global max / RMS, px | Median local-field max / RMS, px | Median / worst product relRMSE |
|---|---:|---:|---:|
| CPU float | 4.2681e-6 / 2.1425e-6 | 9.3756e-6 / 3.7306e-6 | 3.8547e-5 / 0.00137942 |
| CUDA float | 4.6713e-6 / 2.4096e-6 | 2.0888e-5 / 6.8563e-6 | 0.000435334 / 0.00163063 |

These medians include all 60 rows. “Median max/RMS” means the median of each config's vector maximum/RMS. [Full tables](tables.md), [540-comparison CSV](census.csv), [per-config results](results/rows.json) and [summary/statistics](results/summary.json) retain every arm's maxima/RMS, model state, accepted sets, STAR-field comparison, screen transitions and divergence witnesses. The local field uses full-precision applied coefficients on #261's 33×33 endpoint-inclusive normalized grid, at every integer frame. Disabled local models contribute zero applied local field; this is not evidence that local motion was accurately estimated.

## Double neutrality: fixed input versus float feedback

**DC removal is neutral at the tested fixed-input double CCF stage; whole-movie R/R′ are not identical at 1e-9 px.** Across **706 native frame/iteration records**, double maps match an independent full-complex Hermitian-completion inverse within **6.55e-11** map units. Selected integer peaks agree in all records, native five-sample text records round-trip exactly to their float64 dumps, and fitted candidates agree within **1.76e-10 original px**. Changing only DC on those fixed inputs changes fitted candidates by at most **1.71e-10 px**. [Native checks](results/native-stage.json).

Across the full census, R′ has **0/60** positives and **60/60** matching accepted sets. Excluding the two known-failure rows, its global max difference is at most **3.50e-8 px** (median per-config maximum **1.02e-9**), applied local-field maximum difference **4.27e-5 px**, and worst product relRMSE **0.000340753**. On e10216-01 the global maximum difference grows to **0.000222666 px**.

The paired native trace investigated this departure from the initially expected whole-pipeline 1e-9 neutrality. R and R′ already enter the first local iteration with different **float** spectra: relative L2 differences **8.86e-8** and **1.17e-7** in the two traced configurations, increasing with subsequent feedback. Fixed-input double DC invariance still holds. The double CCF toggle preserves float frame transforms, shifting, reconstruction and feedback, so its tiny estimator changes can reach a different rounded state. This trace establishes input-state differences in the sampled cases; it does not fully attribute every residual image difference in the census.

## Stage checks and limits

Cheap analytic/real-buffer stage checks preceded movie execution. The final [stage table](results/stage.json) has **220 rows**: known parabola vertex/curvature, positive amplitude scales 0.01/1/100, flat, exact/near ties, a search-boundary maximum, the existing 1e-15 guard, nonfinite inputs, and six real frame CCFs from three families. Non-DC coefficients are fixed while DC varies, including 0, 36000, 1e6 and the source DC. A separate full-complex NumPy inverse explicitly constructs valid Hermitian spectra; FFTW float/double inverses are evaluated independently. Map error is centered using the actually stored spectral DC and normalized by local peak contrast; curvature error is also normalized by that contrast. Flat-map ratios are undefined and recorded as null.

For the unit-scale parabola at DC 36000, float peak error is **0.00711806 CCF px** without removal and **5.81e-6** with removal. For captured e10216-09/frame 1 it changes **0.0191044 → 4.69e-7 CCF px** under the same pedestal sweep. Raw ULP counts at different offsets are not compared. Conditioning still cannot resolve arbitrary near ties or signals below available precision; flat/guard/boundary/nonfinite outputs are characterized rather than accepted as motion measurements. The standalone FFT stage uses FFTW; CUDA is separately covered by native peak-fit/CCF tests and the complete real-data census against R.

The six original CPU buffer pairs have raw CCF boundary-conjugacy residuals up to **3.58e-4** in spectral units. FFTW double output agrees with the independently projected full-complex reference to **5.10e-11** map units on these inputs. This characterizes the pinned FFTW behavior; it does not repair the inherited CPU representation hazard tracked in [#266](https://github.com/KingAlejandro/MotionCorr-standalone/issues/266). CUDA retains #254's explicit projection. [Stage provenance](results/stage-provenance.json) binds the old native run records to #261's published manifest and hashes the reused buffers now; #261 did not publish historical hashes for those complete spectrum buffers. The new 706-record native captures are separately retained and hash-bound.

## Global/local contribution, statistics and remaining differences

The local switch leaves captured global trajectories **byte-identical** in all **240** paired selectivity checks: none↔local and global↔both on both backends, all configs. Global conditioning repairs most global numerical error, but local float pedestal sensitivity remains; local conditioning alone retains the unconditioned global trajectory. Neither single-stage arm eliminates the product disagreements. Newly worse rows remain in the tables and paired transitions.

For none→both against R, exact McNemar cells `(both, baseline-only, conditioned-only, neither)` are CPU **(0,16,0,44)**, p **3.05176e-5**, and CUDA **(0,20,0,40)**, p **1.90735e-6**. Movie “any grid positive” counts change **13→0/30** and **16→0/30**, with p **0.000244141** and **3.05176e-5**. Config p values are descriptive because the two grids are correlated; movie collapse is a sensitivity analysis, and movies within a collection can also be correlated. No positive-only selection or threshold changes.

The older matching-DC CPU-versus-CUDA screen remains **19 / 13 / 11 / 0** positives for none/global/local/both. All **60 CPU-none** products reproduce the retained original CPU references, and all **60 CUDA-none** products reproduce #261 A1, using core-header/payload/STAR identity. Thus the numerical-reference analysis changes the comparison target explicitly. Exact backend-screen transitions are also retained in the tables.

Every arm/config has a first-integer-change record and a first >0.5 px fitted-candidate event, or an explicit absence. Positive comparisons predominantly first show changed integer ordering; same-integer/different-sample fits, CUDA same-map scan/reduction tie-order differences, and subthreshold positives are separate classifications. A selected event is an attribution witness under #261's convention, not necessarily the first arithmetic difference or a complete causal explanation.

The largest both-conditioned residual is **e12963-05/p5**, CPU/CUDA relRMSE **0.00137942 / 0.00163063**, with no >0.5 px candidate event. R′ also has its largest product change there. Small residual image sensitivity, the remaining CPU/CUDA rounding/feedback contributions, inherited unsupported-peak policies, and downstream scientific accuracy remain unresolved. One CPU-both and two CUDA-both configs exceed the older 0.001 image diagnostic; the 0.1 descriptive screen is not substituted for it.

## Shared failure and model state

**e10216-01 still exhausts five global iterations for R, R′ and every float arm.** R's last global increment RMSD is about **58.57 px**. Both-conditioned CPU/CUDA maximum global gaps versus R are **0.00451336 / 0.0333941 px**, while product relRMSE is only **2.74996e-5 / 0.000201868**. Both grids remain in all counts; their agreement does not establish successful motion recovery. [The failure table](tables.md#e10216-01-retained-in-all-counts) retains every arm's final RMSD and both product values. Existing exit-0/publication behavior is preserved.

R has no applied local model in six configs: both e10216-01 grids, both e10216-05 grids, e12963-04/p5 and e10474f3-08/p5. Model state and acceptance are reported separately. Only e10216-01 fails R's global iteration criterion in this census.

## Sources, controls and reproduction

Diagnostic source is [`afba50a4cebf5238ec2d267ff3ec07d272b13395`](https://github.com/KingAlejandro/MotionCorr-standalone/tree/afba50a4cebf5238ec2d267ff3ec07d272b13395), retained on **diag/s1-dc-oracle**, with collection tooling also pushed at `95e9d913`. Its uninstrumented parent `31309df0` combines #254 `af2a5900` and #260's production fit/test commits `531e9db4`/`6c23ba1d`, retaining both test registrations. [Diagnostic diff](diagnostic.diff) and [design](DESIGN.md) describe the isolated change. This PR contains evidence and replay tools under docs only.

- `MC_DIAG_CCF_DC=none|global|local|both`, unset=none, zeros only disposable CCF spectrum (0,0) before inverse. CPU, CUDA per-patch/batched paths and retries use the same stage selector. Resident frame spectra, published-image DC and dose weighting are not directly changed.
- `MC_DIAG_CCF_DOUBLE=1` is CPU only. Float weights, frame spectra, subsequent float state, tie/search bounds, guard, convergence and publication policy remain as specified. Full-precision model/global capture avoids STAR coefficient-rounding errors.

| Executable | Source | SHA-256 |
|---|---|---|
| cpu64 CPU Release | afba50a4 | `407678ca8d8c1716f115a8f86bbf72729a985d0691f31e72b888da4c6dd8dbd5` |
| 4GPUs CUDA+nvCOMP Release; CPU controls | afba50a4 | `07a8e83d0b728743c4e9edfd9875dacc5b5f766b088e6aeab158317a4696dbb0` |

Both builds use GCC 13.3.0, FFTW 3.3.10 and **Release -O3 -DNDEBUG**. CUDA uses 12.8.61, sm_80 and nvCOMP 5.3.0.16. All **267** source/CMake blobs match the pinned revision on each host; the uninstrumented parent is independently checked too. [Build/source receipts](raw/build-receipts.json), [CPU source validation](raw/cpu64-source-validation.json), [GPU source validation](raw/source-validation.json) and [toolchain](raw/toolchain.txt) retain exact flags, hashes, build exits and the initial unsuccessful NumPy configure attempt.

All 360 primary CPU processes ran on **cpu64**, six workers with eight-CPU masks within its 64 CPUs. All 240 primary GPU processes ran on **4GPUs**, A100 80 GB PCIe, at most two per-GPU advisory flocks, released between processes, UUID selection and eight-CPU taskset. Actual UUIDs were GPU0 `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54` and GPU1 `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d`; no GPU3 work or lock-file deletion. The [600-run ledger](results/run-ledger.json) retains argv/env, source and binary hashes, affinity, GPU PID/UUID witness, route witness paths and each exit. Shared-host wall times are not performance comparisons.

Controls: **12/12** all-diagnostic-variables-unset CPU/CUDA runs and **12/12** capture-enabled numerical-toggle-off runs reproduce the uninstrumented parent; **18/18** cross-host CPU float/R/R′ controls and **4/4** map-capture neutrality reruns are byte-identical under the same predicate. MRC core header bytes 0:224, payload and movie STAR are compared exactly; timestamp labels and extended headers are reported separately. **30/30** transferred movies, STARs and applicable gains match hashes. No historical numerical run is substituted for a primary arm; #261 supplies recipes, controls and stage buffers.

Run `python3 tools/report.py` to regenerate tables/CSV and `python3 tools/verify.py` to verify the compact package and recompute all **540** native trajectory/field comparisons, admissions and paired counts/statistics. The compact native archive retains run/global/model/resource records; full STARs/movie logs, bulk MRCs, spectra/maps and CCF text remain in scratch; [hash manifests](raw/package.json) bind those retained files in `/mnt/clathrin/alex-motioncorr-dc-oracle/`. Recomputing image metrics requires those bulk MRCs. Verified CPU products were offloaded there before redundant task-specific CPU copies were removed; source corpus files and unrelated work were preserved.

Native **CudaPeakFit**, **CudaHermitianCCF**, **RunnerInterpolateRecenter**, **FloatPlanCache** and **MrcHeaderStats** passed. Full Release CTest suites, controlled performance, independent known-motion accuracy, held-out collections and downstream scientific qualification are **UNRUN in this task**. Inherited CPU bugs remain FILE-ONLY; production defaults/tolerances are unchanged and no merge is proposed.
