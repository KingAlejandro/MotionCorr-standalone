# Native B2 CPU prototype: sealed bounded pilot

**Candidate promotion remains blocked by real K267 noisy harm.** The implementation and four-movie characterization task is complete; no merge/default change, full100 expansion, or general scientific qualification is established.

PR [#287](https://github.com/KingAlejandro/MotionCorr-standalone/pull/287), based exactly on PR286 source`4fa272f6c3cb5cec35d98b270ed1c4067adf6160`. Production source reviewed at`326f03a073aec0d26c9cd585ce4f701d1c808245`; subsequent commits change tests/research tooling/evidence only. Binary SHA256`531a1b0984dfbb39bd1b43afa23561091365a4d0459967ef5ee24ca69344c2eb`.

## Implementation and validation

`--experimental_local_b2` defaults off; CPU/use_own, group_frames1, bin_factor1, no interpolation. GPU and unsupported scope are refused before pixels/device query. Fit integer-time physical h(f), k1..3, with per-patch nuisance constants eliminated orthogonally; scaled pivoted Householder QR, spatial rank6, >=4 times/patch and full18+npatch rank. Nuisance is never applied/published; h(0)=0 exactly. The flag intentionally changes the RMS estimand and thus flagged acceptance behavior: nuisance-adjusted residual against the existing numeric10px threshold. This is not a truth metric.

- **PASS:** native Release build of motioncorr/local_b2_fit; selected CTests LocalB2Fit and ExperimentalFlagsCli (2/2). Analytic linear/quadratic/cubic/full18 fields, offsets, noisy B1/C equivalence, zero gauge, rank/nonfinite rejection, midpoint mutants and CPU-build GPU refusal. Independent source review CLEAR; physical h0 correctness is not general accuracy.
- **PASS identity/publication only:** all8 K267 OFF outputs match pinned baseline using the existing product comparator plus raw caseSTAR witnesses; all16 N-control OFF/ON runtime and products match. All14 N40 producer exits0 and expected outputs complete; all4 OFF STAR/runtime and sum payloads match pinned H7; all repeat outputs deterministic. See [verification](native_results/verification-summary.json), [source/build/hardware](native_results/build-source-hardware.json), [selected CTest log](native_results/selected-ctest.log).
- **UNRUN:** full CPU qualification/TierA formats (pbzip2 absent), native GPU/CUDA parity, full100, broad science/performance qualification. CUDA compile CI is not GPU execution. Final-head CI is recorded separately; result review remains parent-owned.

## Four frozen movies: runtime and actual written/read-back STAR

RMS / p95 / max in Å on the unchanged129x129 fixed-ROI lattice; limits0.20/0.40/0.80Å. Full precision is retained in the linked JSON.

| Movie | Runtime OFF | Runtime B2 | Runtime classes OFF→B2 | B2 vs W8 max vector px |
|---|---|---|---|---|
| dose1-s01 | 0.229926119 / 0.424117881 / 0.702293087 | 0.153929595 / 0.273522759 / 0.535522565 | FAIL → PASS | 3.38097106e-06 |
| dose05-s00 | 0.374709159 / 0.696921891 / 1.700276406 | 0.235235130 / 0.401516230 / 0.589428343 | FAIL → FAIL | 2.66594071269e-06 |
| dose4-s00 | 0.083762079 / 0.165812907 / 0.289033143 | 0.084522819 / 0.162939758 / 0.513834609 | PASS → PASS | 4.60232249382e-06 |
| pedestal32-s00 | 1.430188622 / 2.452505466 / 3.846626129 | 1.430188622 / 2.452505466 / 3.846626129 | FAIL → FAIL | 0 |

| Movie | Actual STAR OFF | Actual STAR B2 | STAR classes OFF→B2 | Local enabled; accepted/rejected patches |
|---|---|---|---|---|
| dose1-s01 | 0.229758779 / 0.423565084 / 0.701195209 | 0.153852364 / 0.273409757 / 0.535368601 | FAIL → PASS | True/True; 25/0 both |
| dose05-s00 | 0.374697687 / 0.696696341 / 1.701033510 | 0.235146683 / 0.401333860 / 0.589390666 | FAIL → FAIL | True/True; 25/0 both |
| dose4-s00 | 0.083627358 / 0.165555536 / 0.287276381 | 0.084403618 / 0.162640226 / 0.510673779 | PASS → PASS | True/True; 25/0 both |
| pedestal32-s00 | 1.430188631 / 2.452505380 / 3.846626091 | 1.430188631 / 2.452505380 / 3.846626091 | FAIL → FAIL | False/False; 0/25 both |

All4 sampling classes are VALID. Global converges for the three dose cases and fails for pedestal32 in both arms. No observation/global or local-selection change: first3 keep25/25 patches; pedestal32 rejects25/25 and stays exactly global-only. dose05 still fails; dose4 retains the predicted RMS increase and high-tail regression (runtime max0.289033143→0.513834609Å; real STAR0.287276381→0.510673779Å). No favorable PASS count erases either regression.

The pre-run native-vs-offline comparison bound was0.01313142874082845px, derived independently from signed STAR precision and conditioning. Largest measured difference4.602322493821259e-6px. This is distinct from scientific gates. Actual B2 STAR roundtrip max field loss is0.004549545px (dose1),0.002602294px (dose05),0.003911828px (dose4); classes stay unchanged. W8 only had runtime/global-plus-full-precision-coefficient hybrid fields; this native pilot closes its previously UNRUN actual coefficient writer/readback step.

## Retained tiny failures and independent challenge

| K267 case | OFF numeric field class | B2 numeric field class | Checker OFF/B2 accuracy | Checker OFF/B2 sampling |
|---|---|---|---|---|
| zero | PASS | PASS | PASS / PASS | VALID / VALID
| integer | FAIL | FAIL | FAIL / FAIL | VALID / VALID
| fractional | FAIL | FAIL | FAIL / FAIL | VALID / VALID
| affine | FAIL | FAIL | FAIL / FAIL | VALID / VALID
| pedestal | FAIL | FAIL | FAIL / FAIL | VALID / VALID
| noisy | FAIL | FAIL | FAIL / FAIL | OUTSIDE_FIXED_ROI / OUTSIDE_FIXED_ROI
| flat | FAIL | FAIL | UNIDENTIFIABLE / UNIDENTIFIABLE | VALID / VALID
| repeated | FAIL | FAIL | UNIDENTIFIABLE / UNIDENTIFIABLE | OUTSIDE_FIXED_ROI / OUTSIDE_FIXED_ROI

**Noisy harm:** fixed-ROI runtime RMS2.342955203→3.587249812Å, max9.903898811→19.563704822Å; actualSTAR agrees on failure. Both local_enabled true, same9 converged patches, same nonconverged global trajectory and byte-identical observations. Both sampling OUTSIDE_FIXED_ROI, application consistency NOT_TESTED; field characterization does not qualify the applied image. Affine improves0.402437365→0.317173765Å but still fails. Flat/repeated checker identifiability remains authoritative, independently of numeric field limits.

All8 production-weight N5/9/13/20 velocity controls remain FAIL; isotropic control7PASS/1FAIL is unchanged. Harmful native vel1-N20-iso trajectory RMS11.858575180641232px, runtime field RMS10.494839034867491Å/max14.859851902178468Å, matches the retained PR286 native runtime exactly. It is distinct from the historical offline11.833px label; that old failure is not rewritten.

Native B2 matches independent NumPy/W8 fits on rounded tiny observations to1.1367e-5px (full border), within the diagnostic rounding bound. Rank/QR/time/selection/serialization do not explain the bounded noisy regression. Independent [Gemini4Argon report](independent_gemini4argon/REPORT.md) and [verified provenance](independent_gemini4argon/PROVENANCE.md) are copied verbatim with scripts/results/hashes. At common-grid N5, cubic+intercept has endpoint hhat4=y4−y0=L4 before spatial projection; inherited final L4 gain≈0.4303. Raw observation row-L2 sensitivity is not stochastic variance under correlated Tr observations. B2 has lower expected variance under the stated iid equal-variance L/epsilon reference models, yet transmits these retained endpoint outliers more strongly. Outlier norm/counterfactual ratios are not causal shares; upstream global nonconvergence can still affect observations indirectly. [Author preregistered challenge](TINY_DIAGNOSTIC_PLAN.md), [results](tiny_challenge.json), [exploratory fit](tiny_diagnosis.json).

## Descriptive timings, same fixed production movie

cpu64 guest: AMD EPYC7763,64 visible CPUs; whole-chain affinity32–47,8 OpenMP threads requested, maximum16 allocation. All timings same binary/input/config; unprofiled native producers, wall includes process startup and whole-job publication/exit. Peak RSS and exact commands live in verification/RUN/time receipts. Early ABBA/AA had per-run preflight/leases only; later live samples observe8–9 process threads (ingest coordination included), affinity32–47. No continuous-monitor claim for early pairs.

| Fixed order on dose1-s01 | Whole-job seconds | Peak RSS KiB |
|---|---|---|
| OFF1 | 10.029672801 | 5587984 |
| ON1 | 10.007855043 | 5588732 |
| ON2 | 10.232917912 | 5605232 |
| OFF2 | 10.318967175 | 5620496 |
| OFF_AA1 | 10.098509941 | 5587780 |
| OFF_AA2 | 10.181655686 | 5587596 |
| OFF_AA3 | 10.123640291 | 5605336 |
| OFF_AA4 | 10.019931011 | 5605732 |

Mean ON/OFF=0.994699055; OFF/OFF null ratios=1.008233467, 0.989755732. The apparent−0.53% difference is smaller than the observed null-pair changes (+0.82%,−1.02%). No stable speedup or overhead estimate; no optimization/profile integration. CPU contention was observed and correctly blocked an earlier pre-producer attempt; resolved before this campaign. Per-job and late live snapshots show no high-CPU foreign overlap; unobserved transient interference is not excluded.

## Applied-image report only

Initial image attempts failed before analysis because SciPy was absent from the base venv. Versioned wrapper uses unchanged checker plus pinned NumPy2.5.4/SciPy1.18.1; [dependency/metadata preflight](native_results/image-v2-preflight.json), [seven unique-payload reports](native_results/image-reports-v2.json). Actual generated receipts and one verified-common-scene detector truth cache are retained outside Git. No native/movie regeneration, image PASS, signal gate, or scientific qualification.

| Movie/arm | Interior transfer in-band | Interior FRC in-band | Border relative RMS |
|---|---|---|---|
| dose1-s01 OFF1 | 0.991423024 | 0.675899102 | 2.744831866 |
| dose1-s01 ON1 | 0.992077759 | 0.675368863 | 2.786061412 |
| dose05-s00 OFF1 | 0.991609596 | 0.544597004 | 3.907688619 |
| dose05-s00 ON1 | 0.993945503 | 0.544336171 | 3.964329168 |
| dose4-s00 OFF1 | 0.992043850 | 0.877723791 | 1.410554344 |
| dose4-s00 ON1 | 0.992791643 | 0.877286337 | 1.427295926 |
| pedestal32-s00 OFF1 | 0.941087863 | 0.636603206 | 3.975998553 |

Pedestal32 ON shares exactly the OFF payload and report. For dose cases, transfer rises slightly while in-band FRC falls slightly and border RMS rises. Per-band transfer/FRC and border profiles are retained in each report; no overall image-improvement claim.

## Failure ledger, reproducibility and scope

- Original STOP: aggregate STAR output-root differences mistakenly compared raw. V2 used targeted root normalization; final V3 invokes the unchanged existing comparator plus exact raw caseSTAR witness, exact file sets and size checks. Copy-only root/numeric/basename/missing/extra controls pass. Original producers reused, never silently rerun.
- Original STOP-v2: nicholls foreign PID3491640, CPU33, allowed0–63, elapsed1:34,100%CPU; cwd unavailable to ubuntu. No signal/job change. Natural exit verified; no narrowing/bypass. All earlier receipts remain.
- Local comparator-copy fixture initially used macOS /var alias; initial failure retained, fixture canonicalized before passing controls.
- K267 noisy harm triggered a scientific hold and retained-only diagnosis. Parent additive pre-run amendment released only four unchanged N40 characterization movies. Harm remains a promotion blocker.
- A helper import transiently created3 task-owned Python3.15 bytecode caches in the read-only W8 input tree. Only those14:14:14 caches were removed; helpers now disable bytecode. All original tracked W8 source/evidence checksums pass; the cleanup receipt/log is retained.
- Original missing-SciPy image failures remain; separate v2 reports use existing pinned dependencies. No new native producers for reporting.

[Frozen design/predictions](DESIGN_PLAN.md), [input pins](input_pins.json), [rounding prediction](rounding_prediction.json), versioned amendments/scripts and independent reports are committed. Tiny input hashes were audited retrospectively, not separately precommitted; this is explicit in [their receipt](native_results/retrospective-control-input-hashes.json). Real-scale movie/recipe/generator/expectation hashes were committed before native pilot and every regenerated movie matched its receipt exactly.

Raw scientific images, actual receipts, logs, resource observations, all failed attempts, binary and launch scripts are sealed outside Git at `cpu64:/home/ubuntu/motioncorr-evidence/native-b2-20261026/`; raw index/READY bind their hashes. This Git directory contains compact receipts and summaries. Final branch/head/CI state is reported in the PR evidence comment; no merge recommendation. No jobs remain from this task. No next factorial or full100 producer has run.

Seal:1466 indexed raw files,1,069,023,998 bytes; every scratch-evidence byte verified against durable copy. RAW_INDEX SHA256`6fc75dbee0d4b2dd1f76c7a5d8359abb2d72b1a6e8a7c1f59ab5978bd947d91a`; see [RAW_INDEX](native_results/RAW_INDEX.json) and [READY](native_results/READY.json).
