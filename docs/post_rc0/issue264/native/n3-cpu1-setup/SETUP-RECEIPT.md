# #264 cpu1 setup receipt (22 October 2026): setup only, no build or native run

Parent authorised setup only, after review R4. Nothing was built, configured or run in this
scratch, and no stage of `chain_cpu1.sh` was started. No GPU query was made. The frozen
plan (`../n3-cpu1/`, commit `3751bd05`) is unchanged; its `check_sources.py` wording is
qualified by `RESPONSE-R4.md`.

## Bundle and dry run (Mac, outside the assigned scratch)

- `git bundle create /tmp/mc264-cpu1-setup-20261022/g264-3751bd05.bundle HEAD` at
  `3751bd05a95412dff468557141f2e7e01ad21831`. That is the same form R4 used, chosen because of the
  abbreviation dependence in F3. Single head `3751bd05… HEAD`; `git bundle verify` OK.
- Bundle sha256: `be26918ee3d1149834b72593acd42f3b617762109f5b27caf32c6d0269d41d57`.
- Dry run (`dryrun-SOURCES.txt`): five clones from the bundle, the overlay applied with macOS
  BSD `patch`, the mutant replacement applied. Every HEAD, diff_sha256, runner and helper value
  equals EXPECT. The only exception is `src-ov-base` `status_lines` 2 instead of 1: BSD `patch` left a `.orig`
  backup after the −1-line offset hunk. The remote GNU `patch` with `--no-backup-if-mismatch` gave 1.

## Remote preflight, 2026-10-22T22:43:28Z (4-gpu-vm, uid 1004 alex)

- Scratch `/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1` was absent.
- 410 GB free on `/mnt/clathrin`.
- CPUs 14–15 were 0% busy over a 3 s `/proc/stat` sample, with only kernel threads last scheduled there.
- Locks probed nonblocking: `/tmp/motioncorr-guard264-cpu14-15.lock`, `/tmp/motioncorr-i61-cpu-14-15.lock` and `/tmp/motioncorr-build.lock` were all free.
- Tools: GNU patch 2.7.6, git 2.43.0.

## Setup, 22:44:00–22:44:12Z, exit 0 (`remote/setup.*`)

- The bundle was copied with `scp` and its hash verified on the host (`bundle_hash_ok`).
- A `bootstrap` clone was checked out at `3751bd05` (status 0 lines) to get the frozen tools.
- Command (`remote/setup.cmd`): `G_SCR=$SCR G_SHA=3751bd05… taskset -c 14-15 flock -n /tmp/motioncorr-guard264-cpu14-15.lock bash $SCR/bootstrap/docs/post_rc0/issue264/native/tools/setup.sh $SCR/g264-3751bd05.bundle be26918e…`
  `setup.sh` is unchanged (sha256 `72b48ac8…6a0a`). The CPU lease was held only for the 12 s of setup.
- `SOURCES.txt` sha256: `b18fe03d566cb4cf7d74917bbc47f4eb3ee66310277f869d398e36ce13d5b751`.

## Live tree receipt, 22:49:45Z (`live-receipt.txt`, sha256 `cf54178c…f4a5`)

Computed from the live trees, independently of `SOURCES.txt`, as R4 F1 option 2 requires. Each tree equals
the EXPECT table in `../n3-cpu1/check_sources.py` / `iteration1_SOURCES.txt`, with the candidate
HEAD normalised to `3751bd05`. The match covers HEAD, full `git diff` sha256, status count, runner and helper:

| Tree | HEAD | diff sha256 | status | runner | helper |
| --- | --- | --- | --- | --- | --- |
| src-cand | 3751bd05 | e3b0c442… (empty) | 0 | 439041e3… | 02d8f5c1… |
| src-base | 36913740 | e3b0c442… (empty) | 0 | 8a3a1ad8… | absent |
| src-ov-base | 36913740 | 4b01e260… | 1 (runner M) | 70fc2de0… | absent |
| src-ov-cand | 3751bd05 | 26274cd3… | 1 (runner M) | 55423793… | 02d8f5c1… |
| src-ov-mut | 3751bd05 | 74b983bc… | 2 (helper M, runner M) | 55423793… | d531871f… |

Further checks on `src-cand`:
- `src`, `tests`, `tools` and `CMakeLists.txt` equal `52affe31`.
- `src` alone equals `4b0e4e73`; the git tree is `edd1737d…` for both.
- Candidate file hashes equal the frozen values: predictions `6ff11cb5…859e`, overlay `f82196ac…`, `n3.py` `68dcf292…`, `runlib.py` `faa27bfa…`, `build.sh` `e51a7cee…`, `setup.sh` `72b48ac8…`, `lane.sh` `c966d198…`, `stage.sh` `68a24eeb…`, and the seven cpu1 files as committed.
- The receipt also shows an earlier loop line `DIFF 4b0e4e73`. That loop compared `tests`/`tools` too, which differ from `4b0e4e73` by design; the following src-only line is the frozen claim.

**State after setup:**
- `logs/` holds only `setup.*`;
- no `build-*` directory, no `n3-*` directory, no `CHAIN.txt`;
- scratch 837,748 KiB, under the 8 GiB cap;
- all three locks free;
- no process of this scratch running.

## Pending (parent)

- **Before GO:** parent's independent live-tree verification against the EXPECT values, plus fresh occupancy and lock checks.
- **After builds (F1 option 2):** compare the `source … dirty-diff-sha256 … status-lines` line in each `cpu1-b-ov-{base,cand,mut}-cpu.log` to EXPECT, and record the binary hashes.
- **After the run (F2):** for the 21 overlay rows, `RUN.json` `env.MC264_N3_COEFFS` must equal the receipt string. Each arm needs one `binary_sha256` equal to its `build-<arm>.binaries.sha256`, and the three arms must have three distinct hashes.
- **Launch (F3):** record `taskset -pc <chain pid>` in the PID receipt. The 8 GiB cap is a start/end scratch-size check only.
- **Results:** the native CPU subset is UNRUN. The 16 CUDA rows, the CUDA mutant and N2 GPU are UNRUN.
