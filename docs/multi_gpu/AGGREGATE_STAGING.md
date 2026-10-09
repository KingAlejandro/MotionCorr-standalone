# Aggregate staging: hardlinks, one hash pass, per-worker overlap

`merge_workers.py` used to copy every per-movie product into `merged/` and hash
the staged tree twice, before and after the `--aggregate_only` binary. At 96
movies that was about 31 s of serial time, of which the binary was about 2.5 s
(`scaling/README.md`, "Where the serial aggregate time goes"). The published
tree is unchanged; only how it is staged and checked has changed.

## What happens now

1. **At worker exit** (`run_multi_gpu.py`). Each worker's reap thread, as soon
   as its worker exits 0, digests every file the worker left
   (`output_digests.digest_tree`), pinned to that worker's CPU mask, while the
   other workers are still running. The record is stored in `status.json` as
   `workers[k].exit_digest`: for each file its sha256 and its stat key
   `[dev, ino, size, mtime_ns, ctime_ns]`.
2. **Staging** (`merge_workers.py --stage {auto,link,copy}`, default `auto`).
   Each product is hardlinked into `merged/`, in a thread pool. `auto` copies
   when the filesystem refuses the link (`EXDEV`, `EPERM`, `EMLINK`,
   `ENOTSUP`); `link` fails instead (rc 2); `copy` always copies. `--link` is
   kept as an alias for `--stage link`, and is no longer refused next to
   `--aggregate-with`.
3. **Digest reuse.** If a product's current stat key equals the one recorded
   at exit, the recorded sha256 is used and a linked product is not read
   again. Otherwise its bytes are hashed (while copying, when copying) and
   compared with the record; a difference fails the merge with "changed after
   the worker exited". Without a record (a hand-written or older status), the
   merge hashes each product once itself.
4. **Presence.** Files present now but not at exit, or the reverse, fail the
   merge, as does any file the launcher could not digest.
5. **After the aggregate binary.** Each staged product's stat key must be
   unchanged. A mismatch is hashed only to say whether the bytes or just the
   metadata changed; either way it fails ("aggregate step rewrote N staged
   worker product(s)").

The report gains `staging` (counts by stage, digest source and fallback errno),
`staged_sha256` (the digest of each product as staged) and
`timing_seconds` (staging, ctime barrier, aggregate binary, after-check).

## Why a stat key can stand in for a second hash

- Any write changes mtime and ctime, and a replacement changes the inode.
- ctime cannot be set from userspace, so restoring mtime with `utimensat`
  after a rewrite does not restore the key.
- Timestamps come from a coarse clock, so a write in the same tick as the last
  recorded change could leave ctime unchanged. Before any recorded key is
  relied on, `ctime_barrier` writes a probe on the same filesystem until its
  ctime is later than every recorded ctime. After that, any write to a
  recorded file gets a later ctime. The barrier fails closed if the files span
  another filesystem or the clock does not advance within 5 s; in the merge
  the aggregate binary is then not run.
- Every hash is taken between an fstat before and after the read, both equal
  to the listed key, so a digest never describes a file that moved under it.

## What the second check protects against with hardlinks

A linked product shares its inode with the worker's file. If the aggregate
binary rewrites it, the worker's copy changes too, so the worker tree can no
longer serve as the reference. The after-check still detects the rewrite
through the stat key, and `staged_sha256` in the report records what was
staged. The failure message says how many of the rewritten products were
hardlinks.

## Limitations

- A writer that modifies a file between the merge's stat and its link, and
  then restores mtime with `utimensat`, is detected only by the link-time
  comparison of `[dev, ino, size, mtime]`; ctime changes with the link itself
  and cannot be used there.
- Linking changes a file's ctime, so merging the same worker tree a second
  time takes the re-hash path ("verified"), not the reuse path. The launcher
  never reuses a worker directory.
- The last worker's digest is still on the critical path: `worker_phase_wall_s`
  now includes it.

## Tests

`tests/test_multi_gpu_scheduling.py`: `case_link_staging_with_aggregate`,
`case_link_refusal_falls_back_to_copy`, `case_launcher_exit_digests_are_reused`,
`case_change_after_worker_exit_detected`, `case_exit_digest_records_validated`,
`case_timestamp_barrier_failure_fails_closed`, `case_output_digest_primitives`,
`case_aggregate_same_byte_rewrite_detected`, and an extended
`case_aggregate_may_not_rewrite_staged_products`. Each was shown to fail
against a targeted mutation of the code it covers; the mutation list and
results are in `scaling/staging_negative_controls.txt`.
