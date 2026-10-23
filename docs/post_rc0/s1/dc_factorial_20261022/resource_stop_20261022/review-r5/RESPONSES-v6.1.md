# R5 response: additive v6.1 repair, 23 October 2026

Branch `experiment/262-worker-v6-sol-20261023`, existing worktree
`/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-334e8a36`.
Starting/reviewed final `1fe458ecc33e9eb2e89f8617d6394854e7a5b6f2`.
Tested v6.1 source `2f32e7be4d75c4451d46fbef66a87540716f48c6`.
The subsequent evidence/response commit changes no tool source. Proposed repair only; independent
R6 is required. No process/native/GPU qualification or merge recommendation.

[AMENDMENT-v6.1.md](../AMENDMENT-v6.1.md) was frozen at
`6c64883988a0451dc1ff617a72ae2627cac5163f` before implementation or tests. The full R5 report,
exact focused iteration-02 and late-error/counterfactual scripts/results, reviewer iteration-01
syntax failure and selected provenance files were verified against the reviewer's whitelist and
retained byte-exact. [RETAINED-HASHES.txt](RETAINED-HASHES.txt) identifies these selected copies;
[REVIEWER-HASHES.txt](REVIEWER-HASHES.txt) is the original complete whitelist. The exact-source export
was not duplicated. Original probe scripts still reference that original review export; they are
retained evidence, not modified launchers. The earlier author and reviewer FAIL records remain FAIL.
Read the complete R5 report and probes, AGENTS.md and frozen v6 contract; refreshed full #262 and
both complete live comments before source changes (latest issue timestamp still 21 October).

## R5-1: K22 fake root interface

The new `test_gpu_worker_v6_1.py` gives K22's fake reaped root `returncode=0`; `poll()` returns that
attribute. The own-group exclusion assertion and verified-other-group positive control remain.
The data driver calls **exact K22 itself**, without invoking the harness main or installing a signal
handler. It reports PASS, worker's actual own group absent and verified synthetic group 900002 present.

Single-site `k22_own_group_exclusion_removed` removes `groups.discard(os.getpgrp())` in the new worker.
It fails only `test_k22_exact_fixture_interface_and_own_group_exclusion` in the 17-test data suite,
with no errors. Thus a working fixture still discriminates the exclusion guard. This does not erase
v6's original AttributeError or upgrade the unrun base process harness.

## R5-2: observer error arriving after cleanup entry

The new worker computes group verification, then checks observer errors again before any group
signal. Errors arriving in main refresh or inside `verified_group` take the existing
`signal_job_group` path and return an uncertainty error. `run_job`'s cleanup-failure/lease-hold policy
is unchanged. Failed group verification without observer errors retains the existing refusal.
The checked fallback function's AST is identical to frozen v6: unreaped-root, PID/birth, parent,
PGID/SID and own-group checks have not changed. Escaped or foreign descendants are never guessed.

New **K36** is data-only and uses a synthetic live root/table and mocked signal calls. Its healthy
control records TERM/KILL, no fallback and no errors. Three late-error cases (second refresh,
verification returning true, verification returning false) each record exactly one checked fallback,
TERM/KILL to the synthetic original group, and retained uncertainty. No process disappearance or
job-lease lifetime claim follows. Existing entry-error, initial-refresh and loop-refresh synthetic
checks remain in the full data suite, as do the birth/parent/PGID/SID/own-group/reaped guards.

Single-site `late_observer_root_signal_removed` deletes only the new fallback call. It fails only
`test_k36_healthy_and_late_error_interleavings`, with no errors. Early branches remain covered by the
same passing tests; no broad cleanup refactor or new ownership rule was introduced.

## Source and control identity

Only five new tool files were needed: `gpu_worker_v6_1.py`, `test_gpu_worker_v6_1.py`,
`run_v6_1_controls.py`, `test_v6_1_static.py`, `v6_1_mutants.json`. The frozen admission test is reused
via its existing `--runner` argument. RUN schema is `dc262-run/v6.1`, worker `gpu_worker_v6_1`.
The runner binds new worker/harness/mutant paths and hashes. It additionally excludes new-version
control names from concurrent admission; PID/birth/ancestor/exact Claude resume-token checks remain
unchanged. The same 11 frozen admission cases pass; additional synthetic new-name exclusions and
Codex-owner refusal are among the 17 data tests. No real old PID/session/birth was supplied to it,
and neither runner main nor any process suite was invoked.

New worker SHA-256: `704e21205d223194d3067ffd7bccc1d02fe6126fe16307816f95d0344c5b1f79`.
Frozen v6 worker stays `df141c02d2432144f2cafb8cba3e703618ae8cbfee8361437f6ddfa628f1508c`.
[All source hashes](../gpu_worker_v6_1_controls/SOURCE-HASHES.json) and
[complete v6-to-v6.1 delta](../gpu_worker_v6_1_controls/DIFF-v6-to-v6_1.patch) are retained.
The new worker logic delta is the late-error branch; other worker changes are version labels and
documentation. Every pre-existing tracked file remains unchanged. No original Opus/root writes,
production src, campaign.py, process_ownership.py, v2-v6 source, prior contract or old evidence change.
GPL-2.0-or-later notices and stdlib/in-repository dependencies are retained.

## Evidence, commands and resources

[New evidence packet](../gpu_worker_v6_1_controls/README.md), iteration
`motioncorr-dc262-v6_1-data-9a1ca400-0198-40d4-af74-739daa52775f`:

- **PASS 17/17**, `test_v6_1_static.py --json <N>/static-units.json`, exit 0. Includes exact K22,
  K36, earlier cleanup branches, identity guards, record/hold behavior and embedded compilation.
- **PASS 11/11**, frozen `test_run_v6_admission.py --runner run_v6_1_controls.py --json ...`, exit 0.
- Direct data calls to K22, K36 and `r3_controls(..., ['K28','K30'])`: **PASS**, details retained.
- Two targeted mutants: **FAIL as expected**, exit 1, exactly the intended failed check each and no
  test errors. Their source bytes/hash and JSON/stdout are retained. All 15 mutant replacements are
  unique and compile; other 13 executions are **UNRUN** for this new source. No blanket mutant PASS.

The one driver invokes CLI entry points through `runpy` with exact argv, in the same interpreter;
there are no child processes. Its outer guards forbid real Popen, PID/group signal calls and signal
handler installation; tests override them only with in-memory mocks. The driver outcome is taken
from result JSON and expected failures, not from exit 0 alone. No new unexpected failure occurred.
Reviewer probe iteration-01 and the earlier v6 author failure are preserved, not rerun or repaired.

Host SCMAC-7L9P2F, macOS 26.7.1 arm64, CPython 3.13.7; interpreter hash captured at driver start:
`127b5dc839447e76f0ed6a6c3b3097dc7903547d2f1a1fe21d7fc40c20b7bc65`.
14 logical CPUs, unpinned, numeric OMP/OpenBLAS/VECLIB threads 1. Fresh load 8.59/9.05/7.79, free space
6,000,631,808 bytes, private nonblocking lifetime scratch flock, cap 256 MiB; measured iteration
scratch 141,104 bytes before final ATTEMPT write. Freeze-stage load/space and lease are also recorded.
Inputs are source files and synthetic data; no MotionCorr binary/movie, device UUID, route witness,
native build or runtime options exist for these checks (N/A/UNRUN). No timings are qualified.

## Remaining blockers

Fresh independent **R6 is required** before considering any prospective Mac process suite. The frozen
Claude-owner admission is still unavailable from Codex; its decision belongs to the parent and no
provider-neutral implementation is included. The process suite is **UNRUN and unspent**. K22/K36
synthetic passing does not establish kernel signals, wrapper/binary disappearance or job-lease hold.
Linux/subreaper/taskset/GNU-time, real SMI, native and GPU execution remain **UNRUN**. GPU stays
**PAUSED**, namespace consumer unimplemented/**BLOCKED**. No SSH, build, process/mock job/live-worker
launch, push, PR, external comment, Notion write, delegation, main merge or tag was performed.
Historical truth remains 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE; #65 corrected workflow UNRUN,
certification INCONCLUSIVE. Parent owns review dispatch, any publication and later policy decisions.
