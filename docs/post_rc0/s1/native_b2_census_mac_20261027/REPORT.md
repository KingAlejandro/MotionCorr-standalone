# Mac replicate census, not hash-identical to the frozen census

**Completed:** 100 regenerated production-size movies, 500 main-arm native CPU
producers plus one first-movie binary identity producer. All 501 native exits
were 0; all 501 final scores succeeded. The initial scorer import failure is
retained, with its native OFF result reused without a producer rerun.

This is a NEW macOS arm64 / Apple M4 Pro venue. It establishes synthetic native
field accuracy on these locally generated replicate inputs, with actual STAR
serialization measured separately. It does not establish Linux byte identity,
GPU execution, general image improvement, stable performance or adoption.

## Pass counts

Runtime and actual written/read STAR verdicts agree on **every one of the 500
main-arm results**. Both fields have these counts:

| Population | OFF | B2 | UP | UPFW | FW |
|---|---:|---:|---:|---:|---:|
| In-model, 80 | 22 | **68** | 22 | **41** | **41** |
| Remaining diagnostics, 20 | 0 | 0 | 1 | 3 | 0 |
| └ outmodel, 10 | 0 | 0 | 0 | 0 | 0 |
| └ pedestal32, 10 | 0 | 0 | 1 | 3 | 0 |
| All 100 | 22 | 68 | 23 | 44 | 41 |

The 80 in-model movies include the 10 nonsquare movies. The remaining 20 are
reported as two distinct diagnostic groups: pedestal32 has an in-model motion
recipe but severe upstream/global convergence problems, so it should not be
described as an out-of-model motion recipe. UP passes pedestal32-s02; UPFW
passes pedestal32-s01, s02 and s08.

[Per-condition counts](replicate_results/conditions.md) ·
[every movie, both fields, all five arms and local hashes](replicate_results/per_movie.csv) ·
[full summaries and all population/P6 strata](replicate_results/summary.json).

## Frozen predictions

The [original amendment](REPLICATE_AMENDMENT.md), including the orchestrator's
decision verbatim and P1–P6, was committed at
`154661ba1bd733ac7993281fa895bfcd3a26b222`. The
[five-arm extension](REPLICATE_AMENDMENT_v2.md) and Q1–Q4 were committed at
`8f5e92556dbd338de058666d541d4a901aa276a5`. Both precede generation and every
replicate arm. No backfill was needed.

| Rule | Result, runtime and STAR separately | Verdict |
|---|---|---|
| P1: agreement with W8 per movie | Replicate inputs; no native-versus-W8 field test | **UNTESTABLE on replicate inputs** |
| P2: B2 in-model passes exceed OFF | 68 versus 22 in both fields; 46 rescues, zero losses | Supported |
| P3: list every OFF-pass/B2-fail, retaining metric/tail harm | None in either field; all metric regressions listed below | Reporting complete |
| P4: per-movie OFF/B2 wall times, descriptive only | All times retained; substantial changing contention | Reporting complete; no speedup claim |
| P5: OFF agreement with frozen Linux verdicts, no threshold | **100/100** in runtime and **100/100** in STAR; **no flips** | Agreement reported |
| P6: report differing totals or absolute squared-sum difference >1000 | **0/100 flagged**; every total agrees; largest absolute squared-sum difference **406** | Reporting complete |
| Q1: FW beats OFF in more in-model movies than not | RMS lower/higher 79/1, both fields; exact p = 1.34003259234e-22 | Supported |
| Q2: FW in-model passes ≥ OFF | 41 ≥ 22, both fields | Supported |
| Q3: list OFF-pass/FW-fail and UP-pass/UPFW-fail | None across all 100 movies in either field; metric harms remain | Reporting complete |
| Q4: UPFW versus UP as Q1–Q3 | RMS 79/1 in-model, both fields; passes 41 versus 22; zero pass-to-fail | Supported for the stated count/RMS rules; all harms reported |

P5 is a verdict comparison, not a claim that fields or products equal Linux.
P6 uses receipt pixel moments and the exact declared grid reconstruction; the
underlying Poisson-count moments are also retained for pedestal/scale arms.
[All 100 P6 comparisons](replicate_results/P6_moments.csv) and
[P5 agreement/flip records](replicate_results/P5_agreement.json) are inspectable.
The P6-flagged stratum is **empty**, not a tested passing subgroup. All 100
movies belong to the explicitly reported unflagged stratum; none was omitted
or silently excluded from the 80/20 counts. The maximum squared-sum difference
406 occurs on dose4-s02. The precise original-versus-Mac pixel maximum remains
unmeasured; the orchestrator's recorded admission decision is not a pixelwise
measurement.

## Paired sign tests

Lower/higher refer to truth-field RMS of candidate versus reference; exact ties
are excluded from the two-sided binomial sign test. No regression tolerance is
introduced. The shared-noise design means the 80 movies are **not 80 independent
noise realisations**; these per-movie p-values are descriptive.

| Pair | Field | In-model lower / higher / ties | Two-sided exact p |
|---|---|---|---:|
| B2 / OFF | Runtime | 80 / 0 / 0 | 1.65436122511e-24 |
| B2 / OFF | Actual STAR | 79 / 1 / 0 | 1.34003259234e-22 |
| FW / OFF | Runtime | 79 / 1 / 0 | 1.34003259234e-22 |
| FW / OFF | Actual STAR | 79 / 1 / 0 | 1.34003259234e-22 |
| UPFW / UP | Runtime | 79 / 1 / 0 | 1.34003259234e-22 |
| UPFW / UP | Actual STAR | 79 / 1 / 0 | 1.34003259234e-22 |

The paired pass/fail discordance test is also retained: B2 has 46 rescues and
zero losses in-model (p = 2.84217094304e-14); FW and UPFW each have 19 rescues and
zero losses against their respective references (p = 3.814697265625e-6).
Across all 100 movies, B2 runtime is 90 lower / 0 higher / 10 ties and STAR is
89/1/10; FW is 92/5/3 in both fields; UPFW is 98/2/0 in both fields. Full tests
for the 80/20, outmodel/pedestal32, all-100 and P6 strata are in
[summary.json](replicate_results/summary.json).

## Every regression remains visible

There are **zero pass-to-fail movies** for B2/OFF, FW/OFF and UPFW/UP, in both
runtime and STAR, across all 100. This does not erase numerical harm.

- **B2/OFF:** dose4-s00, outmodel-s01 and outmodel-s07 have at least one metric
  increase. [Every runtime/STAR increase](replicate_results/B2_vs_OFF_regressions.md).
- **FW/OFF:** contrast025-s05, contrast4-s09, dose05-s02, dose1-s09, dose2-s03,
  outmodel-s07, pedestal0-s09, and pedestal32-s01, s02, s04, s06, s07, s08.
  [Every runtime/STAR increase](replicate_results/FW_vs_OFF_regressions.md).
- **UPFW/UP:** contrast025-s09, contrast4-s09, dose05-s02, dose1-s09, dose2-s03,
  outmodel-s07, pedestal0-s09 and pedestal32-s09.
  [Every runtime/STAR increase](replicate_results/UPFW_vs_UP_regressions.md).
- **UP/OFF:** the additional upstream comparison is fully retained too:
  [every affected movie and metric](replicate_results/UP_vs_OFF_regressions.md).

All 372 strict metric-increase rows across these four comparisons are in
[CSV](replicate_results/metric_regressions.csv) and
[JSON](replicate_results/metric_regressions.json); the three primary comparisons
account for 6 B2, 42 FW and 32 UPFW rows.

The expected dose4 tail harm persists: on dose4-s00, B2 runtime maximum rises
**0.295874067621 → 0.518192992249 Å**. Actual STAR maximum rises
**0.294880218659 → 0.520166327601 Å**, and STAR RMS rises
**0.0849853946547 → 0.0851120256298 Å**. Runtime RMS slightly decreases on this
Mac replicate; the Linux pilot's runtime-RMS increase is not relabelled as a
Mac measurement. Both arms still pass all limits on this movie.

FW has substantial diagnostic harm despite its in-model gains. For example,
pedestal32-s04 runtime RMS rises **1.40186067944 → 2.58122243115 Å**;
pedestal32-s02 maximum rises **4.94155585439 → 9.61556923073 Å**.
UPFW worsens all three metrics on outmodel-s07 (runtime RMS
**0.901105749284 → 0.910487401810 Å**). These failures are not excused by pass
counts or the favourable in-model sign tests.

## Descriptive timings and resource context

Same per-movie input, one run per arm, fixed order OFF, B2, UP, UPFW, FW. The
first movie additionally ran the identity arm immediately after OFF. Whole-job
wall times include `/usr/bin/time -l`, startup, publication and process exit;
generation and scoring are excluded. No randomisation, repeat-based precision,
matching-contention guarantee or speedup/overhead inference.

| Arm | Median seconds | Mean seconds | Minimum–maximum seconds |
|---|---:|---:|---:|
| OFF | 9.099088 | 13.413099 | 7.627614–138.735110 |
| B2 | 8.232124 | 11.542754 | 6.336284–96.967998 |
| UP | 8.310610 | 11.750270 | 6.566087–99.964926 |
| UPFW | 8.155758 | 12.005667 | 6.462316–122.273596 |
| FW | 8.169985 | 11.515132 | 6.494090–83.655621 |

[The complete 100-movie timing table](replicate_results/timings.md) retains the
slow section; it was not discarded or rerun. A
[resource snapshot](replicate_results/resource-contention-snapshot.json)
records heavy swap use and unrelated activity during dose05-s03. Each native
run has a preceding occupancy snapshot and resource output in the raw archive.
All producers requested `--j 8`, `OMP_NUM_THREADS=8`; BLAS threads were 1.
No CPU-affinity or continuously measured thread-count claim is made on macOS.
Unrelated processes, including the other local task, were left untouched.

One movie at a time was regenerated and deleted after all five arms. Ninety
movies were 4096 × 4096 × 40; ten nonsquare movies were 5760 × 4092 × 40.
At most one task movie was present. The one-second guard's minimum sampled
free space was **11.1010627747 GiB**, above 10 GiB; no guard fired. All movie
and expectation arrays are now deleted. The raw metadata remains locally
under `/tmp/motioncorr-b2-census-mac-20261027/replicate/`.

## Binary identity, manipulation and provenance

OFF/B2 used Mac binary
`e978af21352295bfe2cf756fa2916703d2b7e6c6b34c352d58630e7975155946`,
reviewed git archive source `326f03a073aec0d26c9cd585ce4f701d1c808245`, tree
`44ea2f4c053229297f50ce7feb1066e291674b06`, archive SHA-256
`63038245056d41bdd8bf7f1c6358c9130e52ec1092ab796b24e32a811838065b`.
UP/UPFW/FW and the identity arm used the supplied, unmodified Mac binary
`d57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546`,
git archive source `5bcfa9878157ae7286d8de01e4baa5df9c073f25`, tree
`d1a67904bdd515bebc548f881e8889ac4a682bb2`. Neither binary was rebuilt or
modified for this replicate; each was rehashed before its runs and at completion.

First-movie flags-off identity: **runtime JSON bytes and fields identical
(0 px difference); movie.star bytes identical; MRC core header and payload
identical. Whole product sets are not raw-byte-identical.** The path-bearing
corrected_micrographs STAR agrees after output-root normalization; some logs,
plots, PDF and complete MRC bytes differ. Exact statuses are retained in the
[identity receipt](replicate_results/first-movie-binary-identity.json).
OFF from e978af21 remains the reference throughout.

All 100 B2/OFF, FW/OFF and UPFW/UP pairs have exactly equal global trajectories.
All 500 sampling statuses are VALID. DC counters verify `none` for OFF/B2/FW
and `both` for UP/UPFW. FW and UPFW each have full-width witnesses on all 100
movies (2,500 patch witness lines per arm); UP/UPFW have coupled-peak counters,
the other arms have none. [Manipulation checks](replicate_results/manipulation-check.json).

The unchanged generator SHA-256 is
`a10f694abafc71c146d0e0f2eeb2b1cf2c58131b2dbf6c1b66800405bd126380`;
evaluator SHA-256 is
`b0ab099a256e458b1c8aea6c2ff5d9ceacab10dd81945b025e96e5c8a87b7ff9`.
Python 3.15.1 / NumPy 2.5.4 / SciPy 1.18.1 generated all inputs locally; truth,
expectations and scoring use this local stack. The fixed 129 × 129 ROI,
frame-0 gauge and 0.20/0.40/0.80 Å limits were unchanged. Commands and exact
environment are in [admission](replicate_results/admission.json), the committed
[producer](run_replicate.py), [reporter](summarize_replicate.py) and raw receipts.
No SSH or remote-host access occurred.

## Retention and limits

The original hash STOP, literal-rounding STOP and every original checksum are
preserved. The first scorer's `-I` import failure is retained in
[replicate_failures](replicate_failures/STOP-v1-score-import.json) and the raw
archive. [The invocation repair](SCORER_INVOCATION_FIX.md) changed no evaluator
or producer arguments. Its first OFF native result was hash-checked and reused;
the replacement score is explicitly versioned. There were **no native retries**.

[Verification](replicate_results/verification.json) checks all 500 compact rows
against their raw metrics, 2,004 retained publication hashes and 2,004 evaluator
identity links. This is metadata verification, not an independent native rerun.

[The compact raw metadata archive](replicate_results/raw-metadata.tar.gz)
contains 6,735 indexed original files / 82,442,315 bytes, plus the index;
compressed size 18,820,155 bytes, SHA-256
`4a6047b967f76088445358b69a32ae347fa3892474eab0d55dcc65ab298e30c7`.
[RAW_INDEX.json](replicate_results/RAW_INDEX.json), SHA-256
`6843a01ba2264fbecf233eecc8b7034f201f7d2495641c24c0f03daa7a9742f5`,
covers runtime captures, actual STAR/log files, native/score/generation receipts,
metrics, stdout/resource snapshots, local input receipts and all failure history.
Movie and expectation arrays are excluded. The archive can be inspected without
recreating or rerunning a native producer.

The favourable in-model results do not supersede retained K267 noisy harm,
outmodel/pedestal32 failures or any prior promotion hold. Full CPU/input-format
qualification, native GPU/CUDA parity, real-data accuracy, summed-image scientific
qualification and stable performance remain **UNRUN** by this campaign. Next:
review this replicate evidence and retained harms before proposing any adoption
or further source change.
