# cpu1d actual launch attempt 1: detached, ongoing at bounded startup snapshot

This directory records the **one actual frozen cpu1d launch** authorized by the parent after inspecting implementation `5576c6b5711b32979359f9b12efde90391ea5ba7` and evidence `ed3942652ed3e191d54b9ec1e125521b4757c81c`. It is separate from the earlier 13 harmless controls and 25-check direct DRYRUN. New actual native CPU execution occurred here; the earlier no-native statements remain historical records of the startup-fix task.

Parent preflight at22:41:00Z is retained verbatim in `parent-preflight.json`, SHA256 `272823c82ad17e2bbbcdbaa63cf27c9ebb819a54c0bb47675bc872309cebd229`. Parent created GO exclusively at22:41:18.509362Z. `parent-GO.copy` SHA256 `9032c504c9c49e728a7c349892cbd4140c1a04f5bc04bc90ac93d6e4007762a4` binds that preflight, startup source, candidate source and one-launch scope.

Immediate admission at22:42:33.772324Z: exact e77 source clean, both CPU binary hashes,32 tools, IDs, F-baseline pins/live RUN files and tutorial STAR match; fresh stage/output paths absent; old cpu1c PIDs gone; CPU8/9 each0% busy over3seconds; CPU lease free. `preflight.json` retains the checks. `launch-once.sh` is the exact command sent over `ssh -J ccp4-gateway -oBatchMode=yes -oConnectTimeout=10 -oConnectionAttempts=1 4GPUs 'bash -s'` (transport exit0). No `CPU1D_*` overrides, build, GPU, flag changes, retry or signal.

At22:42:36Z the wrapper atomically created `logs/launch-cpu1d-attempt1`, acquired `/tmp/motioncorr-c1-cpu8-9.lock` nonblocking, and started the frozen chain. There was exactly one nohup/setsid/taskset invocation. The GO file was read, not changed. The launch command is the frozen README command; no long-chain wait or watcher was started.

## Bounded result at22:43:16.962756Z

**ONGOING, no aggregate PASS.** Actual stage receipts:

- `cpu1d-prereq`: exit0, all25 actual checks PASS (not the earlier DRYRUN).
- `cpu1d-v2-cpu-c1`: exit0 (native CPU).
- `cpu1d-v2-cpu-F`: exit0 (native F CPU).
- `cpu1d-v2-eval-F`: exit0.
- `cpu1d-v2-check`: exit0 under the unchanged field/status contract; truth FAIL/UNIDENTIFIABLE may be accepted evidence and are not relabelled.
- `cpu1d-run-c1-cpu-G`: reserved/running, no exit yet; native T24 global processing witnessed.
- Eleven later stages: UNRUN at this snapshot.

Wrapper/chain exits were absent, not0. No unexpected failure was observed. INCONCLUSIVE must remain INCONCLUSIVE if encountered later. cpu1c historical prerequisite FAIL/16 later UNRUN and the historical truth totals remain unchanged.

## Detached identities for parent reconciliation

All below were alive at the snapshot, uid1004, CPU mask8–9, no `CPU1D_*` overrides. Kernel start ticks identify processes beyond PID reuse; raw `/proc/stat`, UID/mask and full actual argv are retained in `startup-status.json` and the raw snapshot.

- Wrapper **3311648**, PPID1, SID3311648, kernel start ticks **816540337**, started22:42:36Z. Actual argv: `bash /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/cpu1d-launch-wrapper.sh`.
- Chain **3311661**, PPID3311648, SID3311648, start ticks **816540340**, started22:42:36Z. Actual argv: `bash /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/chain-cpu1d.sh`.
- Current stage shell **3311877**, PPID3311661, SID3311648, start ticks **816541117**; actual stage `cpu1d-run-c1-cpu-G` through unchanged `tools-cpu1d-run/c1_stage.sh`.
- T24 driver **3311886**, PPID3311877, start ticks **816541119**.
- Native CPU **3311888**, PPID3311887 (`/usr/bin/time`), SID3311887, start ticks **816541126**; binary SHA256 **`5692c6dc5eaca953357bf7a1161338b99ca320369f0b6c6ab025d9aaa7f9dc3c`**. Source **`e77a51a220cb0d91f4ac3c7fac211876d0c6833f`**. Full argv in `startup-status.json`: `--i movies.star --o <SC>/t24-cpu1d/c1-cpu-G/out/ --j 2 --use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --seed 1 --expected_frames 24 --gainref Movies/gain.mrc`. CPU route, no GPU UUID or ingest route witness applies. This matches the frozen T24 CPU contract.

Use SC=`/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb` for these exact reconciliation paths:

- `$SC/logs/launch-cpu1d-attempt1/{wrapper,chain}.{pid,started,uid,cpus,argv,argv.nul,proc-stat,proc-status}`; `.argv.nul` chain startup receipt captures the pre-exec handshake; the bounded live status captures its actual chain argv after exec.
- `$SC/logs/launch-cpu1d-attempt1/{wrapper.exit,wrapper.finished,chain.exit,chain.reaped}` (absent at snapshot), plus `lease.acquired`.
- `$SC/logs/chain-cpu1d.{pid,started,cpus,out,stop,done,finished}`; stop/done/finished not inferred from the launch shell's exit.
- `$SC/logs/cpu1d-run-c1-cpu-G.{reserved/,cmd,pid,started,log,exit,finished}`.
- `$SC/t24-cpu1d/c1-cpu-G/{RUN.json,logs/c1-cpu-G.time,out/}` (RUN/exit may not exist until completion).
- All17 frozen stage exit paths: `$SC/logs/<stage>.exit`, stage names/allow-sets in `../freeze/cpu1d-expanded-stages.txt`.

## Evidence and limits

One three-second startup delay, followed by one read-only metadata/receipt snapshot; no polling loop or whole-chain wait. `capture-startup.py` records the exact snapshot command (remote `taskset -c 8-9 /home/alex/.mc-venv/bin/python3 -B -`, transport exit0). Its finite PPID traversal reads a single `/proc` inventory; it does not monitor or signal processes.

`remote-startup-snapshot.tgz` SHA256 **`49e15fb2f9beeaf87fd31eac1fa8556d0576dec832efe24a3998592abcc3f9df`** contains the immediate preflight, parent GO copy, detached-launch receipt, full stage/startup receipts, actual prerequisite report and bounded live process snapshot. Its remote original directory is `$SC/cpu1d-actual-launch-attempt1`. Live logs/products remain in place for the parent, unchanged by collection. Snapshot logs may be partial while the chain runs. No final health/reap/qualification/science/performance claim is made.

Parent owns subsequent reconciliation, status publication and any decision. This worker returns detached ownership now; it did not wait for completion. On unexpected failure, preserve receipts and stop without retry. No push or publication.
