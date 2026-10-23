# Author responses to review R2

Retained review files are byte copies of `/tmp/motioncorr-dc-gpu-worker-review-r2-20261022/`
(REVIEW.md `727025a1…`), checked against the reviewer's `HASHES.txt`. The reviewer's `target/`
export (8.5 MB, a `git archive` of `b36067fb`) and its copy of `process_ownership.py`
(`8de59b8c…`, identical to the repository file) are not duplicated here. v2 and v3, their controls and
all earlier attempts are unchanged. All fixes are in the new `tools/gpu_worker_v4.py` (`071a1588…`).
No Linux, SSH, native, GPU or real `nvidia-smi` action was taken. v4 is not deployed.

## Evidence status, stated first

- **No new-namespace control evidence exists.** The single authorized fresh attempt
  (`gpu_worker_v4_controls-r2/attempt-20261022T235306Z-5a851a56…`) was refused by the r2 runner and is
  **UNRUN**: the runner counted PID 23952, a parent-death watchdog child of the author's own Claude
  process 23920 that carries the session id, as another author. The rule is corrected in the runner
  (`071e36f8…`) but the correction has not been executed. No retry was made.
- Earlier v4 attempts in `gpu_worker_v4_controls/` keep their provenance (see
  [../collision_20261022/README.md](../collision_20261022/README.md)): 01–27 were launched by the author
  and run one at a time; 28–33 were launched by an orphan copy of the author session, without overlap;
  34–37 overlapped and are untrusted. They are not new-namespace evidence. The figures below cite only
  01–27.

## Findings

| Finding | Response in v4 | Control(s) | Mutant result (author attempts, harness) |
|---|---|---|---|
| R2-M1 query children adopted on Linux; sampler outlives classification | Queries run in the worker's own process group (never adoptable: the helper skips `pgid == parent_group`); timeout kills the unreaped Popen; the sampler is stopped and joined before the job's ownership classification; any query identity seen among owned processes fails closed (cleanup error). | K19a/b/c hold a sampler query in flight across job exit, timeout and cancellation under a test-only emulation of the Linux adoption rule on real processes; K20 checks a live query is never owned while a new-session positive control is. Linux execution UNRUN. | `v3_query_lifecycle` (both layers reverted) fails K19a, K20 (19, `c2b6e80a`); `query_new_session` fails K20 (20); `sampler_after_classification` **survives** (21): with queries outside ownership it is defence in depth, individually untested. The unmodified frozen v3 under the earlier harness fails K15L, K19a, K20 (17, `1ffacb1d`). The frozen-v3 runs under `c2b6e80a` (34, 35) are untrusted. |
| R2-m1 observer failure on Linux holds the lease even with zero jobs | Policy: release the lease (exit 75, `OBSERVER_FAILED_ZERO_JOBS`) only when no job was launched by this worker, no owned identity was ever recorded and every query process is reaped. Any launch or owned identity with an observer/restore failure still holds the lease after a receipt (unchanged fail-closed rule). | K15L (observer failure before launch with Linux `restore()` emulated): exit 75, lease free, no hold receipt. K14 still holds after a launch. | `no_zero_job_release` fails K15L (22). |
| R2-m2 own-group exclusion unobservable | Direct unit control with an injected process view: an owned record in the worker's own PGID must never reach `killpg`, while another verified group must (positive control); `os.killpg` is replaced in-process, so nothing is signalled. K12/K13 no longer claim this coverage. | K22 | `no_own_group_exclusion` fails K22 (23). |
| R2-m3 null coverage | The frozen null proposal is unchanged. Clean-null byte stability is necessary but not sufficient: it says nothing about uncovered cells (0/54 contention cells covered; no e12963 job in the null). Any causal contention claim would need a matched null for the same cells (for example an exclusive repeat of the 54 jobs) first. Nothing run. | — | — |
| minor: OK without witness | OK now requires at least one successful sample and `gpu_witness_uuids == [target UUID]`; otherwise the job record keeps `route_witness_problem` and the worker stops (75). | K23 | `witness_not_required` fails K23 (24). |
| minor: census wording | FINAL `complete` means every id reached RUN.json status EXITED with any native exit code; `complete_means` and `exited_nonzero` are recorded. | K5, K8 | — |
| minor: errors before the lease | Runs-dir/log/lease I/O errors print a typed `PRELEASE_IO_ERROR` receipt to stdout and exit 74. Limitation: nothing is written to the runs dir in that case. | K24 | — |
| minor: root unsignalled when observer unhealthy | The unreaped Popen root is now SIGTERM/SIGKILLed through its handle (PID-safe); descendants remain unverified, so the job is still CLEANUP_FAILED with the lease held. Side effect: the v3 `unbounded_child_wait` mutant **survives** (26), because the root is now always reaped; the bounded wait only matters for a root surviving SIGKILL (uninterruptible sleep), which mocks cannot produce. | K14 | `unbounded_child_wait` survives (26). |
| minor: binaries hash unsourced | `28d84f5d…` is now bound to `binaries.json` inside the committed `raw/iter2-3eee0a4b/phase0-build.tar.gz` (`ac5ca45d…`), whose `cuda-exp` entry `35f0c674…` matches the build manifest. Provisional: the remote file has not been re-verified (no SSH). | — | — |
| minor: `--only` advertised | Not present in the v4 harness docstring. The frozen v3 harness is unchanged. | — | — |

Other ported mutants (author attempts 25, 27, harness `c2b6e80a`): `no_admission_occupancy` fails
K3, K8; `no_group_signal` fails K12, K13 and also K19a–c and K22. Attempts 27–29 show failures outside
their targets (K19a–c, K18, K5) during a host-load peak (5-minute load ≈ 38): the harness is
timing-sensitive on a busy host. The orphan copy's longer mock timings (`29c8ec27…`) are retained as
evidence only and are not adopted. Under `c2b6e80a` the real worker passed 30/30 in author attempt 18.
The remaining six ported mutants (`v2_resume_semantics`, `no_queue_hash_binding`,
`owned_by_identity_keys`, `no_cancel_before_popen`, `ecc_na_accepted`, `sampler_failures_uncounted`)
have trusted author results only under the earlier harness `1ffacb1d` (attempts 11–16); their
`c2b6e80a` runs (28–33) were orphan-launched. Not every mutant is rejected: two survive, as stated.

Namespace-aware evaluation and matrix generation remain **unimplemented**; evaluation of any v4 output
namespace is blocked. Linux subreaper execution, the `taskset` prefix, real `nvidia-smi`, a query
stuck in uninterruptible sleep and GPU/native behaviour are UNRUN.
