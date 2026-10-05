# Ordinary resume processing identity (Issue142)

## Compatibility change

`--only_do_unfinished` now skips an own-engine movie only when its fixed v1
processing receipt matches the requested processing and its requested numerical
products remain complete. A complete legacy movie without a receipt is refused
with its name, before gain preparation or output mutation. Process it afresh
without the resume flag to migrate; a new output directory preserves the old
results. Same-config incomplete movies, including incomplete legacy movies, are
processed again. A malformed, unsupported or incompatible present receipt is
refused rather than silently trusted.

Fresh external MotionCor2 processing remains supported by the unchanged adapter.
Complete external-engine resume is deliberately refused: v1 does not certify the
adapter's processing identity. Likewise, a complete own-engine movie using a
negative (time-dependent) defect seed is refused; fresh/incomplete attempts remain
supported. If defect correction is disabled, that seed is unused and matching
resume remains allowed. Neither RNG behavior nor scientific pixels are changed.

## Narrow identity and publication contract

The canonical ASCII-hex list block `data_motioncorr_processing` carries version1
and one fixed payload. It records input content/size/dimensions, effective per-row
sampling/voltage/pre-exposure, normalized ascending selected frames, binning,
alignment/grouping/defect/dose options, requested product types and PS geometry,
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
The marker certifies the requested numerical MRC products and model; it does **not**
certify the separate EPS/PDF/report endpoint.

A matching receipt also requires saved model dimensions/binning/effective optics,
exposure/dose and start frame to agree at the writer's STAR precision. Accepted MRC
headers must have the requested dimensions, type and exact writer-encoded sampling;
PS dimensions/type are checked. This does not checksum retained corrected pixels,
fit coefficients or every saved metadata/path field. Those artifacts must remain
owned and unmodified; the derived prepared-gain file and later tampering with saved
gain/defect path fields are not independently certified by this v1 receipt.

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

## Verified scope and remaining checks

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


## Current-main composition and bounded review —5 October2026

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
