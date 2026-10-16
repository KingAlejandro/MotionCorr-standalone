# nvTIFF vs compact LibTIFF timing — 16 October 2026

Question (#141): does nvTIFF 0.8.0.82 save at least 0.15 s/movie over the frozen
`6b6adf44` compact LibTIFF reader, beyond same-arm null variability?
Scope: standalone warm-cache real U8 LZW native-device ingest, five movies, no
application integration, no U16, no safety/licensing result. Sign: positive =
nvTIFF saves time. Analysis rules: `ANALYSIS_PLAN.md` (written before reading results).

## Verdict

| Venue | Verdict | Basis |
|---|---|---|
| SCARF gn0002, A100 40GB, job 3633126 | **GO** (standalone endpoint only) | 250/250 rows PASS, 5/5 files complete, every file and the overall envelope clear 0.15 s on both clocks |
| VM 4GPUs, A100 80GB | **UNRESOLVED** | campaign aborted on the resource gate (0.25 unowned-core limit) in both attempts; 2/5 files complete |

Venues are not pooled. GO does not authorise integration, merge or default changes.

## SCARF (measured)

Saving, seconds/movie, median of 12 paired trials; null = max |adjacent same-arm
difference| over 12 null pairs per file. Descriptive bootstrap interval, not a
confidence interval. Required saving = max(0.15, null).

| File | Ingest-ready saving [interval] | Null | Checked-exit saving [interval] | Null |
|---|---|---|---|---|
| EMPIAR-10361-1 | 0.855 [0.845, 0.862] | 0.032 | 0.844 [0.832, 0.884] | 0.081 |
| EMPIAR-10361-2 | 0.860 [0.849, 0.863] | 0.019 | 0.863 [0.843, 0.864] | 0.080 |
| EMPIAR-10441-1 | 1.713 [1.701, 1.730] | 0.052 | 1.710 [1.698, 1.738] | 0.041 |
| EMPIAR-10641-1 | 0.511 [0.509, 0.515] | 0.026 | 0.512 [0.502, 0.533] | 0.040 |
| EMPIAR-10641-2 | 0.514 [0.510, 0.519] | 0.012 | 0.522 [0.512, 0.543] | 0.020 |
| **Equal-file mean** | **0.891 [0.883, 0.898]** | ≤0.052 | **0.890 [0.878, 0.912]** | ≤0.081 |

Equal-file mean medians, ingest-ready: compact 1.208 s, nvTIFF 0.317 s;
checked-exit: compact 1.763 s, nvTIFF 0.866 s.

Limitations:
- The saving (0.5–1.7 s/movie) is larger than the previously calculated ceilings
  (host LZW decode ~0.31 s, device-ingest saving ~0.4 s). The measured quantity is
  the whole standalone ingest path, not LZW decode alone; the components that make
  up the difference were not isolated here.
- The checked-exit nvTIFF arm still pays ~0.65 s fixed process exit/startup cost.
- One venue, one A100, one allocation, THP `always`; shared PanFS source storage.
- Null bands are observed maxima over six pairs per arm, not confidence bounds.

## VM (measured fragments, not a result)

Four attempts. Runs 1–2 failed before any movie ran (wrong kit-manifest schema;
wrong corpus path). Run 3 stopped at `empiar-10361-1-pair-08-B`
(0.99 unowned cores). Run 4 stopped at `empiar-10441-1-pair-09-A` (0.519 unowned
cores, 5.31 s payload) after 143 rows. The fail-closed controller aborts the
whole campaign on one bad row; the gate, divisor and 0.25 limit were not changed
and no rows were filtered. Unowned CPU was not attributed and kernel/IRQ is not
subtracted. Physical host exclusivity under the VM is unverified.

Two files finished all null and A/B pairs in run 4 (descriptive only, same sign
as SCARF): 10361-1 ingest 0.788, checked-exit 0.890; 10361-2 ingest 0.857,
checked-exit 0.956 s/movie. 10441-1, 10641-1 and 10641-2 have no complete series.

## Provenance

- Source revision: probe at `d61308a2fc8259b3fb8b7bc388237fda14ed4665` (this branch's parent);
  arm A = frozen `6b6adf4420ec09403a7b655dce6cdc2d8ee004a7`; nvTIFF 0.8.0.82 private SDK, not vendored.
- Controller release receipt: `timing-release.json` sha256 `0a5b6f0557fd783b566b4da05520e0e219360f82006931bb1a3696eeef1a4f5d`.
- SCARF: job 3633126, `gn0002`, 2026-10-16T18:39:49Z–18:56:07Z, GPU
  `GPU-ba532823-8144-c15e-618d-060ebb72bf53`, CPUs 0-3,32-35, driver 580.178.04;
  timing exit 0, same-allocation native acceptance exit 0, compute-apps empty on the owned device.
  Run root `/work4/scd/scarf1415/motioncorr/validation-20261011-nvtiff/timing-20261016-job-3633126`.
  Reduced by `reproduce/collect_result.py` → `scarf_result.json`
  (sha256 `1f23d11e40bb728a28f76b7152263ab19c8396ed174dd38b7cf5d5a5f78b5171`).
  Receipt archive `evidence-20261016-scarf.tar.gz` (in `.../validation-20261011-nvtiff/`)
  sha256 `b936eb040832eb4bd5b3f094b6170383c90637c350ca67574ce50bbd5564b318`,
  manifest sha256 `52cf55e6a80ebd10a4e1b199ca105bdf6a403b149c32fbe53a10f6d9185cfc4a`.
  `pairs/progress.json` still reads `PREPARING` (not rewritten at completion);
  the reducer uses `pairs/summary.json` (COMPLETE).
- VM: `vm_result.json`; run root `/home/alex/motioncorr-validation-20261011-vm/timing-20261016/run-4`;
  archive `evidence-20261016-vm.tar.gz` sha256 `db55e9ce65c11890db292b8cc21e0ae9d6ff290e265dd7f2f6004e2e2dc3b74e`.
- Launchers, controller delta and reducer: `reproduce/`. The earlier 13 October SCARF job 3583547
  and 13 October VM failure are retained separately and were not overwritten.

## Next action

Application-level pilot is a separate decision; this result covers only the standalone
endpoint. A VM re-run needs a quieter box or an attributed source for the unowned CPU.
