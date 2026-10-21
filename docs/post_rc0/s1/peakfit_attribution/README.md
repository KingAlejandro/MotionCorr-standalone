# S1 peak-fit attribution (#238, #257; PR #261)

**Measured:** double peak fitting fixes the same-sample CUDA arithmetic defect, but does not reduce the full-census S1 incidence or the typical final global-trajectory discrepancy. With the original CPU references, A0/A1/A2 have **17/19/16 positives out of 60**; the two matched nulls have **21/15**. Separately conditioning the CPU CCF as well gives **0/60** positives for A2, while the known e10216-01 global-alignment failure persists. This supports a broader float-CCF conditioning mechanism; it does not establish scientific correctness or isolate which remaining FFT/map operations cause the residual discrepancy.

This is a separate evidence-only PR, rather than an extension of #255. The independent production bug fix is [PR #260](https://github.com/KingAlejandro/MotionCorr-standalone/pull/260), [issue #257](https://github.com/KingAlejandro/MotionCorr-standalone/issues/257). No production source, default, gate, tolerance or RC0 qualification state changes here. All experiment results below are native measurements or statistics calculated from them. Performance and S1.4 scientific acceptance are **unrun**.

## 1. Global trajectories and fitted candidates

Original CPU-reference STAR convention, two-dimensional vector error per frame. Every config has max/RMS errors in [per-config.csv](results/per-config.csv) and [primary-60.json](results/primary-60.json). The known e10216-01 failure appears in both grids and remains in all census calculations. It is separated only in these descriptive trajectory summaries.

| Arm | Median max error, other 58 (px) | Worst max, other 58 (px) | Median RMS, other 58 (px) | e10216-01 max / RMS (px) |
|---|---:|---:|---:|---:|
| A0: #254 | 0.03860547 | 0.29827826 | 0.01846299 | 176.94435 / 44.65091 |
| A1: + double fit | 0.03910464 | 0.29474684 | 0.01971349 | 121.27297 / 43.78905 |
| A2: + CUDA DC removal | 0.05378297 | 0.41826637 | 0.02308085 | 166.24502 / 74.69483 |

The first global iteration has **3,120/3,120 identical five float samples and integer winners** between A0 and A1. The native fitted-candidate vector difference is therefore attributable to the fit arithmetic at that iteration. Excluding the failed movie, its maximum is **0.48093727 px**, RMS **0.01327669 px** across 3,002 records; including it, maximum **1.93333054 px**, RMS **0.05160195 px** across 3,120. All records, samples and candidates are in [first-global-candidates.json](results/first-global-candidates.json); later common-iteration comparisons are in [candidate-differences.json](results/candidate-differences.json). Later maps and winners differ after feedback, so their candidate differences are not pure fit-arithmetic effects.

The 0.48094 px witness is e10216-08/p5/frame 1, integer (-1,12): samples `(36301.79296875, 36301.7890625, 36301.73046875, 36302.51171875, 36301.21875)`, candidates A0 `(-2.33333349,30.57894707)`, A1 `(-2.23529410,30.10810852)`. A neighbour outside the searched interval exceeds the selected peak; the inherited unbracketed-fit policy is unchanged. This is not a new interpolation-validity policy. The earlier audit's 0.13525164 px replay maximum was already in scaled image/patch pixels; it was not a bound over this census or over accumulated trajectories.

## 2. Full-census incidence and controls

The screen is #255's **image relative RMSE ≥0.1**, distinct from the comparator's backend gate. All 60 configurations are analysed, including regressions and the failed movie. Exact two-sided McNemar uses discordant configuration counts, as #255; the two grids of a movie are correlated, so nominal p values are descriptive config-unit statistics, not independent population/scientific evidence. No multiplicity adjustment is applied.

| Family | n | A0 | A1 | A2 | N1 | N2 |
|---|---:|---:|---:|---:|---:|---:|
| 10216 | 20 | 7 | 10 | 6 | 10 | 8 |
| 12963 | 20 | 9 | 7 | 9 | 10 | 6 |
| 10474 Falcon 3 | 20 | 1 | 2 | 1 | 1 | 1 |
| All | 60 | **17** | **19** | **16** | **21** | **15** |

Cells are `(++, +−, −+, −−)`, with the left arm first.

| Contrast | Cells | Exact p |
|---|---|---:|
| A0→A1 | (13,4,6,37) | 0.75390625 |
| N1→A1 | (16,5,3,36) | 0.7265625 |
| N2→A1 | (15,0,4,41) | 0.125 |
| A1→A2 | (11,8,5,36) | 0.5810546875 |

[Tables by family and grid](results/tables.md), [all primary transition tables](results/primary-transitions.json), and the per-config CSV retain the complete matrix. No positive-only selection is used.

**A0 replay:** all **60/60** diagnostic A0 outputs match the actual #254 parent in MRC core header/payload and per-movie STAR bytes. Labels containing timestamps and extended headers are reported separately by `identity.py`, not silently called full-file equality. For 42 configs the parent products are those retained by #255. Its runner had deleted 18 CPU MRC references (nine movies originally run on SCARF); only those were regenerated on 4GPUs with frozen-F CPU, original inputs/STAR/recipe. For all 18, regenerated CPU STARs are **byte-identical to #255's archived originals**, and the actual #254 replay reproduces #255's relRMSE to every published seven-digit value. A0 has exactly #255's 17 positives. See [regenerated-reference controls](results/regenerated-reference-star-controls.json), `control_pr255` in the primary rows, and the native archive identity records. The old CPU reference was never silently replaced by DC-conditioned output.

**Neutrality:** all six A1 capture-off controls reproduce A1, and all six final-null toggle-off controls reproduce A0, with the same core-header/payload/STAR identity predicate. A0's full-60 parent replay also validates its capture/DC-toggle-off instrumentation. `MC_DIAG_ZERO_CCF_DC` is enabled by variable presence; **off means unset**, not `=0`. Null off means unset/zero. These controls are retained in `raw/experiment-logs.tar.gz` and native records.

**Matched null:** A0's actual native float candidate is perturbed after fitting, before reference subtraction and normal feedback. Each axis receives a random sign times the magnitude of the promoted-minus-native candidate evaluated on that frame's own five float samples, with the unchanged scale and final float store. Seed/patch/iteration/frame determine signs; seeds 1 and 2 are used. This preserves the per-frame correction's axis magnitudes/vector norm before output rounding, analogous to #255's own-frame row-dose null. It is a **conditional same-map mechanism-dose null**, not a match to final accumulated A1−A0 trajectory magnitudes after the maps have diverged. Across **120 config/seed pairs and 510,732 records**, exact sign/output replay has **zero mismatches**; largest axis magnitude rounding error is `7.62939453125e-6` px and actual/target RMS ratios range `0.99999969794–1.00000004399`. [Validation](results/null-validation.json) and every `null-dose.txt` are retained. The superseded host-float-baseline null was preliminary and is excluded from the final census.

### Fairness check: CPU DC conditioning

CPU already fits float samples in double, but can still lose contrast when forming float CCF maps. It therefore cannot be assumed insensitive to DC removal. Six initial paired controls showed CPU-only product relRMSE changes as large as **0.59382516** and global changes up to **0.05655004 px** ([controls](results/cpu-dc-controls.json)). This required a separate full-60 conditioned-CPU comparison for a fair bilateral conditioning test.

The **primary** A2 result above keeps the original CPU references, as requested. The **secondary** comparison in [conditioned-cpu-60.json](results/conditioned-cpu-60.json) uses CPU DC removal at the same pre-CCF-inverse point; no references are substituted in the primary analysis. Against this CPU, A0/A1/A2 have **17/20/0** positives; A1→A2 cells `(0,20,0,40)`, exact p `1.9073486328125e-6`. [Conditioned transition tables](results/conditioned-transitions.json) include every family/grid.

Against conditioned CPU full-precision native global captures, A2's other-58 median maximum error is **0.00000559418 px**, worst maximum **0.00038213949 px**, median RMS **0.00000241748 px**. Other-58 product median relRMSE is **0.00044309191**, worst **0.00136670080**. These small residuals remain unattributed. The failed movie's max/RMS global difference is **0.03790745/0.00493520 px** and product relRMSE **0.00022900919**; agreement does not repair its failure to converge. STAR rounding is used for primary/#255 comparisons, full-precision capture for this secondary diagnostic (explicitly distinguished in the JSON/source).

Zeroing the spectrum's DC bin subtracts a map constant in exact arithmetic: peak **values** change, while exact peak positions and curvature do not. Native float FFT/map arithmetic and subsequent feedback can change both. This ablation conditions both global and patch CCFs; it does not separate their contributions or prove that fit arithmetic alone explains S1.

## 3. Residual first-divergence witnesses

For the **19 A1 + 16 A2** fixed-reference positives, all 35 arm/config entries have native CPU/CUDA captures. [Residual witnesses](results/residual-witnesses.json), [35-row table](results/tables.md#residual-fixed-reference-positive-witnesses) and `raw/divergence-captures-analysis.tar.gz` retain the classification. “First” uses #255's >0.5 px fitted-candidate separation, preferring its S1-relevant accepted-patch screen (acceptance flip or >1 px final-trajectory separation). Smaller arithmetic differences can precede the reported event; no causal claim is made from a later witness alone.

- **27 different-integer witnesses with changed map ordering:** paired native samples establish the selected-order change. Eighteen of these have full-frame CCF dumps, exactly matching the baseline five samples, and byte-identity product controls for the observational reruns; the other witnesses' two peaks are present in the retained five-sample/separate-maximum records. Absolute margins, CPU-baseline ULPs and CUDA-own ULPs are retained. CUDA-own ULP counts after DC removal are not comparable to pedestal-map ULP counts.
- **One exact-tie witness**, 12963-02/p5/A1: both cross-peak margins are zero. A CPU-style scan of the same CUDA map selects (-11,-2), while CUDA selects (0,0), two tied maxima, with a full-frame map retained. Reduction/scan tie order contributes; this case cannot be attributed solely to unique-peak ordering on different maps.
- **Two same-integer/different-candidate witnesses**, 12963-04/p5 in A1 and A2. Their five samples differ between CPU and CUDA; these are not evidence that double arithmetic gives different answers on identical samples. The unbracketed near-flat fit amplifies the sample changes.
- **One subthreshold case**, 12963-05/p5/A2: no accepted-patch candidate event exceeds 0.5 px under that convention, despite the positive image screen. Its smaller fitted/accumulated differences are retained explicitly rather than forced into an integer-jump category.
- **Four entries (two grids × two arms)** are the known e10216-01 both-backend global failure. All five global iterations are exhausted. Last global increment RMSD is CPU-original **51.62225 px**, CPU-DC **58.56911**, A0 **62.16958**, A1 **61.91827**, A2 **58.56882**. Processes still exit 0 under the existing publication policy; run success is not alignment convergence.

## 4. 12963

Original-reference counts are **9→7→9/20** (A0→A1→A2). A0→A1 cells `(5,4,2,9)`, p **0.6875**; A1→A2 `(5,2,4,9)`, p **0.6875**. There is no established response to the production fit fix. In the separate conditioned-CPU comparison, A1→A2 is **9→0/20**, p **0.00390625**. Thus bilateral CCF conditioning responds on this family too; unilateral A2 against the original CPU does not establish that result.

## 5. Global-only product reach

Thirty unique movies, patch arguments removed and `--save_noDW`; two existing #255 CPU global-only products reused, the missing 28 generated. [All DW/non-DW measurements](results/global-only-30.json) are separate from the 60 local-alignment configs.

| Arm | Median DW relative RMSE | Median non-DW relative RMSE |
|---|---:|---:|
| A0 | 0.02457966371 | 0.03060033503 |
| A1 | 0.02827185853 | 0.03107158000 |

The fit fix does not improve the median product discrepancy. The failed movie remains included in these medians. No downstream resolution, truth accuracy or performance conclusion follows.

## Sources, execution and retained evidence

Primary corpus, selection, CPU reference convention and S1 screen are exactly [PR #255](https://github.com/KingAlejandro/MotionCorr-standalone/pull/255) at `23a320a65aafaa41631a051f49e2c36ad99092dd`: 10216, 12963, 10474 Falcon 3 × ten movies × 5×5/3×3. Read its census README and #250's `docs/post_rc0/s1/README.md` for the original CCF/trajectory conventions. [Input manifest](results/input-manifest.json) hashes the actual 30 movie files, gains and original STARs used here.

| Arm | Exact diagnostic source | Executable SHA-256 |
|---|---|---|
| Frozen-F CPU (18 regenerated references) | `6d68e2d6ec45c37b75fd0f4aaff8272f192b7029` | `43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42` |
| Actual #254 parent | `8b55d5dae8815e4648758620750496e4acd533c5` | `71e226f174dd58e91d6cde200e339ccc4be31ce99cc3c57dd273871633b4cb3e` |
| A0 / diagnostic CPU | `4837b2100bcbf436cb88896a50a082f788bb3e29` | `473587594d839b46b07e3990fdaf6bdd54e3c920bc692d550da89cc1f4183e7e` |
| A1 / A2 | `9a83438049507edc98fe96103ed8d1e92d63e065` | `d44cb5289d7d0844de1e8af4aefe317e2f990ed0a7caf725b6065fc636468603` |
| N1 / N2 | `7fe2864e0add90e8b871de62ce3ee26b28a880d8` | `3246149c9ed52b98b642d70b4f86e3c149b8844a3fa2817b2a1d3eea62cb1282` |

A0 reapplies #250's observation-only captures to #254 and adds disabled DC/null diagnostics. A1 adds #257's exact double-fit kernel hunk plus a host-emulation diagnostic flag. A2 uses the same A1 executable, DC variable enabled. N uses A0's production float kernel with native-baseline null addition. These commits are retained on `diag/s1-peakfit-attribution` and `diag/s1-peakfit-null-native`; [A0](diagnostic-A0.diff), [A1](diagnostic-A1.diff), [N](diagnostic-N.diff) diffs reconstruct them from #254/A0 as indicated in the filenames and table. Diagnostic changes are never part of production PR #260. Its implementation revision is `531e9db40c10799627e7a06efd9462f16e868a1f`; final test source `6c23ba1d10364507db39c51745af5a7a2dbf0c06`.

All pooled native results ran on **4GPUs**, A100 80 GB PCIe, GCC 13.3.0, CUDA 12.8.61, sm_80, nvCOMP 5.3.0.16; **Release `-O3 -DNDEBUG`**, configure/build exits 0 ([actual source/build validation](raw/source-validation.json)). Each movie is a separate process with eight CPUs, UUID GPU selection, `/tmp/motioncorr-gpu{0..3}-correctness.lock` flock, and descendant-process `nvidia-smi` UUID witness. No lock file was deleted. Actual lanes were GPU0 `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54` (96–103), GPU1 `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d` (104–111), GPU2 `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598` (112–119); GPU3 remained occupied by unrelated work and was not used. CPU captures/conditioning used valid eight-CPU lanes. Shared-host wall times are not benchmarks.

The unchanged original sweep argv/cwd are loaded by `tools/run_c.py`, replacing binary, output/witness paths and assigned lane; no movie batching, altered tolerances or input resampling. `--gpu 0` addresses the single UUID exposed through `CUDA_VISIBLE_DEVICES`. The standalone scalar C++ metric helper uses the original population-standard-deviation denominator, avoiding NumPy for 4GPUs analysis. A macOS cross-check with the canonical comparator gives relRMSE `0.017329073824470687`, versus scalar `0.017329073824470683`; its backend-gate failure is retained under `raw/canonical-check` and is not misreported as a pass.

`raw/native/run-ledger.json` retains **540 successful selected run records**, including all 300 primary GPU runs, all 60 conditioned-CPU runs, native map probes, neutrality, parent replays and new global-only runs. Each has argv, environment, source/binary hash, affinity, exit and actual GPU witness. All selected exits/8-CPU masks and GPU UUIDs were checked; the 300 primary runs have exactly 60 entries per arm. `raw/native/*-{p3,p5,global}.tar.gz` retain their CCF/global/null captures, STARs, logs, metrics and identity records. `original-references.tar.gz` retains all 60 original-reference metadata/STAR records; `reused-cpu-captures.tar.gz` carries the four reused #250 observation captures. `capture-manifest.json` hashes the 5,608 selected native files. Full product MRCs, complete map stacks and superseded null runs remain in `/mnt/clathrin/alex-motioncorr-peakfit` (old references in `/mnt/clathrin/alex-motioncorr-s1/sweep`, controls in `/mnt/clathrin/alex-motioncorr-s1ccf`); bulk images are not committed. Selected 19 paired full-frame maps are in `raw/first-map-frames.tar.gz`, hashes/dimensions in the witness JSON.

Administrative attempts are excluded from measurements: one CPU capture requested 120–127 on a host ending at CPU123, was intentionally terminated (exit143), retained, and rerun on eight valid CPUs; GPU3 drivers blocked before payload execution and were moved to available locked lanes. SCARF allocation **3664104**, gn0003, eight CPUs/CUDA12.8/TMPDIR=/tmp, had slow/incomplete home-path operations and a capture-retry setup failure. Its partial results were not pooled; only our allocation was cancelled after the complete 4GPUs fallback. [Cancellation receipt](raw/mc-scarf-cancellation.txt) records cancelled/nonzero steps, not numerical passes. Unrelated jobs and services were left alone.

### Reproduce and verify

From this directory, `python3 tools/summarize.py` regenerates the small per-config CSV and review tables without NumPy. `python3 tools/verify_evidence.py` checks the native archive contents against the capture manifest, archive hashes, all primary run/source/UUID/affinity controls and the reported count/statistics invariants. Its retained report is `raw/verification.json`. The native run scripts/build recipes are in `tools/`; earlier SCARF/capture script versions are retained as administrative history, and the final paths/venues are the ones in the run ledger. The #255 analyzer is copied as `tools/s13-analyze.py`; full trajectory/event analyses and their CPU/movie identity checks are retained for replay. Scripts with `/tmp` paths record the original analysis workspace, rather than constituting a portable package installer.

Remaining unexplained: the original-reference CPU–CUDA global gap after double fitting; the small residual under bilateral conditioning; inherited exact-tie/unbracketed-fit and global-failure publication behavior; how much global versus local conditioning contributes; downstream scientific effect and production performance cost. No S1 closure or merge is recommended from this screen alone. Required production Release CPU/CUDA/nvCOMP CTests and their limits are recorded separately in [#257 evidence](https://github.com/KingAlejandro/MotionCorr-standalone/blob/d888ab111b1965aeda484a928e76f421112737e0/docs/post_rc0/issue257/README.md).
