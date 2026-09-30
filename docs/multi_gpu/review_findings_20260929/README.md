# PR117: final-review product and zombie controls

Tested source: `e082f537106590d40d673a05a1356af57437549c`, on
`aa5ebdfa34b93e0e55b2772a1c744bca2116dc38` and current main `a75a3f87`.
This follow-up changes Python tools/tests only; the retained CPU binary's C++
source and CMake inputs are unchanged. Its hash and that source check are in
`validation.log` inside the archive. No new GPU computation or timing study ran.

## Two reproduced findings

- [r4134022552](https://github.com/KingAlejandro/MotionCorr-standalone/pull/117#discussion_r4134022552):
  `killpg(pgid, 0)` also reports zombies. A Linux test wrapper now adopts orphaned
  grandchildren as a subreaper and deliberately leaves them unreaped during the
  launcher call. Before the fix, an actual killed grandchild caused a runtime
  exception, exit1 and no interruption status. The fixed launcher distinguishes
  live members from zombie-only groups using `/proc` PID/group/session/start/state
  records. Unreadable or ambiguous records remain fail-closed. The test verifies
  the adopted child's zombie state and owned group/session, then reaps it itself.
  Both SIGTERM and SIGINT now retain FAIL status and the expected143/130 exit.
  This is an actual Linux process-state control, not a new Docker execution.
- [r4134022564](https://github.com/KingAlejandro/MotionCorr-standalone/pull/117#discussion_r4134022564):
  an empty required-product list previously returned PASS with zero staged files
  after all scientific products were removed. Empty, whitespace-only and
  comma-only suffix lists now fail before staging or aggregate invocation.
  Healthy default-product merging remains covered. The controls assert that no
  output/report directory or aggregate-side-effect marker is created.

The two before-fix logs are retained. The mutation harness additionally removes
both guards from the actual tool source and requires these cases to reject them.

## Executed on the final source

| Check | Result |
|---|---|
| Scheduler suite including the actual binary's device-list parser | **54/54** |
| Source mutations | **83/83 detected, zero skipped** |
| Required test inventory | **19/19 present** |
| Full CPU CTest, sequential | **19/19** |
| Actual CPU serial versus three workers | **6/6 exact**, six distinct payloads |
| Normalized aggregate STAR | **Identical** |

CPU64 used CPUs32–47 and memory node1 under
`/tmp/motioncorr-issue96-cpu-validation.lock`. Library thread counts were one,
CTest ran sequentially, and the actual-binary arm used at most three j4 workers.
The existing ctffind PIDs1156942/1635429 and their start identities are unchanged.
The validation lock and all owned processes were released. The completed run
ended at **2026-09-29T13:41:13Z**.

Two setup failures are retained separately: an interrupted script upload and a
mistyped source argument rejected by the exact-source preflight. Neither ran the
validation suite. The successful run starts only after the source hash matches.

## Evidence and limits

`raw-evidence.tar.gz` contains the run log, all mutation results, test inventory,
CPU comparison reports and content origins, worker status/manifest and failed
setup logs. `archive-members.sha256` hashes every member; `provenance.json` hashes
the archive and source files. `validate_cpu64.sh` is the executed command script.
Raw CPU product trees remain in `/home/ubuntu/mc-pr117-review-p1-20260929/e2e`.

Earlier retained-native24/24 verification remains attached to the earlier
source/tooling record; this follow-up adds no native CUDA execution, CUDA build,
new support mode or scaling result. Publication, current-head CI and Codex review
are the coordinator's next steps; this local evidence does not perform them.
