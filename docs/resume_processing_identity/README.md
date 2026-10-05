# Ordinary resume processing identity (Issue142)

## Compatibility change

`--only_do_unfinished` now skips an own-engine movie only when its fixed v2
processing receipt matches the requested processing and its requested numerical
products remain complete. A complete legacy movie without a receipt is refused
with its name, before gain preparation or output mutation. Process it afresh
without the resume flag to migrate; a new output directory preserves the old
results. Same-config incomplete movies, including incomplete legacy movies, are
processed again. A malformed, unsupported or incompatible present receipt is
refused rather than silently trusted.

Fresh external MotionCor2 processing remains supported by the unchanged adapter.
Complete external-engine resume is deliberately refused: v2 does not certify the
adapter's processing identity. Likewise, a complete own-engine movie using a
negative (time-dependent) defect seed is refused; fresh/incomplete attempts remain
supported. If defect correction is disabled, that seed is unused and matching
resume remains allowed. Neither RNG behavior nor scientific pixels are changed.

## Narrow identity and publication contract

The canonical ASCII-hex list block `data_motioncorr_processing` carries version2
and one fixed payload. It records input content/size/dimensions, effective per-row
sampling/voltage/pre-exposure, normalized ascending selected frames, binning,
alignment/grouping/defect/dose options, requested product types and PS geometry, gain/defect parser and admission classes,
EER grouping/upsampling where applicable, original gain and defect content,
own CPU versus own CUDA, executable content and runtime descriptors. Floating
options use finite hexfloat values, preserving precision beyond rounded STAR
columns. Duplicate, missing, extra, unsupported or oversized receipt data fail.

The effective optics and CLI-plus-row pre-exposure resolver is shared with fresh
execution. Input list order, optics group numbers, shards, output directory,
`--do_at_most`, thread/IO budgets, ingest routing, physical GPU UUIDs and diagnostic
output choices are not numerical compatibility keys. Matching no-op/non-prefix
resume, equivalent effective optics, and copies from another shard retain their
per-movie numerical products and model bytes. Joint outputs may be regenerated.

Every fresh pending attempt captures source identities before gain preparation,
then invalidates the old per-movie STAR before any numerical product overwrite.
The completion STAR is written to a temporary file, checked after close and
renamed only after the requested MRC writes close successfully. An earlier failed
product cancels it. Source snapshots are checked again before publication.
Rotated/flipped gain preparation refuses an alias of its original source inode.
The marker records the processing identity and requires structurally complete
numerical MRC products and model. It does **not** cryptographically certify later
changes to corrected pixels or certify the separate EPS/PDF/report endpoint.

A matching receipt also requires saved model dimensions/binning/effective optics,
exposure/dose and start frame to agree at the writer's STAR precision. Accepted MRC
headers must have the requested dimensions, type and exact writer-encoded sampling;
PS dimensions/type are checked. This does not checksum retained corrected pixels,
fit coefficients or every saved metadata/path field. Those artifacts must remain
owned and unmodified; the derived prepared-gain file and later tampering with saved
gain/defect path fields are not independently certified by this v2 receipt.

## File and runtime boundary

SHA-256 reads original inputs with one descriptor and a fixed64KiB buffer. It
checks regular-file type, size, device/inode, mtime and ctime before/after reading,
EOF, OS errors and final pathname identity. Ctime detects ordinary same-size edits
whose mtime was restored. Inputs, gain, defect, executable, installed runtime and
owned outputs must stay immutable as appropriate during processing. These
snapshot checks do not provide an atomic/security guarantee against an external
writer. Hashing incurs additional I/O/CPU work; no performance benefit is claimed
and its cost has not been measured on large datasets.

The runtime records platform/kernel/machine, RFLOAT width and FFTW versions,
plus glibc on GNU systems and CUDA/cuFFT versions when selected. The executable is
hashed; these runtime strings are **not hashes of all loaded dynamic libraries**,
and matching them does not establish arbitrary library-build or GPU-architecture
parity. Linux's `/proc/self/exe` identifies the running executable inode; macOS
uses its loader path and cannot pin a subsequently replaced executable through
that mechanism. This is a conservative configuration-resume contract, separate
from numerical CPU/CUDA and scientific acceptance.

## Retained initial v1 evidence and remaining checks

Source base: main `6c87441d3e44e977994bd26175601092cc344a21` (checked joint STAR
publication). Schema/digest commit `0248c3b`; runner integration source
`f6c4919`; subsequent acceptance-test additions do not change C++. Original GPL-2.0-or-later implementation; imported RELION notices remain.
No CUDA kernels/arithmetic, random generator, tolerance, fixture or reference
was altered. No hardware job, timing, push or merge was performed by this package.

| Check | Actual result |
|---|---|
| Mac Release digest controls |78 explicit checks PASS; retained peer helper hashes |
| Receipt schema/STAR controls |30 explicit checks PASS |
| Actual own-engine CLI, normal and Python `-O` |225 explicit checks PASS per mode |
| Old-source binary controls |8 cases x2 modes: each fails predecessor for its intended false-success/stale-marker reason; candidate passes each |
| Fresh small CPU comparison |3 cases /7 movie products: exact pixels/full1024-byte headers after only printed-date normalization; all old STAR blocks exact after only owned prepared-gain directory normalization; receipt is the only new block |
| Required inventory |33 existing names +3 new =36 collected/required; missing-name fillers for all3 discriminate |
| Full Mac CPU suite |34 PASS /1 known SyntheticRegression FAIL /1 NativeMovieStaging SKIP; gates unchanged |
| Linux wrapped digest read/stat/EOF/mutation errors |Registered in required ProcessingFileDigest on Linux; UNRUN here |
| Native own CUDA receipt/composed multi-GPU resume |UNRUN |
| Large-input hash cost and dynamic-library/GPU parity |UNMEASURED /not certified |

The unchanged Mac failure reproduces maximum pixel difference23.649856567382812,
RMSE0.311928825603332 and shift RMSD0.003305323357857738px. The first full run also
exposed an existing interpolation-test helper that did not skip the legitimate
`# version` comment before a following STAR block. Its comment handling now has a
powered trailing-block control; duplicate-row and all numerical gates remain.
Raw failed/intermediate evidence is retained outside the source tree in the
coordinator's `work/resume-identity-main-20261002-evidence` artifacts. Compact
commands/hashes/results accompany this note. Final Linux/current-main composition,
latest-source independent review, CI and native acceptance are required before
this package is recommended for merge.


## Retained pre-fix composition and bounded review —5 October2026

Additive merge `b96b88d` incorporates main `78473ccd` (#146 compressed-reader
lifetime) while retaining `CompressedMovieSequence`, `JointStarPublication` and
all three receipt tests in the required-name inventory and count-preserving
missing-name controls. CI now requires37 collected tests. Receipt schema/digest
and runner behavior are unchanged by this composition.

Fresh combined Mac Release validation: **35 PASS,1 unchanged SyntheticRegression
FAIL,1 Linux-only NativeMovieStaging SKIP** out of37. The optimized actual resume
suite passes225 explicit checks. A fresh three-case CPU comparison retains exact
pixels/full normalized1024-byte headers for seven movie products and all existing
model blocks; only the receipt block is added. All raw earlier failures and
predecessor controls remain retained. These are correctness controls, with no
isolated performance claim.

A bounded source audit checked effective optics/exposure and processing flags,
content/backend keys, refusal before gain/output mutation, requested-product
completeness, invalidation before overwrite, FIFO writer cancellation/drain,
checked model publication, legitimate non-prefix/shard/group-renumbered/tomography
resume and the named external-engine/time-seeded exclusions. No new blocker was
reproduced. `own-cuda` identifies the selected existing CUDA pipeline, including
its existing permitted stage fallbacks; it is not an all-stages-on-GPU witness.

Linux wrapped digest boundaries, combined CUDA compilation and native CUDA
receipt controls are still **UNRUN** here. Current-source independent review/CI
and required native acceptance remain merge gates. The compact replay manifest
is `evidence/review-20261005.json`; detailed replay logs remain in the
coordinator's isolated evidence directory.


## Parser-identity repair (v2) —5 October2026

Independent review reproduced a v1 false-success: identical defect bytes copied
from `.txt` to `.map`, and identical MRC gain bytes copied to `.tiff` or `.dm4`,
were accepted on resume even though each fresh request failed its new parser or
admission path. These failures and the original source `caf8cd0` are retained.

Source `ba60ce7` adds fixed `defect_parser` and `gain_parser` fields and explicitly
advances the payload/schema to **v2**. Complete experimental v1 receipts now refuse
named; use a fresh non-resume run to migrate. No v1 receipt has been merged into
production. Parser classes follow actual dispatch: rectangle TXT versus image
maps; generic gain read/preparation versus direct EER gain interpretation. EER's
`.gain` multiplicative/Y-flip behavior and direct first-image MRC dispatch are
included, with rotation/flipping bound separately as before. Other format names
remain conservative rather than assuming arbitrary aliases are equivalent.

Content-equivalent one-file relocation/symlinks within the same parser class stay
compatible. Generic MRC/map and non-EER TIFF/tif/gain aliases are canonicalized;
direct EER MRC/map classes are kept distinct because that reader requests 2D/first
image dispatch. A single-file digest cannot certify IMAGIC companion files or
Image selectors/format specifiers that open another path: v2 own-engine receipt
processing refuses these references named. Extensionless image references are
also refused because their reader can append `.spi`. This is a deliberate narrow
capability boundary, not broader reader-format support or a change to arithmetic.

The current actual CLI suite passes **272 explicit checks in each normal/-O mode**,
including same-parser relocation and symlink positives, TIFF/gain aliases,
identical-content parser-switch refusals and named paired/specifier refusals.
Three powered controls each fail the privately rebuilt exact caf predecessor and
pass v2 in both modes; its rebuilt binary has its own recorded hash, distinct from
the original peer binary. Initial failed v2 test attempts are also retained.
The final combined Mac37 suite again gives35 PASS /1 inherited SyntheticRegression
FAIL /1 Linux-only staging SKIP, with the same unchanged diagnostics. Fresh
three-case/seven-product CPU parity is exact at the stated full-header/old-STAR
scope. Linux/CUDA/native gates are still UNRUN; actual EER parser semantics have
source review only. Details: `evidence/parser-v2-review.json`.
the earlier v1 evidence above does not approve this repaired source.


## Additive saved-model bounds composition —5 October2026

Source `c78db669` additively merges main `282eb7de` (PR148) with the receipt branch,
preserving both histories. The union collects and requires **38 named tests**.
Eight focused CTests pass; actual receipt CLI272 checks and saved-model parser/
completion controls pass in both normal and Python `-O` modes. The imported saved
model bounds/EER interpretation are identical to reviewed main; the only model
conflict resolution keeps the parsed model RAII-owned until receipt parsing also
succeeds. Receipt/CUDA/numerical source remains unchanged from the v2 predecessor.
This does not establish EER decoding or native CUDA receipt execution. Full Mac37
results above remain predecessor evidence; no new full-suite scientific PASS is
claimed by this bounded38-test composition. Independent exact-source delta review
confirms source/scope/license. Current-head CI/native acceptance remain separate.


## Bounded native receipt acceptance —5 October2026

Pinned published source `cd69c004` (production merge `c78db669`), CUDA12.8.61/sm80,
no nvCOMP, VM GPU1 physicalUUID `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d`.
Actual all-descendant logical CPUs104–111 with membind1, build4 under the shared
build lock, j4/io2. Binary SHA256
`e0a5e24770d58962ed0b312ecb61a86be431d76f3457905d672f6808721533df`.

- Native configuration collects46 tests and retains all38 required names;
  **eight focused CTests execute and PASS**. This is not a46-test full native run.
- Linux digest checks91 PASS with the mandatory actual wrapped OS fault marker:
  read/fstat/final stat errors, shortEOF, descriptor/path changes, EINTR recovery.
- Both normal and Python `-O` native receipt campaigns PASS:38 binary invocations
  per mode,19 with actual successful native cuFFT (410 events),684 explicit harness
  checks. PhysicalUUID and original/observed PID-birth/affinity are recorded.
- Matching no-op and same-parser relocation/symlink aliases retain movie bytes and
  mtimes with zero numericalCUDA. Configuration/backend/content/parser mismatches
  refuse named before output mutation. Fifteen expected failing invocations per
  mode are retained, including fresh-invalid parser and late-write controls.
- Missing odd-product repair reproduces allfive requested MRCs exactly including
  the full header with only its one printed timestamp normalized. Both sync/async
  late-product and late-model failures invalidate the old marker, withhold joint
  success, then repair exact payloads. Bounded non-prefix processing leaves the
  completed movie unchanged and produces all remaining movie products/models.
- Reviewed ownership cleanup controls PASS normal/-O, including actual observed
  reparented TERM-ignoring children and numericPID/PGID-only negative controls.
  All observed owned children are gone; strict assignedGPU occupancy release
  passes, final exit0, released2026-10-05T14:51:15+00:00.

Limits remain: these small synthetic configurations are not complete tutorial24,
native tomography/multioptics/PR147 composition or EER decoding acceptance. A
selected own-CUDA receipt plus successful cuFFT witness does not certify every
stage on GPU. No new performance, memory, scientific accuracy or PDF-completion
claim. Historical Mac synthetic failures and old-source/mutant failures remain
unchanged. Compact receipts: `evidence/native-20261005/`; full raw inputs/products/
stdout/stderr/witness traces and the exact binary are retained in the coordinator's
`work/resume-native-acceptance-20261005/evidence-payload-3042180` and VM campaign.

## Review delta: saved EER settings and per-movie source failures (5 October)

Source `060c5dce` addresses the two new review findings without changing receipt
schema, numerical kernels or RNG. EER inputs cross-check saved grouping/upsampling
against their receipt. An absent saved upsampling label means the existing supported
`-1` half-resolution default: requested `-1` matches, requested `1` refuses, and
requested `-1` with an explicit different supported value refuses. Grouping remains
required by the saved-model parser. Non-EER inputs ignore EER-only metadata.

Only source-identity checks immediately before model publication convert their
`std::runtime_error` into a named `RelionError`. Synchronous and background output
therefore share the per-movie failure contract. Physical changes to movie A retain
healthy B's exact CPU pixels; changes to the shared gain/defect/executable snapshot
correctly refuse both movies. Old A completion is removed and joint publication
is withheld in all eight source/writer arms. No broad GPU-error catch was added.

[Retained evidence](evidence/review-delta-20261005/summary.json):

- Required/collected union **39**; full Mac run **37 PASS / inherited synthetic
  regression FAIL / Linux-only staging SKIP**. Gates and inherited failure remain.
- Actual receipt CLI **294 checks** in each normal/Python `-O` mode; all eight
  physical source/writer arms pass in each mode.
- **32 predecessor/fixed control arms** are discriminating: four EER saved-field
  negatives and four source mutations in both Python modes. The retained private
  Mac predecessor was built from `c78db669`; its production source tree is identical
  to published `ca53a5b2`, and its actual binary hash is recorded separately.
- Header-only synthetic EER fixture drives actual resume preflight with sparse MRC
  extent and a constructed compatible receipt. It does **not** decode EER pixels,
  establish EER science, or assert full experimental-data correctness.
- Initial missing-interposition/path and mistaken global-healthy control failures
  remain in private raw evidence alongside the corrected controls.

The preceding native campaign remains evidence for its pinned predecessor source.
**The native delta for this repair is UNRUN**, and current-source CI/review are
separate gates. Structural header/type/geometry/extent validation is not a checksum
of later-edited output pixels; no output-hash feature was added in this repair.
