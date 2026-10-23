# v6 host-tooling controls, 23 October 2026

Final tested source `f5946de124de13379766331bf4f7d2e6491d0bc2`; source hashes in
[SOURCE-HASHES.json](SOURCE-HASHES.json). Full findings, scope and unresolved objections:
[R4 response](../review-r4/RESPONSES-v6.md). CONTRACT-v6 is unchanged.

The real-worker orchestrator suite is **UNRUN**. Codex has no bound Claude ancestor; owner checks
were neither bypassed nor supplied with the old author's identity. The authorization is unspent.
No query/job/worker process, GPU or Linux execution occurs in the data-only checks below.

Four distinct iterations are retained; none was repaired or rerun in place:

- `iteration-01-dfce97f9/`: 12/12 data-only tests PASS, 11/11 admission cases PASS, K28/K30 PASS;
  eight R4 mutants rejected by synthetic checks.
- `iteration-02-15daad22-FAIL/`: **FAIL**, embedded FAULT_ENTRY compilation raises SyntaxError
  (one newline escape). Other 13 tests pass. Mutant results share that error and are not used as
  discriminating evidence. No worker or mock process was launched.
- `iteration-03-1c0e4e86/`: corrected fixture; 14/14 data tests PASS, 11/11 admission PASS,
  K28/K30 PASS, nine R4 mutants fail on their intended synthetic checks.
- `iteration-04-f5946de1-final-source/`: same checks and expected mutant failures on the exact final
  source after the worker docstring correction. Worker and all harness sources are hash-bound.

Each directory contains PREFLIGHT.json, ATTEMPT.json (exact argv and exits), result JSON, stdout,
MUTANTS.json and generated mutant bytes. `real_control: UNRUN` applies to every mutant's process
control. Python sources in each namespace are retained as evidence only. Verification launchers
are retained alongside the iterations. They do not execute run_v6_controls.py or admit a worker.

With `T=docs/post_rc0/s1/dc_factorial_20261022/tools` and `N` a fresh UUID scratch namespace, final
commands (all with OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=VECLIB_MAXIMUM_THREADS=1, nonblocking lifetime
flock, ≤256 MiB scratch allocation) are:

```sh
/Users/alex.konstantinov/.local/bin/python3 -B "$T/test_v6_static.py" --json "$N/static-units.json"
/Users/alex.konstantinov/.local/bin/python3 -B "$T/test_run_v6_admission.py" --json "$N/admission-units.json"
/Users/alex.konstantinov/.local/bin/python3 -B "$T/test_gpu_worker_v6.py" --only K28,K30 --json "$N/K28-K30.json"
# For each retained R4 mutant: same data-only test, --worker "$N/<name>.py", expected exit 1.
```

The baseline tests exit 0. The nine R4 mutants exit 1 and their JSON identifies the precise failed
check; no timing or science inference follows. The four unchanged v5 targeted mutants compile but
were not executed here. Signals and Popen are mocked in the static checks. Embedded harness
scripts are compiled without execution. Admission uses synthetic tables, including a negative
Codex-shaped tree. Real time wrappers, signals, kernel flock lifetime and subreaper adoption remain
UNRUN. Linux K5P and K25W must witness `ownership_mode == linux-child-subreaper` when later authorized.

POSTCHECK.json records host/interpreter identity (the interpreter hash is a post-run observation),
with native binary, movie inputs and device UUID N/A. Raw preflights record load, no pinning, real
ancestry, numeric threads and the scratch lease. No native route witness exists.
TRANSFER.json and transfer-to-final.patch preserve the original unfinished-worker identity/delta.
HASHES.txt hashes this packet, excluding itself.

Raw unittest stdout retains its original trailing spaces. Whole-packet `git diff --check` reports
those spaces; authored source/reports pass the scoped check. Raw evidence is not whitespace-repaired.
