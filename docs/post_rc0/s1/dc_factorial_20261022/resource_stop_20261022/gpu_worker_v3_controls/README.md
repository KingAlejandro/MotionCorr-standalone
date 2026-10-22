# gpu_worker_v3 host mock controls

Every attempt is retained in its own `attempt-NN-<label>/` directory with the
exact worker and test sources, `ATTEMPT.json` (launch PID/birth, host load,
hashes, exit) and the harness `controls.json`/`stdout.log`. [SUMMARY.json](SUMMARY.json)
lists all 18. Runs were made one at a time on macOS (Python 3.13.7, 14 CPUs,
load 3.3–6.8), each after a load check. Every GPU query is a fake `nvidia-smi`;
no GPU, motioncorr, network or remote host is touched.

| Attempts | Harness SHA-256 | Worker | Result |
|---|---|---|---|
| 01 | `36cbb492…` | v3 `a0510eaa…` | 22/22 PASS |
| 02–08 | `36cbb492…` | 7 mutants | each rejected; 07 also has a K12 harness error, 08 did not exercise K8 (harness defects, fixed) |
| **09** | **`73735e79…`** | **v3 `a0510eaa…`** | **22/22 PASS** |
| **10–18** | **`73735e79…`** | **9 mutants** | **all rejected by their targeted controls** |

Final-harness mutant results: `no_admission_occupancy` K3, K8; `ecc_na_accepted`
K2a; `no_queue_hash_binding` K1; `owned_by_identity_keys` K16;
`no_cancel_before_popen` K11; `sampler_failures_uncounted` K7;
`v2_resume_semantics` K1, K8, K9; `unbounded_child_wait` K14;
`no_group_signal` K12, K13. No control reported leftovers in attempts 09–18,
and a process check after the runs found no mock, launcher, fake SMI or
`sleep 300/301` process.

Reproduce one attempt (never overwrites):
`python3 -B tools/run_v3_controls.py <attempts dir> worker` or
`... mutant-<name> --mutant <name>`.

Limits: macOS uses the ownership helper's polling mode, so Linux
child-subreaper adoption is not exercised; the `taskset` prefix is Linux-only
and UNRUN; a query stuck in uninterruptible sleep cannot be reproduced; real
`nvidia-smi` output formats are not exercised; these are host mocks, not native
or GPU evidence.
