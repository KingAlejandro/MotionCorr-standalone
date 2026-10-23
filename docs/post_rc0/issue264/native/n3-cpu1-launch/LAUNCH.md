# #264 cpu1 launch receipt (22 October 2026): one frozen CPU-only chain, in progress

Parent GO came after its independent R4 option-2 live check PASSED at 22:52:37Z (raw
`/tmp/motioncorr-orchestrator-20261022/guard-cpu1-parent-live-v2.json`, sha256 `c61920af…1472`).
The chain is exactly one frozen cpu1 chain at `3751bd05` in the prepared scratch
`/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1`. No GPU or health query, no
CUDA configure, no new source, tools or parameters. Receipts are in `launch-cpu1/` on the host, outside
the `logs/cpu1-*` stage prefix; copies are in `remote/`.

- **Admission, 22:53:37Z:** CPUs 14–15 0% busy over 3 s; the guard264, i61 and build locks free; logs
  held only `setup.*`; no `build-*`, `n3-*` or `launch-*` directory; `src-cand` at `3751bd05` with 0 status lines.
- **Failed local attempt:** the first launch attempt never reached the host. The Mac shell lacked `timeout`, so zsh
  returned 127 before ssh ran. At 22:53:56Z the host still had no `launch-*` directory and no chain process. Recorded in `remote/GO.txt`.
- **Reservation and start:** `mkdir launch-cpu1` was the atomic reservation, followed by a detached `setsid nohup bash -c …` with all stdio
  redirected. The ssh returned 0. Command (`remote/chain.cmd`):
  `G_SCR=$SCR G_SHA=3751bd05… taskset -c 14-15 bash $SCR/src-cand/docs/post_rc0/issue264/native/n3-cpu1/chain_cpu1.sh`.
- **Identity, 22:54:19Z (`remote/identity.txt`):**
  - wrapper PID 3315461 (session leader, uid 1004, started 22:54:09, writes `chain.exit` and `chain.finished`);
  - chain PID 3315463, `taskset -pc` = **14,15**;
  - the wrapper itself has affinity 0–123, but it only waits; the chain and its children inherit 14–15.
  - The chain holds the CPU lease; the first build stage holds the build lock.
- **First build witness, 22:54:29Z (`remote/first-build-witness.txt`):**
  - `cpu1-occupancy-start` rc 0 (PASS);
  - `cpu1-sources` rc 0 (`sources PASS []`; the frozen tool compares `SOURCES.txt` and file hashes, with the live check done by the parent);
  - `cpu1-b-ov-base-cpu` started 22:54:13Z with the source line
    `3691374061f7… dirty-diff-sha256 4b01e260… status-lines 1`, equal to EXPECT;
  - CPU configure done; compiling with two `cc1plus` processes on CPUs 14 and 15.

## Pending (parent owns reconciliation)

- **Running:** the remaining stages, in order: `cpu1-b-ov-cand-cpu`, `cpu1-b-ov-mut-cpu`, `cpu1-receipts`, `cpu1-n3-cpu`, `cpu1-grade`, `cpu1-occupancy-end`.
  Terminal receipts: `launch-cpu1/chain.exit`, `logs/CHAIN.txt`, `logs/CHAIN.stopped_at`.
- **F1 post-build:** the `source` lines of the cand and mut build logs against EXPECT (`3751bd05`, `26274cd3…`/1 and `74b983bc…`/2), and the binary hashes from `build-ov-*-cpu.binaries.sha256`.
- **F2 post-run:**
  - for all 21 overlay rows, `RUN.json` `env.MC264_N3_COEFFS` must equal `n3-cpu1/known-observations.json`;
  - each arm must have one `binary_sha256`, equal to its build receipt;
  - the three arms must have three distinct hashes.
- **Claims:** if the subset passes, only the R4-allowed CPU test-overlay control claim. The full N3/N4 aggregate stays
  INCOMPLETE with 16 CUDA rows UNRUN, and the original iteration-0a N3 stays UNRUN. Any failure or build contention is
  retained and not retried.
