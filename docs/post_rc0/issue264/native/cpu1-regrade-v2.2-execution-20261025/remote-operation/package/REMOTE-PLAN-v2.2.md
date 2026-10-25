# Prospective cpu1 regrade v2.2 — HELD, no execution authorized

Supersedes only the prospective v2.1 procedure. The full remote grade remains UNRUN.
R2B's exact-source failures remain retained; the original input must never be used to
reproduce or diagnose the original-index change. Fresh independent exact-head review,
then parent resource reconciliation/authorization are prerequisites. This document
and `remote_run_v2_2.py` describe one operation, not an authorization or Linux PASS.

## Package (parent, locally after review)

From the exact reviewed full commit SHA, invoke:

```sh
/Users/alex.konstantinov/.local/bin/python3 -I -B package_v2_2.py --revision REVIEWED_FULL_SHA --out NEW_LOCAL_PACKAGE_DIRECTORY
```

The packer reads nine explicit Git blobs from that commit. It emits `package.tar` and
`PACKAGE-RECEIPT.json`, containing source commit, Git blob IDs, file sha256/size, content
bytes, package bytes/hash, and `PACKAGE.json` hash. Both content and archive are capped
at 1 MiB. It includes only grader, driver, contract, two amendments, EXPECT, manifest,
this plan and predictions. No clone/bundle/native archive/corpus is transferred.
The packer itself is versioned and its hash is in the receipt. Parent retains the receipt.

## One future parent-owned launch

1. Refresh occupancy immediately before scheduling CPU13. It remains HELD until parent
   explicitly releases the DC reservation and reviews current #198 allocation. No GPU,
   build, MotionCorr or timing work. Use the documented gateway, no direct SSH retry.
2. Create a unique new sibling namespace
   `N=/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1-regrade-v2-2-SHA12-UUID`.
   The immutable input `S` is the same prefix ending at `cpu1`, without the suffix.
   Require N absent, sufficient space, and no unrelated contents. Transfer the <=1 MiB
   tar once to N. Verify its exact package hash against the local receipt *before*
   extracting its nine regular basename members plus PACKAGE.json into N/package.
   Package member set, hash, size and blob IDs are checked by the driver. Do not deploy
   through a full checkout. Record the exact transfer/extraction argv and exit codes.
3. Launch from N (outside S), with no argument containing S as a complete pathname.
   All ancestors must use only N paths and the exact command shape below. Use shell
   `exec` for the final bootstrap. No `--scratch-root S` in any SSH/bootstrap argv;
   the reviewed driver holds S as a source constant and invokes prechecks in-process.
   This removes all ancestor exemptions. A genuine ancestor writer referring to S
   is a refusal. Sibling N references are not references to S.
4. Parent's launch wrapper records UTC start/end, PID, argv, stdout/stderr and exit in
   new N files, with an external 180-second deadline (`/usr/bin/timeout --signal=TERM
   --kill-after=5s 180s`). An interrupted/missing driver receipt is FAIL/INCONCLUSIVE,
   never PASS. Reconcile process exit before considering any distinct later iteration.
   Never rerun this operation or repair its outputs in place.

The inner command (substitute only receipt pins and N paths) is:

```sh
exec /usr/bin/timeout --signal=TERM --kill-after=5s 180s /usr/bin/taskset -c 13 /usr/bin/env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -I -B N/package/remote_run_v2_2.py --source-commit REVIEWED_FULL_SHA --package-manifest-sha256 RECEIPT_MANIFEST_SHA256 --out N/run
```

Use system Python >=3.8, stdlib only. The driver refuses macOS before any operation.
It verifies its own and every package member's hashes/blob identity, Python version,
all five one-thread settings and exact CPU13 affinity; acquires the nonblocking
lifetime flock `/tmp/motioncorr-guard264-cpu13-regrade.lock`; records `taskset -pc`,
Python/Git versions and executable hashes, uid/PID/UTC; and samples `/proc/stat` for
3 seconds (CPU13 <=50% busy). Contention/refusal stops without waiting/retry.
A 1 MiB per-file write limit and fixed output set keep new data below 20 MiB;
initial namespace <=2 MiB, private index <=1 MiB/tree, only one temporary copy at a time.
The packer receipt provides the measured package cost; no unmeasured <20 MB clone claim.

## Driver sequence and implemented checks

`live-pre` → `files-pre` → `grade` → `live-post` → `files-post` → compare → package reverify.
Each step records arguments, exit, start/end and stdout/stderr. Nonzero stops and
retains the failed receipt; subsequent steps are UNRUN. `OPERATION.json` is atomic.

- Live: five exact HEAD/diff/status/runner/helper descriptors vs EXPECT; three live
  binaries vs receipt vs EXPECT, distinct; processes referring to S rejected. `/proc`
  permission failures are counted and retained as a limitation (not universal writer exclusion).
- Every Git command has a private GIT_INDEX_FILE outside S, fixed sanitized options,
  no hooks/fsmonitor/external diff/textconv/automatic maintenance, optional locks off,
  15-second child deadline. Original index hash/device/inode/size/mtime/ctime are
  checked around every call and overall. These commands never select original index
  for writing. Only ordinary stable-input checks are claimed, not adversarial race proof.
- Files: 101 pinned hashes; all 16 MRCs exact 768×512×1, mode2, nsymbt0, MAP word,
  1,573,888 bytes each. Grade snapshots/rechecks 117 inputs, binds precheck/manifest,
  retains row parity/N4/contradiction gates, and publishes REGRADE_V2_2.json atomically.
- Compare: live source/binary/original-index identities unchanged (private paths ignored);
  files reports byte-semantically equal. No input-root outputs; every output is new.
- Streaming binary hashes enforce cumulative caps and stable open/path identity.

Exit 0 requires all these checks plus FULL PASS under the unchanged row, exact-decimal
pair, payload-relation and N4 contract. A successful future result could support only:
“v2.2 CPU subset regrade of TEST-ONLY overlay output passed, with exact parsed printed
global rows and validated payload relations.” It cannot replace the original FAIL,
prove full-precision recovery, production guard safety or adoption. Original 24 CPU
rows PASS / 3 PASS 5 FAIL pairs / N4 PASS, 16 CUDA UNRUN, aggregate INCOMPLETE stay.
All Linux Git/process/SSH/affinity/lease behavior and genuine native MRC regrading
remain UNRUN in the local author task. Maintainer parity/nonfinite-model issues persist.
