# cpu1 regrade v2.2 amendment (23 October 2026; freeze before code/controls)

Base: `5dc412c346edb8fd774795dfb49b727391e8efd9`. Responds only to R2B F1–F4.
The v2 contract, amendment 1, old sources, plans, reports and all native evidence remain byte-exact.
New versioned files implement this iteration; only a dated README addendum may change an existing file.

1. **F1: private Git index.** Every fixed read-only Git command uses an explicit private
   `GIT_INDEX_FILE` copied outside the input root. Disable optional locks, fsmonitor,
   untracked/split-index caches, external diff/textconv, hooks and automatic maintenance.
   Use `/usr/bin/git`, a sanitized environment and bounded commands. Original index
   bytes and stable stat identity are checked before/after; per-call receipts bind the
   private index and original index. Never diagnose the old failing positive on remote
   evidence. Fresh synthetic clean/stale/modified/untracked fixtures test original-index
   immutability and retained HEAD/diff/status/runner/helper/binary/EXPECT checks. The
   R2B unexplained index change and both failed positives stay failed, cause unresolved.
2. **F2: streaming.** Enforce the cumulative byte cap on every read, limit each request
   to the remaining cap plus one byte, and require the opened file's device/inode/size/
   mtime/ctime and pathname identity to remain stable through completion. Fresh tiny
   growth, same-size-write and pathname-replacement controls discriminate the checks.
3. **F3: no ancestor exemption.** Skip only this process. The prospective launch passes
   no input-root path in any SSH/bootstrap/driver ancestor argv, cwd or fd: the driver
   reads its fixed input root from reviewed source, then calls the prechecks in-process.
   Thus no ancestor allowlist is needed. Scan ancestor writers like any other process.
   Path-token boundaries allow a sibling output namespace without hiding descendants
   or `--arg=/input/path` references. Fake-proc fixtures cover own process, exact benign
   SSH/bootstrap/driver ancestry, active parent writer, cwd/fd references and siblings.
   Real Linux process/SSH behavior remains UNRUN; inaccessible process data is reported.
4. **F4: narrow measured package and executable prospective driver.** Package only
   explicit reviewed scripts, amendments, contract, EXPECT, manifest and predictions;
   record exact Git commit/blob IDs, file hashes, package hash and measured bytes.
   No bundle/full clone. A local packer has a 1 MiB content/package cap. The Linux-only
   driver verifies all package pins, its own pin and Python version, obtains a nonblocking
   lifetime CPU13 lease, confirms affinity/one-thread settings, samples CPU13, records
   runtime identities, performs live/files prechecks, grade, live/files postchecks and
   exact identity comparisons. Outputs and private indexes are outside old scratch;
   bound new operation storage to 20 MiB, private index to 1 MiB/tree. No retry, no
   MotionCorr/build/GPU command. Preserve every failure and stop. This task never runs
   the driver remotely; CPU13 stays HELD for fresh independent review and parent scheduling.

Controls use separate fresh fixtures per exact/restored mutant case; no full 65-case
matrix or copied tar corpus. Reuse the retained archive read-only in place, and report
exit/verdict-changing detections separately from diagnostic-only assertions. Retain
65/65 author controls and the contaminated 33-mutant campaign unchanged: R2B's 12
exit-changing plus 7 diagnostic-only detections, 5 equivalent, 4 redundant, 3 originally
untested and 2 misdeclarations are historical, not upgraded by this iteration.

Original native subset FAIL (24 CPU rows PASS; 3 PASS/5 FAIL pairs; N4 PASS), 16 CUDA
rows UNRUN and aggregate INCOMPLETE remain. Full remote grade UNRUN. No production
guard adoption, tolerance/default/policy, science, performance or merge claim. Retained
motion-truth 2 PASS/10 FAIL/4 UNIDENTIFIABLE and #65 UNRUN/INCONCLUSIVE remain unchanged.
Local controls: one numeric thread, fresh UUID namespace, nonblocking lease, 512 MiB
scratch cap, record source/input/runtime hashes, commands, exits and limitations.
