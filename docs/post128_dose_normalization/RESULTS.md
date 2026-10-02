# Exact dose normalization: retained result

## Verdict

GO to final review as a long-movie integration candidate; no useful tutorial whole-process
speedup established. Draft PR131, separate from workspace-only PR130. No merge.

Reuse was proposed in #77 on29September, not implemented/measured in that record.
Earlier reciprocal/rsqrt/algebraic experiments were not exact and are excluded.
This implementation retains original expf, ascending float sum, sqrtf, numerator,
division and DC. One per-reconstruction denominator plane, no stale cache.

## Source and venue

- Baseline main: c499b1d3bf1cceec5c3b194f356844d6f493e7f2.
- Frozen candidate production/test/CMake:2fe51dd; source implementation eb75bf5.
  Subsequent commits change measurement tools/fixtures/documentation only.
- Fresh matched Release binaries, CUDA12.8/sm80/nvCOMP5.3 on SCARF gn0002,
  A100-SXM4-40GB UUID GPU-ba532823-8144-c15e-618d-060ebb72bf53.
- Payload masks0–7, j6/io6/OMP6; build<=8. Dedicated job requested1GPU/16CPUs;
  exclusive actual allocation64CPUs/4GPUs, only GPU0 used. Payload PID/start/exe,
  affinity, topology/NUMA maps, physical UUID, binary/source/input hashes and exact
  arguments retained per arm. No concurrent compute during controlled pairs.
- Job3517816 retained as FAILED1:0; job3517973 COMPLETED0:0, released
  2026-10-01T11:16:23+01:00 with empty compute list. Separate phase observations,
  no pooling with PR130's previous node/device/timing series.

## Full-application observations

Alternating AB/BA, fresh output directories. Wrapper-inclusive complete process,
including output/PDF, not stage subtraction. Hashed inputs shared by both arms;
matching warmed-input/cache regime, not a guaranteed cold filesystem experiment.
Nominal polling intervals20ms/tutorial and1ms/one movie; scheduling delay is not a hard bound. Three screening pairs; only80/160
screens winning all3 pairs advanced to five-pair confirmation. No significance
or population-wide long-acquisition claim from this sample.

| Workload/phase | Main median s | Reuse median s | Difference of arm medians | Faster pairs | Exact non-PDF products |
|---|---:|---:|---:|---:|---|
| tutorial-screen | 12.821181 | 12.808291 | 0.101% | 2/3 | PASS |
| F8-screen-v2 | 2.679919 | 2.590224 | 3.347% | 2/3 | PASS |
| F24-screen-v2 | 2.899748 | 2.808841 | 3.135% | 2/3 | PASS |
| F80-screen-v2 | 3.539068 | 3.370013 | 4.777% | 3/3 | PASS |
| F160-screen-v2 | 4.467294 | 4.181763 | 6.392% | 3/3 | PASS |
| F80-confirmation-v2 | 3.496401 | 3.388722 | 3.080% | 5/5 | PASS |
| F160-confirmation-v2 | 4.550652 | 4.255333 | 6.490% | 5/5 | PASS |

Synthetic one-movie fixtures use full3710x3838 pixels and the original gain:
8/24 use the first pages,80/160 cycle all24 decoded tutorial pages. Deflate1,
predictor1, one full row per strip, every decoded pixel/page re-read and compared.
These are explicitly synthetic, not new acquisitions or scientific ground truth.
Initial generator wrongly used128rows/strip; unchanged baseline refused pinned
nvCOMP and the campaign stopped. Original failure and fixture remain unchanged;
corrected fixture-v2 paths were separately generated and graded. No failed pair
was counted as a completed timing observation.

### All confirmation observations (seconds)

- F80-confirmation-v2: main [3.543980600021314, 3.4964014969882555, 3.497914830018999, 3.4365471540077124, 3.436559842986753]; reuse [3.4047665700200014, 3.4906805859936867, 3.3444467689841986, 3.3887222449993715, 3.343497469002614]. Paired savings [0.1392140300013125, 0.00572091099456884, 0.15346806103480048, 0.04782490900834091, 0.09306237398413941].

- F160-confirmation-v2: main [4.538989970984403, 4.52350664100959, 4.596681288006948, 4.597196111979429, 4.550652165024076]; reuse [4.15379031500197, 4.255333350010915, 4.263946289982414, 4.34485145600047, 4.252912101976108]. Paired savings [0.3851996559824329, 0.26817329099867493, 0.33273499802453443, 0.25234465597895905, 0.29774006304796785].

### Dose stage (screen only; not application verdict)

Reported CUDA dose kernel duration includes the new precompute. The original
reconstruction total also includes precompute; complete wall includes allocation.

- tutorial-screen: summed dose kernel median 223.92→76.30ms.

- F80-screen-v2: summed dose kernel median 83.97→10.47ms.

- F160-screen-v2: summed dose kernel median 319.83→20.78ms.

## Correctness and failure evidence

- Fresh baseline native+nvCOMP39/39; candidate native+nvCOMP40/40.
- Candidate CPU32/32, native CUDA without nvCOMP39/39.
- New native test:1,365 byte-exact weighted Fourier frames,50 byte-exact complete
  null/polynomial reconstructions, original frozen kernel/manual frame-loop oracle;
  1/8/24/80/160frames, odd/non-square geometry, changed/zero/irregular doses/apix,
  nonzero real/imaginary DC and signed-zero controls. Independent review caught
  initially unpowered zero-only DC input; corrected before source freeze/native run.
- Actual fifth allocation, precompute launch/completion, plane cleanup and late
  fatal cleanup controls pass; first failure and consumed late fatal retained,
  no frame-copy/inverse-FFT consumption or host success publication after failure.
  All owned allocations/events/plans released. These inject returned error codes;
  physically poisoned hardware context and other toolkits/devices remain unrun.
- Three actual compiled production mutants (omitted dose, wrong dose, wrong DC)
  each pass positive control then fail the exact old-kernel oracle as intended.
- Ten application option rows pass: global/patch variants, selected frames,
  grouping, no gain, even/odd, save-noDW, power spectrum and no-dose. Actual native
  stage witnesses and ingest backend identities required, no warning/fallback
  accepted in timing pairs. Native resident-to-host retry/reset path separately
  exercised by the option controls.
- Every completed pair grades full MRC normalized1024-byte/extended headers and
  pixels, STAR metadata/trajectories/movie identities, complete inventory and
  non-PDF artifacts. PDFs inventory only; no new rendered-PDF/scientific-truth
  acceptance claim. Historical noisy scientific-truth failures are not erased.

## Memory/logging/limitations

Extra plane4*ny*(nx/2+1)bytes =28,493,312bytes (27.173MiB) on this geometry.
Recorded allocation estimate is not whole-process VRAM/RSS peak. Per-movie
Peak VRAM auxiliary row changes by exactly one plane; stage/numeric contract
checks this within printed2-decimal rounding and requires all other stage deltas
zero before that line is excluded from auxiliary comparison. Raw unexcluded
auxiliary FAIL JSON/logs are retained alongside exact accepted verdicts. No
header/pixel/STAR tolerance or scientific gate relaxed.

RSS and device memory are retained sampled observations; GPU memory sample is
not an allocator peak, single payload process RSS is not arbitrary process-tree
unique resident pages. Added plane increases memory pressure; no resource-memory
reduction claim. All50 arm executions across completed screens/confirmations
are retained (25 matched pairs), plus ten option rows and the failed firstF8
baseline. No whole-application claim based on asymptotic/kernel speedup alone.

## Retention

Remote full input/output trees, source/builds, raw and accepted comparators,
profiles, witnesses, binary/source/input hashes, resource/process samples and
failed/successful job records:
`/work4/scd/scarf1415/motioncorr/post128-dose-normalization-20261001`.
Final metadata/log archive SHA256:
`17a4c56b1d13f0d2f81fe18fe36c8a82e7f16d8d5be98e5056857db524d1b6e4`.
Earlier pre-review archive is also retained locally:
`c949dd0632467642e1909ed41e90525473307d4b19af210e21601ac2b50ffd78`.
The archive contains metadata/logs, not all large pixel payloads; full trees are
retained remotely. Source/test and tools independently reviewed; PR Codex review
and final publication-head CI tracked on PR131, not inferred from old evidence.

## Codex measurement-tool follow-up

Review of f222fc5 found two actionable defects, not production arithmetic defects:
summary accepted a completed-pair prefix without requested count; cleanup treated
zombies as live survivors. Runner now persists expected count at entry and writes
hash-bound completion only after all pairs/verdicts/binary/input checks. Summary
requires that marker, exact inventory hashes and unique complete pair/arm coverage.
Cleanup excludes stateZ, retaining live/reparented TERM-ignoring child handling.
Actual helper/summary CLI controls passed in CPU-only SCARF3518019 (COMPLETED0:0),
including old-zombie mutation and six partial/missing/duplicate/tampered/failing
summary negatives. No timing or GPU compute in that follow-up job.

Prior completed measurements were explicitly retrospectively sealed, not re-run:
retained completed-job records, original PAIRS_COMPLETE logs, expected3/5 counts,
unique arm inventory,25 exact verdicts and pinned binary hashes checked; original
provenance/summary files preserved. completion-reconciliation.json records the
attestation and hashes. Re-summarization through the corrected CLI preserves all
observations and medians. This is not a claim that old runs used the new marker
mechanism. Production/tests/CMake remain identical to native-tested2fe51dd.
