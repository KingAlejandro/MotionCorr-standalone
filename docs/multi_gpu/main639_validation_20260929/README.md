# PR117 composed with merged PR114

Combined tested source: `169b1b2582ae28b2b643227c534e19db32602892`.
This is a history-preserving merge of scheduler head `9d9e2282` and current main
`6393547e6ed8a0fcbbda8fc314eb1ab7a969f709` (merged PR114).

## Composition

- Preserved both upstream-change notices in `SOURCE_MANIFEST.txt`.
- Preserved `MultiGpuScheduling`, `RunnerInterpolateRecenter`,
  `RunnerInterpolateShifts`, their required inventory entries and all
  missing-registration controls. The CPU minimum and full inventory are21.
- Runner changes merged without a conflict. Relative to main, the production
  delta remains the scheduler's single-device argument validation/help; the
  recenter arithmetic and call site remain exactly those already merged in114.
- No source/test change followed the tested merge; the publication commit only
  adds this evidence.

## Executed combined-tree acceptance

Fresh Release CPU build on cpu64, CPUs32–47, memory node1, build≤16,
sequential CTest, under `/tmp/motioncorr-issue96-cpu-validation.lock`:

| Check | Result |
|---|---|
| Fresh CPU compilation | PASS |
| Scheduler cases, including real binary parser | 54/54 |
| Source mutations | 83/83 detected, zero skipped |
| Required test inventory | 21/21 |
| Full CPU CTest, including both recenter tests and CI controls | 21/21 |
| Actual CPU serial versus three-worker six-movie run | 6/6 exact |
| Distinct scientific payloads | 6/6 |
| Normalized aggregate STAR | Identical |

Run ended **2026-09-29T13:48:46Z**. All six stage return codes were zero.
The validation lock and owned processes are released; ctffind PIDs1156942 and
1635429 retain their original start identities and were untouched.

The executed script is
`docs/multi_gpu/port_validation/cpu64_port_validation.sh` at the tested commit;
it was invoked through the lock, `taskset -c 32-47` and `numactl --membind=1`.
The git-backed source, fresh binary and raw products remain at
`/home/ubuntu/mc-pr117-main639-20260929`.

`raw-evidence.tar.gz` preserves the command/build/test log, mutation outcomes,
complete test inventory, comparator content origins, worker manifest/status and
CPU comparison summaries. `archive-members.sha256` hashes each member and
`provenance.json` records the source parents and archive digest.

## Remaining scope

Exact published-head CI, including CUDA compilation, runs after publication.
This combined-tree validation includes no fresh native GPU execution or timing
campaign. Earlier PR114 native recenter and PR117 native worker evidence remains
pinned to its recorded sources; a CPU comparison or compile-only CI result does
not relabel it as new GPU evidence. Current-source review and merge decisions
remain with the coordinator.
