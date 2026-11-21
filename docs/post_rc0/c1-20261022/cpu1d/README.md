# cpu1d: bounded CPU qualification startup replacement

Parent handoff only. Refs #238 (W1 CPU qualification), resource policy #198 and `POST_FREEZE_TEST_PLAN.md` §9. No push, PR, GitHub comment, Notion update, build, native qualification, numerical fixture or GPU launch was performed in this task.

Branch `docs/c1-cpu-startup-20261022`, isolated worktree `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-b50646d5`, exact base `ffe189214c494c76ee9f0214e7486ea0571898ad`. Implementation/control source commit **`5576c6b5711b32979359f9b12efde90391ea5ba7`**; subsequent evidence commit changes no scripts. All changes are confined to this new `cpu1d/` directory. Author worktree, parent checkout and protected root were not changed.

## Retained status and scope

cpu1c attempt 1 failed before the chain: noclobber prevented opening an existing lock; its `lease.contended` label was incorrect. Attempt 2 acquired the lease and ran the prerequisite: **RAN/FAIL, 24/25 checks** because both launch directories matched its stage glob. The **16 later stages are UNRUN; all native execution is UNRUN**. Old directories, receipts, source, tools and binaries remain unchanged. R2 and its response remain under `../cpu1c/review/`; no numerical criteria have been changed.

cpu1d uses the same 17 stages and allow-sets: only census comparison accepts 0/1; only census decision accepts 0/3. Decision 3 is **INCONCLUSIVE** even if the chain reaches `.done`. FAIL/INCOMPLETE stop. Truth FAIL/UNIDENTIFIABLE outcomes remain valid evidence under the unchanged helper contract. Historical 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE remains intact; no science, performance or engineering-qualification PASS follows from this startup work.

Startup changes only:

- New stage/chain prefix `cpu1d`, T24 directory `t24-cpu1d`, deployed packet `tools-cpu1d-run`. Shared `v2`, `census` and `census-ref-cpu` paths stay unchanged and must remain absent.
- Launch marker **`logs/launch-cpu1d-attempt1`**, outside `logs/cpu1d-*`. Atomic `mkdir` inside the wrapper reserves the invocation before any receipt writes; a duplicate returns 4 and preserves existing receipts. Do not precreate this directory.
- Prerequisite exempts only its own seven known receipt names; every other matching artifact (including unknown names and dangling symlinks) blocks. The unchanged stage wrapper rejects an already reserved prerequisite before its checker can run.
- Append-open FD9 for `/tmp/motioncorr-c1-cpu8-9.lock`; open failure returns 8, contention 7, missing GO 9. No lock wait or retry. Whole wrapper/chain inherits `taskset -c 8-9`; the mask is checked. PID, kernel start ticks/session, UID, actual startup argv, intended chain argv, affinity, child exit/reap and wrapper exit/finish are recorded. A private child handshake permits identity capture before chain execution and self-expires after five seconds if release fails. No signals are used.
- The chain's old GO polling loop becomes an immediate refusal if GO is absent. It is launched only through the wrapper; its existing stage receipts and stop behavior stay intact.

The wrapper has environment overrides solely for harmless controls; the real command uses defaults. Startup `/proc` child argv is the handshake shell; `chain.argv` records the exact subsequent `exec bash CHAIN`. PID and kernel start identity survive that exec. These are launch receipts, not native route witnesses.

## Exact frozen identities

Native candidate source (unchanged, pristine remote checkout): `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`. Frozen CPU tools baseline: `67beb5f59382a74bbc64b10bfa488ab3d549dc0c`.

- C1 CPU binary: `5692c6dc5eaca953357bf7a1161338b99ca320369f0b6c6ab025d9aaa7f9dc3c`.
- Frozen F CPU binary: `43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42`.
- Unchanged `cpu1c_sums.py`: `2efdca7e26a6e78a327cb5eb21284c2b6d3cf4d02d4d8d472e511bbe9832439c`.
- New chain: `3c842fb2c505bf5db4dac37b21db6fcbc0aad1ae3ea1b083b10bba57f2958cdc`.
- New wrapper: `ac71cae5ca0696859fb48731a94c77a235b3266a6f33ee1c6e795635248df404`.
- Identities (100 movies, ten dose1 controls): `45273edefbf8f83fc529fe06636741904f566b5729a51bb81f9e31beb020cf2c`.
- F G/L RUN pins: `05cf608df6fc57e1c5a6e0618277f550f6b2fa27c18ba60a36f88d531d0abd06` / `4b2ffd1fcfee0ccd9d04abedfc3d30560ad5a0ea189a34ed4a7adb626b0d97cb`.
- Tutorial input STAR: `fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041` (inherited input binding; not newly rehashed in this task).

`freeze/cpu1d-manifest.json` retains the original criteria/input identities and the fully expanded 17 argv/allow-sets/expected receipts. `freeze/git-tool-provenance.json` binds **all 32 deployed files to exact Git blobs**: 31 unchanged baseline blobs and the new prerequisite. The unchanged helper keeps its original filename and is not copied into a new validator. Identities and baseline pins are reused read-only under their existing cpu1c filenames.

`freeze_packet.py` asserts the expanded argv and allow-sets equal cpu1c after only namespace/path substitutions, and asserts that the prerequisite outside its freshness block differs only in startup paths. It executes a print-only shell `go` function to expand argv, never a stage or native command. `freeze/packet.sha256` applies to the exported remote packet root, not this smaller retained freeze directory.

## Verification actually run

At 22:28:50–22:28:52 UTC on 22 October, `4-gpu-vm`, uid1004, CPUs8–9, numeric threads1, no GPU UUID/route (not used), append-open nonblocking CPU lease held through controls and direct prerequisite. Full commands are in `evidence/motioncorr-cpu1d-controls-attempt1.sh`. Old wrapper/chain PIDs3308367/3308375 were freshly verified gone before admission. Other CPU workers were active on10–12; no timing claim.

1. Shell/Python syntax checks: PASS. Git-only exporter: PASS (17 argv, exact allow-sets, 32 files, 31 byte-identical shared tools).
2. **13/13 harmless integration controls PASS**, overall exit0. The actual old wrapper2 + unchanged actual stage + exact old prerequisite namespace block reproduces exit1. The new actual wrapper + actual stage + exact new namespace block passes with its own active stage receipts, its own launch PID/start/mask receipts, and both old failure-marker directories present. Tests do not clone freshness logic or run the prerequisite's numerical imports/checkers.
3. Genuine stale reservation/exit/unknown-own-prefix/dangling artifacts block (exit1); stale prerequisite reservation blocks in the actual stage wrapper (4). Existing lease opens correctly, a distinct holder stops before the chain (7), nonzero child exit5 propagates, invocation marker refuses reuse (4) without changing receipts, missing GO stops (9), and open failure is distinct (8).
4. **Real direct prerequisite DRYRUN PASS, 25/25, exit0**, on actual frozen read-only source, binaries, inputs, tools and F-baseline pins. No `c1_stage.sh` or chain invocation for this DRYRUN. Actual filename is `cpu1d-startup-operation1/cpu1d-prereq-dryrun.json`, outside the stage namespace.
5. Final readback: original32 and new32 deployed hashes match; 23 retained old launch-file hashes equal their Git records; all18 captured mock process/start identities gone; CPU lease free; no cpu1d stage receipts, real GO or real launch marker; shared census/v2 paths and T24 directory absent; no AppleDouble files. New scratch data about0.52MB, below the bounded16MiB cap (including packet, deployed tools, controls, receipts; no movie copies).

Raw 391-member control/operation archive: `evidence/startup-controls-attempt1.tgz`, SHA256 `4af1a0bfdeb07c5e8510c0b2f77c4f511061e91db4a67dd0ba55edfd0670866e`. Contains commands, wrapper/stage stdout/stderr, all exits, PID/identity/mask/reap receipts, namespace reports, packet/deployment verification and preflight. Summaries: `evidence/RESULTS.json`, `cpu1d-prereq-dryrun.json`, `final-readback.json`, `verification.json`.

Local exporter command used full implementation SHA after an initial unexecuted export with abbreviated metadata (both local exports retained in `/tmp`; only full-SHA freeze1 was deployed):

```sh
/Users/alex.konstantinov/.local/bin/python3 -B docs/post_rc0/c1-20261022/cpu1d/freeze_packet.py "$PWD" 5576c6b5711b32979359f9b12efde90391ea5ba7 /tmp/motioncorr-cpu1d-packet-freeze1
COPYFILE_DISABLE=1 tar -czf /tmp/motioncorr-cpu1d-packet-freeze1.tgz -C /tmp/motioncorr-cpu1d-packet-freeze1 .
```

Remote frozen packet remains at `/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/cpu1d-startup-freeze1`. Existing files were never overwritten. GitHub #238/#198 bodies and latest relevant discussions were refreshed read-only before edits; latest #238 update was21:54:29Z, #198 resource correction remains18October01:34:27Z. Local context snapshots remain in `/tmp/motioncorr-cpu1d-startup-context/`. Full fetched Notion plan, §9, R2/response and both retained attempts were read.

## Parent's next bounded action

Inspect this diff, all frozen hashes, operational controls and current occupancy; then decide GO once. There is **no real cpu1d stage/native evidence yet**, and no blocker identified in the startup controls. All remaining qualification/science blockers and GPU resource restrictions remain. Review here is author verification, not an independent review.

Recheck remote source/binaries/tools/input pins and all fresh paths immediately before admission. Parent alone creates `logs/chain-cpu1d.go` after approval. Keep `logs/launch-cpu1d-attempt1` absent; the wrapper atomically creates it. Use the default environment (no `CPU1D_*` overrides). Parent command after its explicit GO only:

```sh
set -C
nohup setsid taskset -c 8-9 bash /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/cpu1d-launch-wrapper.sh > /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/logs/launch-cpu1d-attempt1.outer.out 2>&1 < /dev/null &
```

The outer log is also outside the stage glob. Reconcile wrapper/chain identity and exits; do not use `.done` as an aggregate PASS. On contention, a failed stage, or a startup error: retain everything, stop, and freeze a distinct iteration before any further attempt. No name-based signals, in-place retry, old-evidence cleanup, gate relaxation or GPU launch is authorized by this packet.

Limitations: controls use the exact prerequisite namespace block, not the full25 checks on a fabricated input tree; the separate real25-check DRYRUN covers frozen metadata/input admission. Movie payloads were not newly rehashed or evaluated; existing receipt verification remains the native runners' contract. No CI/build/native/scientific/performance validation was performed; intended qualification flags and numerical criteria remain exactly as frozen.
